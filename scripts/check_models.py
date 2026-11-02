"""Verify model IDs and optionally make one small, explicitly requested live call."""
import argparse
import sys

import httpx

from plant_memory.config import get_settings
from plant_memory.model_gateway import ModelGateway, approved_models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Makes one paid request using the configured key")
    parser.add_argument("--model", help="Approved provider/model ID; defaults to MODEL_REASONING")
    args = parser.parse_args()
    settings = get_settings()
    response = httpx.get(settings.ai_gateway_base_url.rstrip("/") + "/models", timeout=20)
    response.raise_for_status()
    ids = {entry["id"] for entry in response.json()["data"]}
    missing = sorted(approved_models() - ids)
    print("Configured model IDs:")
    for model in sorted(approved_models()):
        print(f"  {model}: {'listed' if model in ids else 'NOT LISTED'}")
    print("Credential configured:", ModelGateway().available())
    if missing:
        return 1
    if not args.live:
        print("Catalog validation only; provider credentials and inference are not yet verified.")
        return 0
    model = args.model or settings.model_reasoning
    result = ModelGateway().complete_json(model=model,
        system="Return JSON with status set to ok. This is a connectivity test, not an engineering analysis.",
        user="Check the connection.",
        schema={"type": "object", "properties": {"status": {"type": "string", "enum": ["ok"]}},
                "required": ["status"], "additionalProperties": False},
        purpose="connectivity_test", org_id=None, project_id=None, max_tokens=256)
    print("Live response:", result.parsed)
    print("Model:", result.model, "Tokens:", result.input_tokens + result.output_tokens,
          "Reported cost USD:", result.cost_usd)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Do not log request objects, authorization headers, or environment values.
        print(f"Verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
