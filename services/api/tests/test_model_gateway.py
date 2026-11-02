from decimal import Decimal

import httpx
import pytest

from plant_memory import model_gateway as mg
from plant_memory.config import Settings


@pytest.fixture
def gateway(monkeypatch):
    settings = Settings(_env_file=None, ai_gateway_api_key="unit-test-only")
    monkeypatch.setattr(mg, "get_settings", lambda: settings)
    monkeypatch.setattr(mg, "assert_budget_available", lambda: None)
    records = []
    monkeypatch.setattr(mg.ModelGateway, "_record", lambda *args: records.append(args))
    return mg.ModelGateway(), records


def mock_response(monkeypatch, data, status=200):
    requests = []
    real_client = httpx.Client
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=data)
    monkeypatch.setattr(mg.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    return requests


def completion(content='{"ok":true}', **kwargs):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": "0.001"}, **kwargs}


@pytest.mark.parametrize("data", [{}, {"choices": []}, {"choices": [None]},
    {"choices": [{"message": {"content": "x"}, "finish_reason": "length"}]},
    {"choices": [{"message": {"refusal": "blocked"}}]},
    completion(usage={"cost": "NaN"}), completion(usage={"prompt_tokens": -1}),
    {"choices": [{"message": {"tool_calls": [{"function": {"name": "x", "arguments": "{}"}}]}}]}])
def test_rejects_malformed_or_incomplete_response(data):
    with pytest.raises(mg.ModelUnavailable):
        mg.parse_completion(data)


def test_schema_and_usage(gateway, monkeypatch):
    g, records = gateway
    mock_response(monkeypatch, completion())
    result = g.complete_json(model=g.s.model_fast, system="test", user="test",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        purpose="test", org_id=None, project_id=None)
    assert result.parsed == {"ok": True}
    assert result.cost_usd == Decimal("0.001")
    assert records[-1][-1] is True


@pytest.mark.parametrize("content", ['{"ok":"wrong type"}', 'not JSON'])
def test_schema_failure_is_not_success(gateway, monkeypatch, content):
    g, records = gateway
    mock_response(monkeypatch, completion(content))
    with pytest.raises(mg.ModelUnavailable, match="JSON schema"):
        g.complete_json(model=g.s.model_fast, system="test", user="test",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            purpose="test", org_id=None, project_id=None)
    assert records[-1][-1] is False


def test_unknown_model_rejected_before_network(gateway):
    g, _ = gateway
    with pytest.raises(mg.ModelUnavailable, match="approved"):
        g.complete_chat(model="made-up/model", messages=[], tools=[], purpose="test", org_id=None, project_id=None)


def test_gpt_tool_call_request(gateway, monkeypatch):
    import json
    g, _ = gateway
    calls = [{"id": "call_1", "type": "function", "function": {"name": "resolve_equipment", "arguments": '{"query":"PT-101"}'}}]
    data = completion(None)
    data["choices"][0]["message"]["tool_calls"] = calls
    requests = mock_response(monkeypatch, data)
    result = g.complete_chat(model="openai/gpt-6-astra", messages=[], tools=[], purpose="test", org_id=None, project_id=None)
    assert result.tool_calls == calls
    assert "temperature" not in json.loads(requests[0].content)


@pytest.mark.parametrize("status", [401, 402, 429, 503])
def test_provider_failures_are_explicit(gateway, monkeypatch, status):
    g, records = gateway
    mock_response(monkeypatch, {"error": "unavailable"}, status)
    with pytest.raises(mg.ModelUnavailable):
        g.complete_chat(model=g.s.model_reasoning, messages=[], tools=[], purpose="test", org_id=None, project_id=None)
    assert records[-1][-1] is False


def test_account_verification_error_is_actionable_without_echoing_body():
    response = httpx.Response(403, json={"error": {"type": "customer_verification_required", "message": "secret raw body"}})
    message = mg.gateway_error(response)
    assert "payment card" in message
    assert "secret raw body" not in message


def test_paid_credit_requirement_has_specific_message():
    response = httpx.Response(403, json={'error': {'type': 'no_providers_available', 'message': 'Free tier users do not have access. Upgrade to paid credits.'}})
    assert 'paid Vercel AI Gateway credits' in mg.gateway_error(response)
