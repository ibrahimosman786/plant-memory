"""Single adapter for hosted model calls from Python services (extraction, classification).

- Routes through Vercel AI Gateway's OpenAI-compatible endpoint.
- Only approved model IDs (settings.model_*) may be used; no silent fallback to another model.
- Every call is recorded in model_calls with model, provider, prompt version, tokens, cost, latency.
- Enforces the environment-wide active-call semaphore and the monthly budget guard.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select

from . import PROMPT_VERSION
from .cache import LimitExceeded, semaphore
from .config import get_settings
from .db.models import ModelCall
from .db.session import scoped_session


class ModelUnavailable(RuntimeError):
    """Raised when the gateway is not configured or a call fails. Callers must degrade to
    `partial`/`blocked`, never to 'no issue found'."""


class BudgetExhausted(RuntimeError):
    pass


@dataclass
class ModelResponse:
    content: str
    parsed: Any | None
    model: str
    provider: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int
    tool_calls: list[dict] | None = None


def approved_models() -> set[str]:
    s = get_settings()
    return {s.model_fast, s.model_reasoning, s.model_escalation}


def month_to_date_spend(org_id: uuid.UUID | None = None) -> Decimal:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with scoped_session(None) as s:
        q = select(func.coalesce(func.sum(ModelCall.cost_usd), 0)).where(ModelCall.at >= start)
        if org_id:
            q = q.where(ModelCall.org_id == org_id)
        return Decimal(str(s.execute(q).scalar_one()))


def assert_budget_available() -> None:
    s = get_settings()
    spent = month_to_date_spend()
    if spent >= Decimal(str(s.monthly_model_budget_usd)):
        raise BudgetExhausted(f"monthly model budget {s.monthly_model_budget_usd} USD exhausted (spent {spent})")


class ModelGateway:
    def __init__(self) -> None:
        self.s = get_settings()

    def available(self) -> bool:
        return bool(self.s.ai_gateway_api_key)

    def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict,
        purpose: str,
        org_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        run_id: uuid.UUID | None = None,
        max_tokens: int = 4000,
        temperature: float = 0.0,
        timeout: float = 90.0,
    ) -> ModelResponse:
        if model not in approved_models():
            raise ModelUnavailable(f"model {model} is not in the approved set")
        if not self.available():
            raise ModelUnavailable("AI_GATEWAY_API_KEY is not configured")
        assert_budget_available()
        body = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "output", "schema": schema, "strict": True}},
        }
        started = time.perf_counter()
        ok = True
        try:
            with semaphore("pm:llm:env", self.s.env_max_active_llm_calls):
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(
                        f"{self.s.ai_gateway_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.s.ai_gateway_api_key}", "Content-Type": "application/json"},
                        json=body,
                    )
            resp.raise_for_status()
            data = resp.json()
        except LimitExceeded as exc:
            raise ModelUnavailable(str(exc)) from exc
        except (httpx.HTTPError, ValueError) as exc:
            ok = False
            self._record(org_id, project_id, run_id, purpose, model, None, 0, 0, Decimal("0"), int((time.perf_counter() - started) * 1000), ok)
            raise ModelUnavailable(f"gateway call failed: {exc}") from exc
        latency = int((time.perf_counter() - started) * 1000)
        content = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        cost = Decimal(str(usage.get("cost", 0) or 0))
        provider = (data.get("providerMetadata") or {}).get("gateway", {}).get("provider") if isinstance(data.get("providerMetadata"), dict) else None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = None
        self._record(org_id, project_id, run_id, purpose, model, provider, in_tok, out_tok, cost, latency, ok)
        return ModelResponse(content, parsed, model, provider, in_tok, out_tok, cost, latency)

    def complete_chat(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict],
        purpose: str,
        org_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        run_id: uuid.UUID | None = None,
        max_tokens: int = 2000,
        timeout: float = 90.0,
    ) -> ModelResponse:
        """Tool-calling turn. The approved-model and budget rules are the same as complete_json."""
        if model not in approved_models():
            raise ModelUnavailable(f"model {model} is not in the approved set")
        if not self.available():
            raise ModelUnavailable("AI_GATEWAY_API_KEY is not configured")
        assert_budget_available()
        body = {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        started = time.perf_counter()
        try:
            with semaphore("pm:llm:env", self.s.env_max_active_llm_calls):
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(
                        f"{self.s.ai_gateway_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.s.ai_gateway_api_key}", "Content-Type": "application/json"},
                        json=body,
                    )
            resp.raise_for_status()
            data = resp.json()
        except LimitExceeded as exc:
            raise ModelUnavailable(str(exc)) from exc
        except (httpx.HTTPError, ValueError) as exc:
            self._record(org_id, project_id, run_id, purpose, model, None, 0, 0, Decimal("0"), int((time.perf_counter() - started) * 1000), False)
            raise ModelUnavailable(f"gateway call failed: {exc}") from exc
        latency = int((time.perf_counter() - started) * 1000)
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        cost = Decimal(str(usage.get("cost", 0) or 0))
        provider = (data.get("providerMetadata") or {}).get("gateway", {}).get("provider") if isinstance(data.get("providerMetadata"), dict) else None
        self._record(org_id, project_id, run_id, purpose, model, provider, in_tok, out_tok, cost, latency, True)
        return ModelResponse(content, None, model, provider, in_tok, out_tok, cost, latency, tool_calls=message.get("tool_calls") or [])

    @staticmethod
    def _record(org_id, project_id, run_id, purpose, model, provider, in_tok, out_tok, cost, latency, ok) -> None:
        with scoped_session(None) as s:
            s.add(ModelCall(org_id=org_id, project_id=project_id, run_id=run_id, purpose=purpose, model=model, provider=provider,
                            prompt_version=PROMPT_VERSION, input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost, latency_ms=latency, ok=ok))


def record_external_usage(*, org_id, project_id, run_id, model: str, input_tokens: int, output_tokens: int, cost_usd: Decimal, purpose: str = "agent") -> None:
    """Usage reported by the eve stream for the coordinator model is recorded here so the
    budget guard sees agent spend too."""
    ModelGateway._record(org_id, project_id, run_id, purpose, model, "gateway", input_tokens, output_tokens, cost_usd, 0, True)
