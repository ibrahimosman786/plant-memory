"""Single adapter for hosted model calls from Python services (extraction, classification).

- Routes through Vercel AI Gateway's OpenAI-compatible endpoint.
- Only approved model IDs (settings.model_*) may be used; no silent fallback to another model.
- Every call is recorded in model_calls with model, provider, prompt version, tokens, cost, latency.
- Enforces the environment-wide active-call semaphore and the monthly budget guard.
"""

from __future__ import annotations

import json
import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from jsonschema import validate, ValidationError as SchemaError
from sqlalchemy import func, select

from . import PROMPT_VERSION
from .cache import LimitExceeded, semaphore, cache_get_json, cache_set_json
from .config import get_settings
from .db.models import ModelCall
from .db.session import scoped_session


class ModelUnavailable(RuntimeError):
    """Raised when the gateway is not configured or a call fails. Callers must degrade to
    `partial`/`blocked`, never to 'no issue found'."""


class BudgetExhausted(RuntimeError):
    pass


def gateway_error(response: httpx.Response) -> str:
    """Translate provider failures without leaking raw response text or credentials."""
    try:
        error = response.json().get("error", {})
        code = error.get("type") or error.get("code") if isinstance(error, dict) else None
    except (ValueError, AttributeError):
        code = None
    if code == "no_providers_available" and isinstance(error, dict) and "paid credits" in str(error.get("message", "")).lower():
        return "This model requires paid Vercel AI Gateway credits. Add AI Gateway credits to the account that owns this key; adding a payment method alone is not sufficient."
    if code == "customer_verification_required":
        return "Vercel AI Gateway requires account verification: add a valid payment card in the Vercel AI Gateway dashboard."
    return {
        401: "AI Gateway rejected the credential. Check the server API key.",
        402: "AI Gateway credits or spending limit exhausted. Check the account budget.",
        403: "AI Gateway denied access. Check account verification and key permissions.",
        429: "AI Gateway rate limit reached. Retry after the limit clears.",
    }.get(response.status_code, f"AI Gateway request failed (HTTP {response.status_code}).")


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
    return {s.model_fast, s.model_reasoning, s.model_escalation, *s.model_alternatives}


def _health_key(model: str) -> str:
    s = get_settings()
    digest = hashlib.sha256(f"{s.ai_gateway_base_url}|{s.ai_gateway_api_key}|{model}".encode()).hexdigest()
    return "pm:model-health:" + digest


def record_health(model: str, ok: bool, message: str) -> None:
    try:
        cache_set_json(_health_key(model), {"state": "ready" if ok else "blocked", "message": message,
            "checked_at": datetime.now(timezone.utc).isoformat()}, ttl=900)
    except Exception:
        pass  # diagnostics must not interrupt inference


def model_health(model: str) -> dict:
    if not get_settings().ai_gateway_api_key:
        return {"state": "unconfigured", "message": "No AI Gateway credential is configured.", "checked_at": None}
    try:
        cached = cache_get_json(_health_key(model))
        if cached:
            return cached
    except Exception:
        pass
    return {"state": "unchecked", "message": "Credential saved; no recent verified connection for this model.", "checked_at": None}


def parse_completion(data: dict) -> tuple[dict, dict]:
    """Reject truncated, refused and malformed responses before treating them as evidence."""
    try:
        choice = data["choices"][0]
        message = choice["message"]
        if choice.get("finish_reason") in ("length", "content_filter") or message.get("refusal"):
            raise ValueError("model response was truncated or refused")
        if not isinstance(message, dict) or not isinstance(message.get("content") or "", str):
            raise ValueError("invalid message")
        calls = message.get("tool_calls") or []
        if not isinstance(calls, list):
            raise ValueError("invalid tool calls")
        for call in calls:
            if not isinstance(call.get("id"), str) or not call["id"]:
                raise ValueError("tool call is missing an id")
            fn = call["function"]
            if not isinstance(fn.get("name"), str) or not isinstance(fn.get("arguments"), str):
                raise ValueError("invalid tool call")
        usage = data.get("usage") or {}
        for field in ("prompt_tokens", "completion_tokens"):
            if int(usage.get(field, 0)) < 0:
                raise ValueError("negative token count")
        cost = Decimal(str(usage.get("cost", 0) or 0))
        if not cost.is_finite() or cost < 0:
            raise ValueError("invalid cost")
        return message, usage
    except (KeyError, IndexError, AttributeError, TypeError, ValueError, ArithmeticError) as exc:
        raise ModelUnavailable("Gateway returned an invalid, truncated, or refused response") from exc


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
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "output", "schema": schema, "strict": True}},
        }
        # Some reasoning models do not support temperature. Use their default sampling.
        if not model.startswith("openai/"):
            body["temperature"] = temperature
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
            message = gateway_error(exc.response) if isinstance(exc, httpx.HTTPStatusError) else "AI Gateway is unreachable or returned invalid JSON."
            record_health(model, False, message)
            raise ModelUnavailable(message) from exc
        latency = int((time.perf_counter() - started) * 1000)
        try:
            message, usage = parse_completion(data)
        except ModelUnavailable as exc:
            record_health(model, False, str(exc))
            self._record(org_id, project_id, run_id, purpose, model, None, 0, 0, Decimal("0"), latency, False)
            raise
        content = message.get("content") or ""
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        cost = Decimal(str(usage.get("cost", 0) or 0))
        provider = (data.get("providerMetadata") or {}).get("gateway", {}).get("provider") if isinstance(data.get("providerMetadata"), dict) else None
        try:
            parsed = json.loads(content)
            validate(parsed, schema)
        except (json.JSONDecodeError, SchemaError) as exc:
            record_health(model, False, "Model output did not match the required JSON schema")
            self._record(org_id, project_id, run_id, purpose, model, provider, in_tok, out_tok, cost, latency, False)
            raise ModelUnavailable("Model output did not match the required JSON schema") from exc
        self._record(org_id, project_id, run_id, purpose, model, provider, in_tok, out_tok, cost, latency, ok)
        record_health(model, True, "Last model request succeeded.")
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
            message = gateway_error(exc.response) if isinstance(exc, httpx.HTTPStatusError) else "AI Gateway is unreachable or returned invalid JSON."
            record_health(model, False, message)
            raise ModelUnavailable(message) from exc
        latency = int((time.perf_counter() - started) * 1000)
        try:
            message, usage = parse_completion(data)
        except ModelUnavailable as exc:
            record_health(model, False, str(exc))
            self._record(org_id, project_id, run_id, purpose, model, None, 0, 0, Decimal("0"), latency, False)
            raise
        content = message.get("content") or ""
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        cost = Decimal(str(usage.get("cost", 0) or 0))
        provider = (data.get("providerMetadata") or {}).get("gateway", {}).get("provider") if isinstance(data.get("providerMetadata"), dict) else None
        self._record(org_id, project_id, run_id, purpose, model, provider, in_tok, out_tok, cost, latency, True)
        record_health(model, True, "Last model request succeeded.")
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
