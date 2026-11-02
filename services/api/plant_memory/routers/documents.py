"""Documents: upload (direct multipart for local dev or presigned PUT), versions, evidence, files."""

from __future__ import annotations

import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select

from .. import PIPELINE_VERSION
from ..auth.deps import DbDep, PrincipalDep, require_project_role
from ..auth.principal import Principal
from ..config import get_settings
from ..db.models import Document, DocumentVersion, EvidenceSpan
from ..queue import INGEST_QUEUE, get_queue
from ..storage import Buckets, LocalStorage, derived_key, get_storage, original_key

router = APIRouter(prefix="/v1", tags=["documents"])

ALLOWED_CONTENT = {
    "text/csv", "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain", "application/octet-stream",
}
ALLOWED_EXT = {".csv", ".xlsx", ".pdf", ".docx", ".txt", ".md"}
KINDS = {"equipment_list", "io_list", "narrative", "datasheet", "pid", "config_export", "catalogue", "rates", "note", "other"}


def version_out(v: DocumentVersion, d: Document | None = None) -> dict:
    out = {"id": str(v.id), "document_id": str(v.document_id), "version_no": v.version_no, "sha256": v.sha256, "revision_label": v.revision_label, "status": v.status,
           "status_detail": v.status_detail, "content_type": v.content_type, "size_bytes": v.size_bytes, "page_count": v.page_count, "pipeline_version": v.pipeline_version,
           "supersedes_id": str(v.supersedes_id) if v.supersedes_id else None, "created_at": v.created_at.isoformat()}
    if d:
        out["filename"] = d.original_filename
        out["kind"] = d.kind
    return out


def _check_quota(s, project_id: uuid.UUID, size: int, filename: str, content_type: str) -> None:
    st = get_settings()
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT or (content_type and content_type.split(";")[0] not in ALLOWED_CONTENT):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"unsupported file type {ext} / {content_type}")
    if size > st.max_file_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"file exceeds {st.max_file_bytes} bytes")
    n = s.execute(select(func.count(Document.id)).where(Document.project_id == project_id)).scalar_one()
    if n >= st.max_files_per_project:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"project file limit {st.max_files_per_project} reached")
    pages = s.execute(select(func.coalesce(func.sum(DocumentVersion.page_count), 0)).where(DocumentVersion.project_id == project_id)).scalar_one()
    if pages >= st.max_pdf_pages_per_project:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"project page limit {st.max_pdf_pages_per_project} reached")


def _register(s, principal: Principal, project_id: uuid.UUID, *, filename: str, content_type: str, data: bytes, kind: str, revision_label: str | None, document_id: uuid.UUID | None) -> tuple[Document, DocumentVersion, bool]:
    sha = hashlib.sha256(data).hexdigest()
    if document_id:
        doc = s.get(Document, document_id)
        if doc is None or doc.project_id != project_id:
            raise HTTPException(404, "document not found")
        prev = s.execute(select(DocumentVersion).where(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.version_no.desc())).scalars().first()
        if prev and prev.sha256 == sha:
            return doc, prev, False  # identical upload: idempotent
        version_no = (prev.version_no + 1) if prev else 1
        supersedes = prev.id if prev else None
    else:
        dup = s.execute(select(DocumentVersion).where(DocumentVersion.project_id == project_id, DocumentVersion.sha256 == sha)).scalars().first()
        if dup:
            return s.get(Document, dup.document_id), dup, False
        doc = Document(org_id=principal.org_id, project_id=project_id, original_filename=filename, kind=kind, created_by=principal.user_id)
        s.add(doc)
        s.flush()
        version_no, supersedes = 1, None
    v = DocumentVersion(org_id=principal.org_id, project_id=project_id, document_id=doc.id, version_no=version_no, sha256=sha, revision_label=revision_label, status="uploaded",
                        storage_key="", content_type=content_type or "application/octet-stream", size_bytes=len(data), supersedes_id=supersedes, created_by=principal.user_id)
    s.add(v)
    s.flush()
    v.storage_key = original_key(principal.org_id, project_id, v.id, filename)
    get_storage().put(Buckets.originals(), v.storage_key, data, v.content_type)
    return doc, v, True


def _enqueue(v: DocumentVersion) -> None:
    get_queue().enqueue("ingest", f"{v.id}:{PIPELINE_VERSION}", {"version_id": str(v.id), "org_id": str(v.org_id), "project_id": str(v.project_id)})


@router.post("/projects/{project_id}/documents", status_code=201)
async def upload_document(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep,
                          file: UploadFile = File(...), kind: str = Form("other"), revision_label: str | None = Form(None), document_id: uuid.UUID | None = Form(None)) -> dict:
    if kind not in KINDS:
        raise HTTPException(422, "bad kind")
    data = await file.read()
    _check_quota(s, project_id, len(data), file.filename or "upload", file.content_type or "")
    doc, v, created = _register(s, principal, project_id, filename=file.filename or "upload", content_type=file.content_type or "application/octet-stream", data=data, kind=kind, revision_label=revision_label, document_id=document_id)
    s.commit()
    if created:
        _enqueue(v)
    return {**version_out(v, doc), "created": created}


class PresignIn(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    kind: str = "other"
    revision_label: str | None = None
    document_id: uuid.UUID | None = None


@router.post("/projects/{project_id}/documents/presign")
def presign_upload(project_id: uuid.UUID, body: PresignIn, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    """Two-step upload for S3 deployments: presign → client PUT → /complete. Local dev can also use this."""
    if body.kind not in KINDS:
        raise HTTPException(422, "bad kind")
    _check_quota(s, project_id, body.size_bytes, body.filename, body.content_type)
    staging = f"staging/{principal.org_id}/{project_id}/{uuid.uuid4()}/{body.filename}"
    return {"upload": get_storage().presign_put(Buckets.originals(), staging, body.content_type), "staging_key": staging}


class CompleteIn(BaseModel):
    staging_key: str
    filename: str
    content_type: str
    kind: str = "other"
    revision_label: str | None = None
    document_id: uuid.UUID | None = None


@router.post("/projects/{project_id}/documents/complete", status_code=201)
def complete_upload(project_id: uuid.UUID, body: CompleteIn, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    if not body.staging_key.startswith(f"staging/{principal.org_id}/{project_id}/"):
        raise HTTPException(403, "staging key not owned by caller")
    storage = get_storage()
    if not storage.exists(Buckets.originals(), body.staging_key):
        raise HTTPException(404, "staged object missing")
    data = storage.get(Buckets.originals(), body.staging_key)
    _check_quota(s, project_id, len(data), body.filename, body.content_type)
    doc, v, created = _register(s, principal, project_id, filename=body.filename, content_type=body.content_type, data=data, kind=body.kind, revision_label=body.revision_label, document_id=body.document_id)
    s.commit()
    if created:
        _enqueue(v)
    return {**version_out(v, doc), "created": created}


@router.get("/projects/{project_id}/documents")
def list_documents(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> list[dict]:
    docs = s.execute(select(Document).where(Document.project_id == project_id).order_by(Document.created_at)).scalars().all()
    versions = s.execute(select(DocumentVersion).where(DocumentVersion.project_id == project_id).order_by(DocumentVersion.version_no)).scalars().all()
    by_doc: dict[uuid.UUID, list] = {}
    for v in versions:
        by_doc.setdefault(v.document_id, []).append(version_out(v))
    return [{"id": str(d.id), "filename": d.original_filename, "kind": d.kind, "created_at": d.created_at.isoformat(), "versions": by_doc.get(d.id, [])} for d in docs]


@router.get("/projects/{project_id}/documents/{document_id}/versions/{version_id}")
def get_version(project_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> dict:
    v = s.get(DocumentVersion, version_id)
    d = s.get(Document, document_id)
    if v is None or d is None or v.document_id != document_id or v.project_id != project_id:
        raise HTTPException(404)
    out = version_out(v, d)
    out["download_url"] = get_storage().presign_get(Buckets.originals(), v.storage_key, filename=d.original_filename)
    if v.page_count:
        out["page_images"] = [get_storage().presign_get(Buckets.derived(), derived_key(v.org_id, v.project_id, v.id, v.pipeline_version or PIPELINE_VERSION, f"pages/{p}.png")) for p in range(1, v.page_count + 1)]
    return out


@router.post("/projects/{project_id}/documents/{document_id}/versions/{version_id}/reprocess")
def reprocess(project_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    v = s.get(DocumentVersion, version_id)
    if v is None or v.project_id != project_id:
        raise HTTPException(404)
    queued = get_queue().enqueue("ingest", f"{v.id}:{PIPELINE_VERSION}:reprocess:{uuid.uuid4().hex[:6]}", {"version_id": str(v.id), "org_id": str(v.org_id), "project_id": str(v.project_id)})
    return {"queued": queued}


@router.get("/projects/{project_id}/evidence")
def get_evidence(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, ids: Annotated[list[uuid.UUID], Query()] = []) -> list[dict]:
    if not ids:
        return []
    rows = s.execute(select(EvidenceSpan, DocumentVersion, Document).join(DocumentVersion, DocumentVersion.id == EvidenceSpan.document_version_id).join(Document, Document.id == DocumentVersion.document_id)
                     .where(EvidenceSpan.id.in_(ids[:100]), EvidenceSpan.project_id == project_id)).all()
    out = []
    for sp, v, d in rows:
        item = {"id": str(sp.id), "document_version_id": str(v.id), "document_id": str(d.id), "filename": d.original_filename, "kind": d.kind, "revision_label": v.revision_label,
                "version_no": v.version_no, "locator": sp.locator, "text": sp.text, "span_kind": sp.kind}
        page = (sp.locator or {}).get("page")
        if page and v.page_count:
            item["page_image_url"] = get_storage().presign_get(Buckets.derived(), derived_key(v.org_id, v.project_id, v.id, v.pipeline_version or PIPELINE_VERSION, f"pages/{page}.png"))
        out.append(item)
    return out


# ---- local-storage signed file endpoints (S3 deployments use presigned S3 URLs instead)

@router.get("/files/get")
def file_get(bucket: str, key: str, exp: int, sig: str, filename: str | None = None) -> Response:
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not storage.verify(bucket, key, exp, sig, "get"):
        raise HTTPException(403, "bad or expired signature")
    if not storage.exists(bucket, key):
        raise HTTPException(404)
    headers = {"Content-Disposition": f'inline; filename="{filename}"'} if filename else {}
    return Response(storage.get(bucket, key), media_type=storage.content_type(bucket, key), headers=headers)


@router.put("/files/put")
async def file_put(bucket: str, key: str, exp: int, sig: str, request: Request) -> dict:
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not storage.verify(bucket, key, exp, sig, "put"):
        raise HTTPException(403, "bad or expired signature")
    data = await request.body()
    if len(data) > get_settings().max_file_bytes:
        raise HTTPException(413)
    storage.put(bucket, key, data, request.headers.get("content-type", "application/octet-stream"))
    return {"ok": True}
