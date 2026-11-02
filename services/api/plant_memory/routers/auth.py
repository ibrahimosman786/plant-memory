"""Identity: dev token issuance (local only), current principal, bootstrap of a dev org."""

from __future__ import annotations

import uuid
import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from ..auth.deps import PrincipalDep
from ..auth.tokens import issue_dev_token
from ..config import get_settings
from ..db.models import Membership, Organization, Project, User
from ..db.session import get_engine, scoped_session
from ..model_gateway import BudgetExhausted, ModelGateway, ModelUnavailable, approved_models, model_health, record_health

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
    configured = ModelGateway().available()
    health = model_health(settings.model_reasoning)
    model_connected = health["state"] == "ready"
    return {
        "database": db_ok,
        "auth_backend": settings.auth_backend,
        "dev_login_enabled": settings.auth_backend == "dev" and settings.environment != "production",
        "agent_backend": settings.agent_backend,
        "model_connected": model_connected,
        "reasoning_model": settings.model_reasoning if model_connected else None,
        "model_configured": configured,
        "connection_verified": model_connected,
        "model_health": health,
        "default_model": settings.model_reasoning,
        "models": sorted(approved_models()),
    }


class CheckModelIn(BaseModel):
    model: str = Field(min_length=1, max_length=150)


@router.post("/models/check")
def check_model(body: CheckModelIn, principal: PrincipalDep) -> dict:
    if principal.org_role not in ("admin", "analyst", "reviewer"):
        raise HTTPException(403, "An analyst or administrator must check the model connection")
    if body.model not in approved_models():
        raise HTTPException(422, "model is not in the approved set")
    try:
        ModelGateway().complete_json(model=body.model, system="Return the requested JSON with status ok.",
            user="Connectivity check only; no engineering data.",
            schema={"type": "object", "properties": {"status": {"type": "string", "enum": ["ok"]}},
                    "required": ["status"], "additionalProperties": False},
            purpose="connectivity_test", org_id=principal.org_id, project_id=None, max_tokens=256, timeout=30)
    except (ModelUnavailable, BudgetExhausted) as exc:
        record_health(body.model, False, str(exc))
    return {"model": body.model, **model_health(body.model)}


class DevTokenIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    name: str | None = None
    org_name: str = "Spartan Controls (dev)"
    role: str = "admin"


class SessionExchangeIn(BaseModel):
    subject: str = Field(min_length=1, max_length=180, pattern=r"^user_[A-Za-z0-9]+$")
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    name: str = Field(min_length=1, max_length=200)


@router.post("/auth/session")
def exchange_session(body: SessionExchangeIn, x_session_exchange: Annotated[str | None, Header()] = None) -> dict:
    """Trusted frontend server only, after Clerk validates identity and email.

    Never accepts a role or organization supplied by the browser. Existing grants are
    preserved; new identities get an isolated workspace. No email-only account linking.
    """
    settings = get_settings()
    secret = settings.session_exchange_secret
    if not secret or len(secret) < 32:
        raise HTTPException(503, "Session exchange is not configured")
    if not x_session_exchange or not secrets.compare_digest(secret, x_session_exchange):
        raise HTTPException(401, "Invalid session exchange credential")
    if settings.auth_backend not in ("dev", "session"):
        raise HTTPException(409, "Session exchange requires the signed-session authentication backend")
    if settings.environment == "production" and (settings.auth_dev_secret.startswith("change-me") or len(settings.auth_dev_secret) < 32):
        raise HTTPException(503, "Configure a strong production session signing key")
    with scoped_session(None) as s:
        # Serialize first-login provisioning for this subject across API processes.
        s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:subject))"), {"subject": body.subject})
        user = s.execute(select(User).where(User.external_subject == body.subject)).scalars().first()
        if user is None:
            existing = s.execute(select(User).where(User.email == body.email)).scalars().first()
            if existing:
                raise HTTPException(409, "This email belongs to an existing identity; ask an administrator to link accounts")
            user = User(email=body.email, name=body.name, external_subject=body.subject)
            s.add(user)
            s.flush()
            org = Organization(name=f"{body.name[:150]}'s workspace")
            s.add(org)
            s.flush()
            s.add(Membership(org_id=org.id, user_id=user.id, role="admin"))
        membership = s.execute(select(Membership).where(Membership.user_id == user.id)).scalars().first()
        if membership is None:
            raise HTTPException(403, "Account has no workspace membership")
        s.commit()
        return {"token": issue_dev_token(user.id, user.email, ttl_seconds=3600), "user_id": str(user.id),
                "org_id": str(membership.org_id), "role": membership.role}


@router.post("/auth/dev-token")
def dev_token(body: DevTokenIn) -> dict:
    """Development-only: provisions the user (and a dev org) and returns a signed token.
    Disabled unless AUTH_BACKEND=dev."""
    s_ = get_settings()
    if s_.auth_backend != "dev" or s_.environment == "production":
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
