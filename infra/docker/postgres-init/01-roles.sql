-- Local development roles. Production roles are created by Terraform/Secrets Manager.
-- pm_admin: owns schema, runs migrations. BYPASSRLS so operator jobs (startup run-resume, org-wide
--           budget roll-ups) can see across tenants. Never used on a request path (see db/session.py).
-- pm_app:   runtime role for API and workers. Subject to row-level security (FORCE on tenant tables).
-- pm_workflow: eve workflow world. Separate database, no access to engineering records.

CREATE ROLE pm_admin LOGIN PASSWORD 'pm_admin' BYPASSRLS;
CREATE ROLE pm_app LOGIN PASSWORD 'pm_app';
CREATE ROLE pm_workflow LOGIN PASSWORD 'pm_workflow';

CREATE DATABASE plant_memory OWNER pm_admin;
CREATE DATABASE plant_memory_workflow OWNER pm_workflow;

\connect plant_memory
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
GRANT CONNECT ON DATABASE plant_memory TO pm_app;
GRANT USAGE ON SCHEMA public TO pm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE pm_admin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE pm_admin IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO pm_app;

\connect plant_memory_workflow
-- Graphile Worker (used by @workflow/world-postgres) needs pgcrypto for gen_random_uuid.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
