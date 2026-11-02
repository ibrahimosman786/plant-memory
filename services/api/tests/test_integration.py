"""Opt in with PM_RUN_INTEGRATION=1. Creates labelled synthetic test data, never calls a paid model."""
import json
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plant_memory.config import get_settings
from plant_memory.main import app
from plant_memory.model_gateway import ModelGateway, ModelResponse

pytestmark = pytest.mark.skipif(os.getenv("PM_RUN_INTEGRATION") != "1", reason="requires local Postgres and demo fixture")


@pytest.fixture(scope="module")
def workspace():
    assert get_settings().environment != "production", "Never seed integration data in production"
    from plant_memory.cli import _kind
    from plant_memory.ingestion.pipeline import process_document_version
    c = TestClient(app)
    stamp = uuid.uuid4().hex[:8]
    auth = c.post("/v1/auth/dev-token", json={"email": f"eval-{stamp}@plant-memory.local", "org_name": f"Evaluation {stamp}"})
    assert auth.status_code == 200, auth.text
    h = {"Authorization": "Bearer " + auth.json()["token"]}
    org_id = uuid.UUID(auth.json()["org_id"])
    p = c.post("/v1/projects", json={"name": f"Verification {stamp}", "description": "Synthetic automated test data"}, headers=h)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    base = f"/v1/projects/{pid}"
    fixture = Path(__file__).resolve().parents[3] / "packages/synthetic-data/out/v02"
    manifest = json.loads((fixture / "manifest.json").read_text())
    for rel in manifest["documents"]:
        file = fixture / rel
        r = c.post(base + "/documents", headers=h,
                   files={"file": (file.name, file.read_bytes())}, data={"kind": _kind(file), "revision_label": "A"})
        assert r.status_code == 201, r.text
        process_document_version(uuid.UUID(r.json()["id"]), org_id, uuid.UUID(pid), model_candidates=False)
    snap = c.post(base + "/snapshots", json={"name": "Verification baseline"}, headers=h)
    assert snap.status_code == 201, snap.text
    yield c, h, base, snap.json()["id"]
    c.close()


def run_case(workspace, tags, backend="local", model=None):
    c, h, base, snapshot = workspace
    cr = c.post(base + "/change-requests", json={"title": "Verification change", "request_text": "Investigate replacing the control panel", "target_tags": tags}, headers=h)
    assert cr.status_code == 201, cr.text
    start = c.post(base + f"/change-requests/{cr.json()['id']}/runs", json={"snapshot_id": snapshot, "backend": backend, "model": model}, headers=h)
    assert start.status_code == 202, start.text
    rid = start.json()["id"]
    end = time.monotonic() + 90
    while time.monotonic() < end:
        result = c.get(base + f"/runs/{rid}", headers=h).json()
        if result["state"] not in ("queued", "running"):
            return result
        time.sleep(0.15)
    pytest.fail("Investigation did not finish within 90 seconds")


@pytest.fixture(scope="module")
def report(workspace):
    c, h, base, _ = workspace
    result = run_case(workspace, ["CP-101"])
    assert result["state"] in ("completed", "incomplete"), result
    assert result["report_version_id"], result
    rv = c.get(base + f"/report-versions/{result['report_version_id']}", headers=h).json()
    return result, rv


def test_upload_trace_report_and_export(workspace, report):
    c, h, base, _ = workspace
    result, rv = report
    pkg = rv["package"]
    assert len(pkg["equipment"]) > 1
    assert pkg["findings"]
    assert pkg["work_items"] and pkg["checklist"]
    assert pkg["evidence"]
    assert any("range" in f["title"].lower() for f in pkg["findings"])
    allowed = {e["id"] for e in pkg["evidence"]}
    assert all(set(f["evidence_ids"]) <= allowed for f in pkg["findings"])
    for format_ in ("json", "html", "md"):
        r = c.post(base + f"/report-versions/{rv['id']}/export?format={format_}", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["bytes"] > 100
    events = c.get(base + f"/runs/{result['id']}/events", headers=h).json()
    assert len({e["sequence"] for e in events}) == len(events)


def test_unknown_target_stays_incomplete(workspace):
    result = run_case(workspace, ["ZZ-9999"])
    assert result["state"] == "incomplete"


def test_cross_organization_access_denied(workspace, report):
    c, _, base, _ = workspace
    auth = c.post("/v1/auth/dev-token", json={"email": f"outsider-{uuid.uuid4().hex}@example.com", "org_name": "Other evaluation tenant"}).json()
    response = c.get(base + f"/report-versions/{report[1]['id']}", headers={"Authorization": "Bearer " + auth["token"]})
    assert response.status_code in (403, 404)


def test_missing_key_does_not_fake_analysis(workspace, report, monkeypatch):
    c, h, base, _ = workspace
    monkeypatch.setattr(ModelGateway, "available", lambda self: False)
    response = c.post(base + f"/report-versions/{report[1]['id']}/analyses", headers=h,
        json={"question": "What conflicts exist?", "model": "openai/gpt-6-astra"})
    assert response.status_code == 503


def test_analysis_persists_without_changing_report(workspace, report, monkeypatch):
    c, h, base, _ = workspace
    rv = report[1]
    evidence = rv["package"]["evidence"][0]
    output = {"claims": [{"statement": "Test commentary", "evidence_ids": [evidence["id"]]}],
              "questions_for_engineer": [], "limitations": ["Mocked model response; not a live AI result"]}
    monkeypatch.setattr(ModelGateway, "available", lambda self: True)
    monkeypatch.setattr(ModelGateway, "complete_json", lambda self, **kwargs: ModelResponse(
        json.dumps(output), output, kwargs["model"], "test", 20, 10, Decimal("0"), 1))
    r = c.post(base + f"/report-versions/{rv['id']}/analyses", headers=h,
        json={"question": "Test evidence analysis", "model": "openai/gpt-6-astra"})
    assert r.status_code == 201, r.text
    history = c.get(base + f"/report-versions/{rv['id']}/analyses", headers=h).json()
    assert history[0]["model"] == "openai/gpt-6-astra"
    assert c.get(base + f"/report-versions/{rv['id']}", headers=h).json()["package"] == rv["package"]
    output["claims"][0]["evidence_ids"] = [str(uuid.uuid4())]
    bad = c.post(base + f"/report-versions/{rv['id']}/analyses", headers=h,
        json={"question": "Test foreign citation", "model": "openai/gpt-6-astra"})
    assert bad.status_code == 502


def test_gateway_selection_and_fallback(workspace, monkeypatch):
    monkeypatch.setattr(ModelGateway, "available", lambda self: False)
    result = run_case(workspace, ["CP-101"], "gateway", "openai/gpt-6-astra")
    assert result["model"] == "openai/gpt-6-astra"
    assert result["backend"] == "guided"
    assert result["model_connected"] is False
    assert result["report_version_id"]


def test_scripted_agent_calls_tools_with_selected_model(workspace, monkeypatch):
    calls = []
    def complete(self, **kwargs):
        calls.append(kwargs["model"])
        tools = [{"id": "resolve-1", "type": "function", "function": {"name": "resolve_equipment", "arguments": '{"query":"CP-101"}'}}] if len(calls) == 1 else []
        return ModelResponse("Test agent turn", None, kwargs["model"], "test", 10, 5, Decimal("0"), 1, tools)
    monkeypatch.setattr(ModelGateway, "available", lambda self: True)
    monkeypatch.setattr(ModelGateway, "complete_chat", complete)
    result = run_case(workspace, ["CP-101"], "gateway", "openai/gpt-6-astra")
    assert result["state"] in ("completed", "incomplete"), result
    assert result["report_version_id"]
    assert result["model_connected"] is True
    assert calls == ["openai/gpt-6-astra", "openai/gpt-6-astra"]


def test_new_revision_stales_report_and_stays_out_of_old_snapshot(workspace, report):
    from plant_memory.db.session import TenantScope, scoped_session
    from plant_memory.engine.context import SnapshotContext
    from plant_memory.ingestion.pipeline import process_document_version
    from plant_memory.db.models import Equipment
    from sqlalchemy import select
    c, h, base, snapshot_id = workspace
    docs = c.get(base + "/documents", headers=h).json()
    doc = next(d for d in docs if d["filename"] == "equipment_list.csv")
    uploaded = c.post(base + "/documents", headers=h,
        files={"file": ("equipment_list.csv", b"tag,type,description\nPT-999,transmitter,Future revision only\n", "text/csv")},
        data={"kind": "equipment_list", "revision_label": "B", "document_id": doc["id"]})
    assert uploaded.status_code == 201, uploaded.text
    org = uuid.UUID(c.get("/v1/me", headers=h).json()["org_id"])
    pid = uuid.UUID(base.rsplit("/", 1)[1])
    process_document_version(uuid.UUID(uploaded.json()["id"]), org, pid, model_candidates=False)
    with scoped_session(TenantScope(org, (pid,))) as s:
        future = s.execute(select(Equipment).where(Equipment.project_id == pid, Equipment.normalized_tag == "PT-999")).scalars().one()
        assert SnapshotContext(s, org, pid, uuid.UUID(snapshot_id)).equipment_by_id([future.id]) == {}
    rv = report[1]
    response = c.post(base + f"/report-versions/{rv['id']}/reviews", headers=h, json={"decision": "approved"})
    assert response.status_code == 409, response.text
    analysis = c.post(base + f"/report-versions/{rv['id']}/analyses", headers=h,
        json={"question": "Analyze outdated evidence", "model": "openai/gpt-6-astra"})
    assert analysis.status_code == 409


def test_verified_session_provisions_isolated_workspaces(workspace, monkeypatch):
    from plant_memory.routers import auth
    settings = get_settings().model_copy(update={"session_exchange_secret": "test-exchange-credential-" * 3})
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    c = workspace[0]
    h = {"X-Session-Exchange": settings.session_exchange_secret}
    identities = []
    for _ in range(2):
        suffix = uuid.uuid4().hex
        body = {"subject": f"user_{suffix}", "email": f"session-{suffix}@example.com", "name": "Session test"}
        response = c.post("/v1/auth/session", headers=h, json=body)
        assert response.status_code == 200, response.text
        identities.append(response.json())
        again = c.post("/v1/auth/session", headers=h, json=body)
        assert again.json()["org_id"] == response.json()["org_id"]
    assert identities[0]["org_id"] != identities[1]["org_id"]


def test_snapshot_inventory_paginates_authorized_equipment(workspace, report):
    from plant_memory.db.session import TenantScope, scoped_session
    from plant_memory.db.models import Run
    from plant_memory.engine.context import SnapshotContext
    from plant_memory.runs.tools import InventoryIn, _inventory
    c, h, base, _ = workspace
    org_id = uuid.UUID(c.get("/v1/me", headers=h).json()["org_id"])
    pid = uuid.UUID(base.rsplit("/", 1)[1])
    result, _ = report
    with scoped_session(TenantScope(org_id, (pid,))) as session:
        run = session.get(Run, uuid.UUID(result['id']))
        ctx = SnapshotContext(session, org_id, run.project_id, run.snapshot_id)
        first = _inventory(ctx, run, InventoryIn(limit=1)).data
        assert first['equipment_total'] > 1
        assert len(first['equipment']) == 1
        assert first['next_offset'] == 1
        second = _inventory(ctx, run, InventoryIn(offset=1, limit=1)).data
        assert first['equipment'][0]['id'] != second['equipment'][0]['id']
        assert {d['version_id'] for d in first['documents']} == {str(v) for v in ctx.version_ids}


def test_project_chat_retrieves_cites_and_handles_followups(workspace, monkeypatch):
    c, h, base, snapshot_id = workspace
    calls = []
    foreign = [False]
    def complete(self, **kwargs):
        payload = json.loads(kwargs['user'])
        calls.append((kwargs['purpose'], payload))
        if kwargs['purpose'] == 'chat_search_plan':
            output = {'in_scope': True, 'queries': ['CP-101']}
        else:
            assert payload['evidence']
            eid = str(uuid.uuid4()) if foreign[0] else payload['evidence'][0]['id']
            output = {'claims': [{'statement': 'Scripted evidence response', 'evidence_ids': [eid]}],
                      'questions_for_engineer': [], 'limitations': ['Scripted test, not a live AI answer']}
        return ModelResponse(json.dumps(output), output, kwargs['model'], 'test', 10, 10, Decimal('0'), 1)
    monkeypatch.setattr(ModelGateway, 'available', lambda self: True)
    monkeypatch.setattr(ModelGateway, 'complete_json', complete)
    body = {'question': 'What about its replacement?', 'snapshot_id': snapshot_id, 'model': 'openai/gpt-6-astra',
            'history': [{'role':'user','content':'Tell me about CP-101'}]}
    r = c.post(base + '/chat', headers=h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()['sources']
    assert calls[0][1]['history'][0]['content'] == 'Tell me about CP-101'
    assert r.json()['analysis']['claims'][0]['evidence_ids'][0] in {e['id'] for e in r.json()['sources']}
    foreign[0] = True
    bad = c.post(base + '/chat', headers=h, json=body)
    assert bad.status_code == 502
    assert 'outside' in bad.json()['detail']
    denied = c.post(base + '/chat', headers=h, json={**body, 'snapshot_id':str(uuid.uuid4())})
    assert denied.status_code == 404


def test_project_chat_redirects_unrelated_question(workspace, monkeypatch):
    c, h, base, snapshot_id = workspace
    calls = []
    monkeypatch.setattr(ModelGateway, 'available', lambda self: True)
    def complete(self, **kwargs):
        calls.append(kwargs['purpose'])
        output = {'in_scope': False, 'queries': []}
        return ModelResponse(json.dumps(output), output, kwargs['model'], 'test', 10, 10, Decimal('0'), 1)
    monkeypatch.setattr(ModelGateway, 'complete_json', complete)
    r=c.post(base+'/chat',headers=h,json={'question':'Write a film review','snapshot_id':snapshot_id,'model':'openai/gpt-6-astra'})
    assert r.status_code == 200
    assert r.json()['analysis']['claims'] == []
    assert calls == ['chat_search_plan']
