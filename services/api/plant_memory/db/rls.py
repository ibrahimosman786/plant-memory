"""Row-level security DDL applied by migrations to every tenant table.

FORCE ROW LEVEL SECURITY makes the policies apply even to the table owner (the migration
role), so no application path bypasses them. The runtime role (pm_app) is not a superuser
and has no BYPASSRLS. NULLIF guards keep an unscoped transaction (empty settings) from raising
a cast error: it simply sees no rows.
"""

from __future__ import annotations

from .models import TENANT_TABLES

POLICY_SQL = """
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
  USING (
    org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
    AND project_id = ANY (string_to_array(NULLIF(NULLIF(current_setting('app.project_ids', true), ''), '*'), ',')::uuid[])
  )
  WITH CHECK (
    org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
    AND project_id = ANY (string_to_array(NULLIF(NULLIF(current_setting('app.project_ids', true), ''), '*'), ',')::uuid[])
  );
"""

# Projects are scoped by org; '*' (org admins) sees every project, otherwise only granted ids.
PROJECT_POLICY_SQL = """
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS org_isolation ON projects;
CREATE POLICY org_isolation ON projects
  USING (
    org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
    AND (
      current_setting('app.project_ids', true) = '*'
      OR id = ANY (string_to_array(NULLIF(NULLIF(current_setting('app.project_ids', true), ''), '*'), ',')::uuid[])
    )
  )
  WITH CHECK (
    org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
  );
"""


def rls_statements() -> list[str]:
    stmts = [POLICY_SQL.format(table=t) for t in TENANT_TABLES]
    stmts.append(PROJECT_POLICY_SQL)
    return stmts
