from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from plant_memory.model_gateway import ModelUnavailable
from plant_memory.routers.analysis import AnalysisOutput, report_context, validate_citations
from plant_memory.runs.gateway_agent import Trail, _absorb


def test_foreign_evidence_rejected():
    output = AnalysisOutput(claims=[{"statement": "A conflict exists", "evidence_ids": ["foreign"]}],
                            questions_for_engineer=[], limitations=["Requires review"])
    with pytest.raises(ModelUnavailable, match="outside"):
        validate_citations(output, {"allowed"})


def test_claim_requires_citation():
    with pytest.raises(ValidationError):
        AnalysisOutput(claims=[{"statement": "Unsupported", "evidence_ids": []}],
                       questions_for_engineer=[], limitations=["Review"])


def test_abstention_is_valid():
    output = AnalysisOutput(claims=[], questions_for_engineer=["Which revision is authoritative?"],
                            limitations=["Insufficient evidence"])
    validate_citations(output, set())


def test_context_budget_preserves_evidence_records():
    context, ids = report_context({"evidence": [{"id": str(i), "text": "x" * 4000} for i in range(50)]})
    assert context["evidence_omitted"] > 0
    assert ids == {e["id"] for e in context["evidence"]}
    assert all(len(e["text"]) <= 3500 for e in context["evidence"])


def test_failed_check_does_not_count_as_complete():
    trail = Trail()
    _absorb(None, None, trail, "run_consistency_checks", SimpleNamespace(status="failed"))
    assert not trail.checked
    assert "run_consistency_checks" in trail.failed_tools


def test_successful_retry_clears_failure():
    trail = Trail(failed_tools={"run_consistency_checks"})
    _absorb(None, None, trail, "run_consistency_checks", SimpleNamespace(status="complete", data={"findings": []}))
    assert trail.checked
    assert not trail.failed_tools


def test_agent_tool_payload_keeps_source_and_work_identifiers():
    import json
    from plant_memory.runs.gateway_agent import _compact
    for name, data in [
        ("get_evidence", {"id": "source-1", "text": "Pump range 0–100", "locator": {"page": 3}}),
        ("search_evidence", {"results": [{"evidence_id": "source-1", "text": "Pump range"}]}),
        ("build_work_scope", {"work_items": [{"id": "work-1", "description": "Review range"}]}),
    ]:
        result = SimpleNamespace(status="complete", warnings=[], data=data, evidence_ids=["source-1"])
        payload = json.loads(_compact(name, result))
        assert payload["data"] == data
        assert payload["evidence_ids"] == ["source-1"]
        assert not payload["payload_truncated"]


def test_agent_large_tool_payload_is_valid_bounded_json():
    import json
    from plant_memory.runs.gateway_agent import _compact
    result = SimpleNamespace(status="complete", warnings=[],
                             data={"results": [{"id": str(i), "text": "x" * 10000} for i in range(100)]})
    encoded = _compact("search_evidence", result)
    payload = json.loads(encoded)
    assert len(encoded) <= 20000
    assert payload["payload_truncated"]
    assert payload["data"]["results"][0]["id"] == "0"
