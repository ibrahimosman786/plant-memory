# Verification record — 2026-11-02

## Passed

- 42 Python tests covered: 41 passed in the full suite, then all 10 database integration tests passed after adding inventory pagination coverage.
- 3 shared TypeScript/JSON-schema contract tests.
- Frontend ESLint and TypeScript checks.
- Next.js production build after the connection-status UI changes.
- `git diff --check` and Python compilation.
- Credential-pattern scan found no matching credentials in tracked or unignored text files.
- Live model catalog lists all four configured model IDs.

Integration coverage includes 21 synthetic document uploads, ingestion, snapshot creation,
dependency tracing, findings, work scope, estimates, checklist, three export formats,
cross-organization access denial, citation validation, analysis persistence, stale-report
rejection, snapshot isolation, per-run GPT selection using a scripted model, deterministic
fallback, and isolated workspace provisioning through the session exchange.

## Live provider verification

GPT-6 Astra, Claude Opus 5.5 and a small Claude Haiku request reached AI Gateway but were
rejected with HTTP 403, `customer_verification_required`. Vercel requires a valid payment
card on file. No successful live model inference is claimed. The supplied credential is
stored only in the ignored root `.env`, with restrictive file permissions.

A real HTTP investigation against the existing pumping-station demo completed using six
deterministic tools after the provider rejection. Its metadata records `backend=guided`,
`model_connected=false` and the actionable billing reason.

- Run: `3814301a-2ab1-447b-b8c5-282e01c83a8f`
- Report: `5af3beba-2fc1-401a-8685-0356f3e5e6ce`
- Project: `638c1c94-32b0-4c58-b521-4453fce8901c`

## Not verified

- Live model reasoning, structured output and report interpretation after account activation.
- Browser visual interaction: the in-app browser failed to attach and exposed no usable tab.
  API integration and the production frontend build passed; those do not substitute for visual QA.
- Hosted Clerk login, deployed infrastructure and remote CI. No remote is configured in this
  checkout and no Vercel deployment was created.

Local Node was v23.10.0 during verification, while the repository requests Node 24+. The build
passed with a version warning. `.nvmrc` and CI use Node 24.

The authenticated `/v1/models/check` endpoint was exercised against the running API with
Claude Sonnet 5.5. It returned `state=blocked` and the Vercel account-verification message;
`/v1/status` returned the same cached state. Source payload preservation, bounded valid JSON
and snapshot inventory pagination have regression coverage. See AGENT_GUIDE.md for access
and specialization instructions.
