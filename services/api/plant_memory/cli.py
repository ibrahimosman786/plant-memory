"""Operator CLI.

  python -m plant_memory.cli seed-demo --variant v02 [--out packages/synthetic-data/out] [--email dev@spartan.local]
  python -m plant_memory.cli ingest-pending           # drain the ingest queue once (no worker needed)
  python -m plant_memory.cli investigate --project <id> --snapshot <id> --request "..." --tags PT-103A [--backend gateway|local|eve]

Everything goes through the HTTP API with an issued token so the CLI exercises the same path the
UI does (uploads, quotas, RLS, queue).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

KIND_BY_NAME = {"equipment_list.csv": "equipment_list", "io_list.xlsx": "io_list", "config_export.csv": "config_export", "control_narrative.docx": "narrative",
                "pid.pdf": "pid", "catalogue.csv": "catalogue", "rates.csv": "rates"}


def _client():
    from .main import app
    return TestClient(app)


def _token(c: TestClient, email: str, role: str = "admin") -> str:
    r = c.post("/v1/auth/dev-token", json={"email": email, "role": role})
    r.raise_for_status()
    return r.json()["token"]


def _kind(path: Path) -> str:
    if path.name in KIND_BY_NAME:
        return KIND_BY_NAME[path.name]
    if path.parent.name == "datasheets":
        return "datasheet"
    if path.suffix == ".txt":
        return "note"
    if "revB" in path.name or "io_list" in path.name:
        return "io_list"
    return "other"


def seed_demo(args) -> None:
    out = Path(args.out)
    variant_dir = out / args.variant
    manifest = json.loads((variant_dir / "manifest.json").read_text())
    c = _client()
    tok = _token(c, args.email)
    h = {"Authorization": f"Bearer {tok}"}
    with c:
        p = c.post("/v1/projects", json={"name": args.project_name or f"Pumping station {args.variant}", "description": f"Synthetic variant {args.variant} ({manifest['family']})"}, headers=h)
        p.raise_for_status()
        project = p.json()
        print(f"project {project['id']} {project['name']}")
        docs_by_name: dict[str, str] = {}
        for rel in manifest["documents"]:
            path = variant_dir / rel
            if path.name.endswith("_revB_delta.csv"):
                continue  # uploaded afterwards as a new version of io_list
            ct = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix == ".csv":
                ct = "text/csv"
            with path.open("rb") as fh:
                r = c.post(f"/v1/projects/{project['id']}/documents", files={"file": (path.name, fh, ct)}, data={"kind": _kind(path), "revision_label": manifest.get("revision")}, headers=h)
            if r.status_code >= 400:
                print(f"  upload {rel} failed: {r.status_code} {r.text[:200]}")
                continue
            v = r.json()
            docs_by_name[path.name] = v["document_id"]
            print(f"  uploaded {rel} -> version {v['id']} ({v['kind']})")
        print("ingesting…")
        from .worker import drain_once
        n = drain_once()
        print(f"  processed {n} jobs")
        # revision deltas become a new version of the I/O list
        for rel in manifest["documents"]:
            path = variant_dir / rel
            if path.name.endswith("_revB_delta.csv") and "io_list.xlsx" in docs_by_name:
                with path.open("rb") as fh:
                    r = c.post(f"/v1/projects/{project['id']}/documents", files={"file": (path.name, fh, "text/csv")}, data={"kind": "io_list", "revision_label": "B", "document_id": docs_by_name["io_list.xlsx"]}, headers=h)
                print(f"  uploaded revision {rel}: {r.status_code}")
                drain_once()
        docs = c.get(f"/v1/projects/{project['id']}/documents", headers=h).json()
        for d in docs:
            for v in d["versions"]:
                det = v["status_detail"]
                print(f"  {d['filename']:<28} v{v['version_no']} {v['status']:<8} spans={det.get('spans')} eq={det.get('extraction', {}).get('equipment_created')} asr={det.get('extraction', {}).get('assertions')} warn={len(det.get('warnings', []))}")
        sn = c.post(f"/v1/projects/{project['id']}/snapshots", json={"name": f"{args.variant} baseline"}, headers=h)
        sn.raise_for_status()
        print(f"snapshot {sn.json()['id']} with {len(sn.json()['document_version_ids'])} versions")
        print(json.dumps({"project_id": project["id"], "snapshot_id": sn.json()["id"]}))


def ingest_pending(args) -> None:
    from .worker import drain_once
    print(f"processed {drain_once()} jobs")


def investigate(args) -> None:
    c = _client()
    tok = args.token or _token(c, args.email)
    h = {"Authorization": f"Bearer {tok}"}
    with c:
        cr = c.post(f"/v1/projects/{args.project}/change-requests", json={"title": args.title or args.request[:80], "request_text": args.request, "target_tags": args.tags or []}, headers=h)
        cr.raise_for_status()
        run = c.post(f"/v1/projects/{args.project}/change-requests/{cr.json()['id']}/runs", json={"snapshot_id": args.snapshot, "backend": args.backend}, headers=h)
        run.raise_for_status()
        run_id = run.json()["id"]
        print(f"run {run_id} started ({args.backend})")
        seen = -1
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            evs = c.get(f"/v1/projects/{args.project}/runs/{run_id}/events", params={"after": seen}, headers=h).json()
            for e in evs:
                seen = e["sequence"]
                print(f"  [{e['sequence']:>3}] {e['type']:<26} {json.dumps(e['payload'])[:160]}")
            r = c.get(f"/v1/projects/{args.project}/runs/{run_id}", headers=h).json()
            if r["state"] == "waiting_clarification" and args.answer:
                pending = [cq for cq in r["clarifications"] if cq["answer"] is None]
                if pending:
                    a = c.post(f"/v1/projects/{args.project}/runs/{run_id}/clarifications/{pending[0]['id']}/answer", json={"answer": args.answer}, headers=h)
                    print(f"  answered clarification: {a.status_code}")
                    continue
            if r["state"] not in ("queued", "running"):
                print(f"run state {r['state']} (tools={r['tool_invocations']}, cost={r['cost_usd']})")
                if r.get("report_version_id"):
                    rv = c.get(f"/v1/projects/{args.project}/report-versions/{r['report_version_id']}", headers=h).json()
                    pkg = rv["package"]
                    print(f"report v{rv['version_no']} status={rv['status']} findings={len(pkg['findings'])} work_items={len(pkg['work_items'])} checklist={len(pkg['checklist'])} estimate_complete={(pkg.get('estimate') or {}).get('complete')}")
                    for f in pkg["findings"]:
                        print(f"   - [{f['severity']}] {f['type']}: {f['title']}")
                    if args.export:
                        ex = c.post(f"/v1/projects/{args.project}/report-versions/{r['report_version_id']}/export", params={"format": args.export}, headers=h)
                        print(f"export: {ex.json()}")
                return
            time.sleep(0.5)
        print("timed out waiting for run")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plant-memory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed-demo")
    s.add_argument("--variant", default="v02")
    s.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "packages" / "synthetic-data" / "out"))
    s.add_argument("--email", default="dev@spartan.local")
    s.add_argument("--project-name")
    s.set_defaults(fn=seed_demo)
    i = sub.add_parser("ingest-pending")
    i.set_defaults(fn=ingest_pending)
    v = sub.add_parser("investigate")
    v.add_argument("--project", required=True)
    v.add_argument("--snapshot", required=True)
    v.add_argument("--request", required=True)
    v.add_argument("--title")
    v.add_argument("--tags", nargs="*")
    v.add_argument("--backend", default="gateway", choices=["gateway", "local", "eve"])
    v.add_argument("--answer", help="auto-answer the first clarification with this text")
    v.add_argument("--export", choices=["md", "html", "json"])
    v.add_argument("--timeout", type=float, default=120)
    v.add_argument("--email", default="dev@spartan.local")
    v.add_argument("--token")
    v.set_defaults(fn=investigate)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
