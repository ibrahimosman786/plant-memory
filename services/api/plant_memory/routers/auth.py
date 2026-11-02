"""Identity: dev token issuance (local only), current principal, bootstrap of a dev org."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from ..auth.deps import PrincipalDep
from ..auth.tokens import issue_dev_token
from ..config import get_settings
from ..db.models import Membership, Organization, Project, User
from ..db.session import get_engine, scoped_session
from ..model_gateway import ModelGateway

router = APIRouter(prefix="/v1", tags=["auth"])


@router.get("/status")
def public_status() -> dict:
    """What is running, in terms a new user can read. No secrets."""
    settings = get_settings()
    db_ok = True
    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
    except Exception:
        db_ok = False
    model_connected = ModelGateway().available()
    return {
        "database": db_ok,
        "auth_backend": settings.auth_backend,
        "agent_backend": settings.agent_backend,
        "model_connected": model_connected,
        "reasoning_model": settings.model_reasoning if model_connected else None,
    }


class DevTokenIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    name: str | None = None
    org_name: str = "Spartan Controls (dev)"
    role: str = "admin"


@router.post("/auth/dev-token")
def dev_token(body: DevTokenIn) -> dict:
    """Development-only: provisions the user (and a dev org) and returns a signed token.
    Disabled unless AUTH_BACKEND=dev."""
    s_ = get_settings()
    if s_.auth_backend != "dev":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if body.role not in ("viewer", "analyst", "reviewer", "admin"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad role")
    with scoped_session(None) as s:
        user = s.execute(select(User).where(User.email == body.email)).scalars().first()
        if user is None:
            user = User(email=body.email, name=body.name or body.email.split("@")[0], external_subject=f"dev:{body.email}")
            s.add(user)
            s.flush()
        org = s.execute(select(Organization).where(Organization.name == body.org_name)).scalars().first()
        if org is None:
            org = Organization(name=body.org_name)
            s.add(org)
            s.flush()
        m = s.execute(select(Membership).where(Membership.org_id == org.id, Membership.user_id == user.id)).scalars().first()
        if m is None:
            s.add(Membership(org_id=org.id, user_id=user.id, role=body.role))
        else:
            m.role = body.role
        s.commit()
        return {"token": issue_dev_token(user.id, user.email), "user_id": str(user.id), "org_id": str(org.id), "role": body.role}


@router.get("/me")
def me(principal: PrincipalDep) -> dict:
    with scoped_session(None) as s:
        projects = s.execute(select(Project).where(Project.id.in_(list(principal.project_roles.keys())))).scalars().all() if principal.project_roles else []
    return {"user_id": str(principal.user_id), "org_id": str(principal.org_id), "email": principal.email, "name": principal.name, "org_role": principal.org_role,
            "projects": [{"id": str(p.id), "name": p.name, "role": principal.project_roles[p.id]} for p in projects]}
