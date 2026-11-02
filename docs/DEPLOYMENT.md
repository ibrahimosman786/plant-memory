# GitHub and Vercel handoff

The local checkout currently has no Git remote. No GitHub repository was created or pushed
in this pass. The connected Vercel account search returned no project named plant-memory.
No public deployment has been made.

## Deployment shape

The frontend can run on Vercel. The API and ingestion worker require a persistent host,
PostgreSQL/pgvector, persistent object storage, and shared queue/concurrency storage.
Do not put the current thread-based run driver into a short-lived serverless function.

Frontend Vercel settings: root directory `apps/web`, framework Next.js, Node 24, package
manager pnpm. Configure Clerk public/secret keys and `NEXT_PUBLIC_API_BASE_URL` to the
reachable HTTPS API. Set `SESSION_EXCHANGE_SECRET` only on the frontend server and API, with
the same random value of at least 32 characters. A successful frontend build alone does not
deploy the backend.

API settings: `ENVIRONMENT=production`, `AUTH_BACKEND=session`, `AUTH_DEV_SECRET` set to a
strong random signing key (legacy variable name), `SESSION_EXCHANGE_SECRET`, and
`CORS_ORIGINS` as a JSON array containing only the
frontend origin, runtime and migration database URLs with separate roles, object storage
credentials, shared queue/Valkey, `AI_GATEWAY_API_KEY`, and approved model IDs. Keep secrets
server-side. Run Alembic migrations with the migration role.

## Remaining production work

- Configure and verify the implemented Clerk session exchange on the deployed origins.
  The frontend requires a verified primary email. The API authenticates the frontend server,
  preserves existing memberships and creates separate workspaces for new identities. It does
  not automatically link accounts by email. Add project members through the admin API.
- Verify session expiration, identity suspension/revocation policy and authorization flows.
  Workspace sessions currently last one hour; Clerk logout does not immediately revoke an
  already-issued workspace token. Production revocation policy must account for this window.
- Add a durable job claim/lease before multiple API replicas; one worker process is the demo
  configuration. Startup recovery alone does not provide multi-worker execution guarantees.
- Configure provider-side spend limits. Local recorded-spend checks are not strict reservations.
- Verify live tool calls and structured outputs with each chosen model and actual credentials.
- Validate real document formats, OCR and retrieval against engineer-labelled records.
- Add deployment-specific backup, recovery, retention and monitoring policies.

GitHub CI is provided in `.github/workflows/ci.yml`. It checks Python/TypeScript contracts,
frontend lint/typechecking and the database-backed synthetic workflow. Remote CI has not run
until the repository is connected and pushed.
