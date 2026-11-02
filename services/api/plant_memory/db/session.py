"""Database engine and tenant-scoped sessions.

Row-level security reads two transaction-local settings:
  app.org_id       -- the caller's organization
  app.project_ids  -- comma-separated project UUIDs the caller may access ('*' = every project in
                      the org; only valid for the projects table, used by org admins)
Both are set with transaction-local set_config inside EVERY transaction the session opens (an
`after_begin` hook re-applies them after each commit), so a pooled connection never leaks scope
and a mid-request commit never silently drops it.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings

_engine: Engine | None = None
_admin_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=10, future=True)
    return _engine


def get_admin_engine() -> Engine:
    global _admin_engine
    if _admin_engine is None:
        _admin_engine = create_engine(get_settings().database_admin_url, pool_pre_ping=True, future=True)
    return _admin_engine


@dataclass(frozen=True)
class TenantScope:
    org_id: uuid.UUID
    project_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)
    all_projects: bool = False  # org-admin view of the projects table only

    def as_settings(self) -> dict[str, str]:
        return {
            "app.org_id": str(self.org_id),
            "app.project_ids": "*" if self.all_projects else ",".join(str(p) for p in self.project_ids),
        }


def _apply(conn, scope: TenantScope | None) -> None:
    if scope is None:
        conn.execute(text("SELECT set_config('app.org_id', '', true)"))
        conn.execute(text("SELECT set_config('app.project_ids', '', true)"))
        return
    for key, value in scope.as_settings().items():
        conn.execute(text("SELECT set_config(:k, :v, true)"), {"k": key, "v": value})


def apply_scope(session: Session, scope: TenantScope | None) -> None:
    """Apply RLS settings to the current transaction (kept for callers that manage transactions)."""
    _apply(session.connection(), scope)


SessionLocal = sessionmaker(class_=Session, expire_on_commit=False, future=True)


@contextmanager
def scoped_session(scope: TenantScope | None, *, admin: bool = False) -> Iterator[Session]:
    """A session every transaction of which carries the tenant scope.

    `admin=True` uses the migration role (table owner) and is restricted to bootstrap
    operations such as creating organizations and users — never request handling.
    """
    engine = get_admin_engine() if admin else get_engine()
    session = SessionLocal(bind=engine)

    def _after_begin(sess, transaction, connection):
        _apply(connection, scope)

    event.listen(session, "after_begin", _after_begin)
    try:
        session.begin()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        event.remove(session, "after_begin", _after_begin)
        session.close()
