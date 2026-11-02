"""Tool endpoints for the agent runtime. Authenticated with the run-scoped service token; the
tenant/project come from that token, never from the request body."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth.deps import ServiceDbDep, ServicePrincipalDep
from ..db.models import Run
from ..runs.tools import ToolError, invoke, tool_manifest

router = APIRouter(prefix="/internal/tools", tags=["internal"])


class ToolCall(BaseModel):
    input: dict[str, Any] = {}


@router.get("")
def manifest(principal: ServicePrincipalDep) -> list[dict]:
    return tool_manifest()


@router.post("/{name}")
def call_tool(name: str, body: ToolCall, principal: ServicePrincipalDep, s: ServiceDbDep) -> dict:
    run = s.get(Run, principal.run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    try:
        result = invoke(s, run, name, body.input)
    except ToolError as exc:
        s.commit()
        raise HTTPException(exc.http_status, {"code": exc.code, "message": str(exc)}) from exc
    s.commit()
    return result.model_dump()
