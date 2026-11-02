# Plant Memory

An engineering change-assessment workspace: ingest plant records, freeze a document snapshot,
trace equipment dependencies, surface contradictions, draft a work scope and estimate, and
prepare a source-linked review package. AI can select investigation tools and explain a report;
deterministic code owns the findings, numerical calculations, and package validation.

This is an independent synthetic-data demonstration, not a Spartan Controls product or a
commissioned control-system tool. It never connects to or writes to live plant equipment.

## Run locally

Requirements: Python 3.12+, Node 24+, pnpm 10.11, Docker (or an equivalent PostgreSQL 16
installation with pgvector and the roles in `infra/docker/postgres-init/01-roles.sql`).

```sh
cp .env.example .env
docker compose up -d postgres valkey
python3.12 -m venv .venv
.venv/bin/pip install -e './packages/synthetic-data' -e './services/api[dev]'
pnpm install --frozen-lockfile
cd services/api
../../.venv/bin/alembic upgrade head
cd ../..
```

Do not overwrite an existing `.env`. For the web app, copy `apps/web/.env.example` to
`apps/web/.env.local` if it does not exist and configure the existing Clerk sign-in integration.
Local developer sign-in is also available. For production, set the same strong
`SESSION_EXCHANGE_SECRET` on the frontend server and API, use `AUTH_BACKEND=session`, and set
a strong `AUTH_DEV_SECRET` (the legacy variable name for the session-signing key). Clerk verifies
the user and primary email; the server exchange creates an isolated workspace for a new
identity and preserves existing grants. Development login is disabled in production.

Run these in separate terminals from the repository root:

```sh
.venv/bin/uvicorn plant_memory.main:app --host 127.0.0.1 --port 8000 --reload
.venv/bin/python -m plant_memory.worker
pnpm dev:web
```

Open http://localhost:3000. Sign in using the local demo engineer, open the seeded pumping
station, and choose **Investigation**. No AI key is required for deterministic mode.

If no demo project exists:

```sh
.venv/bin/python -m pm_synth.cli generate --out packages/synthetic-data/out --only v02
.venv/bin/python -m plant_memory.cli seed-demo --variant v02
```

## Connect Claude and GPT

Set `AI_GATEWAY_API_KEY` in the root `.env` on the API server, then restart the API and worker.
Never place this key in a `NEXT_PUBLIC_` variable or commit it. A key with funded access is
required for real inference. A configured key alone is not evidence of a successful connection.

The model catalog was checked on 2026-11-02. The initial approved set is:

- `anthropic/claude-haiku-5.5` (extraction default)
- `anthropic/claude-sonnet-5.5` (investigation default)
- `anthropic/claude-opus-5.5` (selectable higher-capability model)
- `openai/gpt-6-astra` (selectable GPT model)

Model IDs are configurable through `MODEL_FAST`, `MODEL_REASONING`, `MODEL_ESCALATION`, and
the JSON array `MODEL_ALTERNATIVES`. Verify IDs against the live catalog rather than guessing
names such as “Cloud Astra.” The investigation dropdown pins the selected model to the run.
Models are never silently substituted. A deterministic fallback is explicitly labelled.

```sh
.venv/bin/python scripts/check_models.py
# Optional: one paid connectivity request, when credentials are configured:
.venv/bin/python scripts/check_models.py --live --model openai/gpt-6-astra
```

On a report, **Ask about this report** sends its bounded evidence packet and your question to
the selected model. Source IDs are validated against the supplied evidence. Results are
persisted separately as analysis events; they do not change findings or approve the report.
A valid citation ID does not prove semantic support: inspect the cited source before relying
on a generated claim. Stale reports cannot receive new AI analyses.

## Verify

```sh
.venv/bin/pytest services/api/tests -q
# Requires the local database and generated v02 fixtures; creates labelled synthetic test data:
PM_RUN_INTEGRATION=1 .venv/bin/pytest services/api/tests -q
pnpm test
pnpm --filter @plant-memory/web typecheck
pnpm --filter @plant-memory/web lint
pnpm --filter @plant-memory/web build
```

Integration tests use scripted model doubles, not paid inference. They verify ingestion,
report generation, exports, tenant boundaries, model selection, fallback, and citation checks.

## Architecture and limits

- Next.js/React frontend with an evidence drawer, relationship graph, run progress, and review UI.
- FastAPI/Python service and PostgreSQL with project-scoped row-level security.
- Versioned evidence, immutable document snapshots, deterministic rules, Decimal estimates.
- Bounded in-process tool-calling agent through Vercel AI Gateway's compatible HTTP API.
- Separate ingestion worker; optional OCR and real embeddings need the extraction extras.
- Human review is stored with the report. Reports retain their original snapshot; review status
  and embedded review fields are updated by the existing review workflow.

The configured dollar guards check recorded spend between calls; they are not atomic billing
reservations and cannot guarantee a hard cap under concurrent calls or missing cost metadata.
Configure a provider-side budget as well. The current agent driver uses process-local threads;
use a single API worker for the demo. Multi-replica durable execution needs a job lease/worker
design before production. The external `eve` adapter is an existing stub path; no eve service
is included. Use `gateway` or `local`.

See [engineering notes](docs/BUILD_NOTES.md), [demo walkthrough](docs/DEMO.md), and
[deployment handoff](docs/DEPLOYMENT.md).
