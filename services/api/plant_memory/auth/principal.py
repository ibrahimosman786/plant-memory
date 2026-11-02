from __future__ import annotations

import uuid
from dataclasses import dataclass, field

ROLE_ORDER = {"viewer": 0, "analyst": 1, "reviewer": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    """Authenticated caller. `project_roles` is the effective role per accessible project."""

    user_id: uuid.UUID
    org_id: uuid.UUID
    email: str
    name: str
    org_role: str
    project_roles: dict[uuid.UUID, str] = field(default_factory=dict)
    kind: str = "user"  # user | service (agent/worker acting for a run)
    run_id: uuid.UUID | None = None

    def role_for(self, project_id: uuid.UUID) -> str | None:
        if self.org_role == "admin":
            return "admin"
        return self.project_roles.get(project_id)

    def has_role(self, project_id: uuid.UUID, minimum: str) -> bool:
        role = self.role_for(project_id)
        return role is not None and ROLE_ORDER[role] >= ROLE_ORDER[minimum]

    @property
    def project_ids(self) -> tuple[uuid.UUID, ...]:
        return tuple(self.project_roles.keys())
