"""FastAPI dependencies: resolve the caller, open a tenant-scoped DB session, enforce roles."""

from __future__ import annotations

import uuid
from typing import Annotated, Iterator

import jwt
from fastapi import Depends, Header, HTTPException, Path, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Membership, Project, ProjectMember, Run, User
from ..db.session import TenantScope, scoped_session
from .principal import Principal
from .tokens import verify_agent_token, verify_user_token


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    return authorization.split(" ", 1)[1].strip()


def _load_user_principal(claims: dict) -> Principal:
    subject = claims.get("sub")
    email = claims.get("email")
    # Identity tables carry no tenant RLS, so the runtime role can read them unscoped.
    with scoped_session(None) as s:
        user = None
        if subject:
            user = s.execute(select(User).where((User.external_subject == subject) | (User.id == _as_uuid(subject)))).scalars().first()
        if user is None and email:
            user = s.execute(select(User).where(User.email == email)).scalars().first()
        if user is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "user is not provisioned")
        membership = s.execute(select(Membership).where(Membership.user_id == user.id)).scalars().first()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "user has no organization")
        grants = s.execute(select(ProjectMember).where(ProjectMember.user_id == user.id, ProjectMember.org_id == membership.org_id)).scalars().all()
        project_roles = {g.project_id: g.role for g in grants}
        return Principal(user.id, membership.org_id, user.email, user.name, membership.role, project_roles)


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


def current_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    token = _bearer(authorization)
    try:
        claims = verify_user_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc
    return _load_user_principal(claims)


def service_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    """Caller is the agent runtime acting for exactly one run. Scope is the run's project only."""
    token = _bearer(authorization)
    try:
        claims = verify_agent_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid agent token: {exc}") from exc
    run_id = uuid.UUID(claims["run_id"])
    org_id = uuid.UUID(claims["org_id"])
    project_id = uuid.UUID(claims["project_id"])
    user_id = uuid.UUID(claims["user_id"])
    with scoped_session(TenantScope(org_id, (project_id,))) as s:
        run = s.get(Run, run_id)
        if run is None or run.project_id != project_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "run not accessible")
        if run.state in ("completed", "failed", "cancelled", "incomplete"):
            raise HTTPException(status.HTTP_409_CONFLICT, f"run is {run.state}")
    return Principal(user_id, org_id, "agent@plant-memory.local", "Plant Memory agent", "analyst", {project_id: "analyst"}, kind="service", run_id=run_id)


PrincipalDep = Annotated[Principal, Depends(current_principal)]
ServicePrincipalDep = Annotated[Principal, Depends(service_principal)]


def db_for(principal: Principal) -> Iterator[Session]:
    """Org admins are authorized for every project in the organization. Row-level security
    only sees the project ids written into the session, so include those ids explicitly.
    The '*' setting is reserved for the projects table and does not satisfy tenant-table checks.
    """
    project_ids = principal.project_ids
    if principal.org_role == "admin" and principal.kind == "user":
        with scoped_session(TenantScope(principal.org_id, all_projects=True)) as lookup:
            project_ids = tuple(lookup.execute(select(Project.id).where(Project.org_id == principal.org_id)).scalars())
    scope = TenantScope(principal.org_id, project_ids)
    with scoped_session(scope) as s:
        yield s


def db_session(principal: PrincipalDep) -> Iterator[Session]:
    yield from db_for(principal)


def service_db_session(principal: ServicePrincipalDep) -> Iterator[Session]:
    yield from db_for(principal)


DbDep = Annotated[Session, Depends(db_session)]
ServiceDbDep = Annotated[Session, Depends(service_db_session)]


def require_project_role(minimum: str):
    def dep(project_id: Annotated[uuid.UUID, Path()], principal: PrincipalDep) -> Principal:
        if not principal.has_role(project_id, minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires {minimum} role on project")
        return principal

    return dep


def assert_role(principal: Principal, project_id: uuid.UUID, minimum: str) -> None:
    if not principal.has_role(project_id, minimum):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires {minimum} role on project")


def idempotency_key(request: Request, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str | None:
    return idempotency_key
