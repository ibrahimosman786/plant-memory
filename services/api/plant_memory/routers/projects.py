from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth.deps import PrincipalDep, require_project_role
from ..auth.principal import Principal
from ..db.models import Project, ProjectMember, User
from ..db.session import TenantScope, scoped_session

router = APIRouter(prefix="/v1/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class MemberIn(BaseModel):
    email: str
    role: str


def _org_scope(principal: Principal) -> TenantScope:
    """projects table: org admins see every project in the org, others only their grants."""
    if principal.org_role == "admin":
        return TenantScope(principal.org_id, all_projects=True)
    return TenantScope(principal.org_id, principal.project_ids)


def project_out(p: Project, role: str | None) -> dict:
    return {"id": str(p.id), "name": p.name, "description": p.description, "permissions_version": p.permissions_version, "role": role, "created_at": p.created_at.isoformat()}


@router.get("")
def list_projects(principal: PrincipalDep) -> list[dict]:
    with scoped_session(_org_scope(principal)) as s:
        rows = s.execute(select(Project).where(Project.org_id == principal.org_id).order_by(Project.created_at)).scalars().all()
        return [project_out(p, principal.project_roles.get(p.id, "admin" if principal.org_role == "admin" else None)) for p in rows]


@router.post("", status_code=201)
def create_project(body: ProjectIn, principal: PrincipalDep) -> dict:
    if principal.org_role not in ("admin", "reviewer", "analyst"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cannot create projects")
    with scoped_session(TenantScope(principal.org_id, all_projects=True)) as s:
        p = Project(org_id=principal.org_id, name=body.name, description=body.description)
        s.add(p)
        s.flush()
        s.add(ProjectMember(org_id=principal.org_id, project_id=p.id, user_id=principal.user_id, role="admin"))
        s.commit()
        return project_out(p, "admin")


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))]) -> dict:
    with scoped_session(_org_scope(principal)) as s:
        p = s.get(Project, project_id)
        if p is None or p.org_id != principal.org_id:
            raise HTTPException(404)
        members = s.execute(select(ProjectMember, User).join(User, User.id == ProjectMember.user_id).where(ProjectMember.project_id == project_id)).all()
        out = project_out(p, principal.project_roles.get(project_id))
        out["members"] = [{"user_id": str(u.id), "email": u.email, "name": u.name, "role": m.role} for m, u in members]
        return out


@router.post("/{project_id}/members")
def add_member(project_id: uuid.UUID, body: MemberIn, principal: Annotated[Principal, Depends(require_project_role("admin"))]) -> dict:
    if body.role not in ("viewer", "analyst", "reviewer", "admin"):
        raise HTTPException(422, "bad role")
    with scoped_session(_org_scope(principal)) as s:
        user = s.execute(select(User).where(User.email == body.email)).scalars().first()
        if user is None:
            raise HTTPException(404, "user not provisioned")
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404)
        pm = s.execute(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)).scalars().first()
        if pm is None:
            s.add(ProjectMember(org_id=principal.org_id, project_id=project_id, user_id=user.id, role=body.role))
        else:
            pm.role = body.role
        p.permissions_version += 1  # invalidates permission-scoped caches
        s.commit()
        return {"ok": True, "permissions_version": p.permissions_version}
