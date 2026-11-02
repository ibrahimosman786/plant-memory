# Build notes: actual issues and fixes

These notes distinguish pre-existing capabilities from this implementation pass. Plant Memory
already had ingestion, SQL models, deterministic engineering tools, reports and a basic agent.
This pass extended model integration, report interpretation, reliability and verification.

| Observed problem | Change made | Evidence / practical limit |
| --- | --- | --- |
| No GPT selection in the investigation UI; agent read the global default instead of a per-run choice | Added an approved model set, API validation, dropdown and frozen run model | Scripted agent integration checks the GPT ID on every turn |
| Marketing/model names were ambiguous | Queried Vercel's live `/v1/models` and used exact returned IDs | Catalog availability does not establish funded account access |
| A configured key was described as a connected model | Added an authenticated connection test and cached health state; runs also record actual inference success | Live check now correctly shows the Vercel account verification block |
| Tool summaries removed source text, citation IDs and work-item IDs before the model saw them | Preserve structured tool data, bound complete values and mark truncation; add snapshot inventory pagination | Regression tests verify usable evidence/work IDs, valid bounded JSON and inventory scope |
| JSON parsing did not enforce the response schema | Added JSON Schema validation and rejected refused, truncated and malformed responses | Unit tests cover malformed payloads, wrong types and provider errors |
| No report question/answer workflow | Added bounded evidence context, structured claims, persisted analysis history and source buttons | Server validates citation membership; a human still checks whether the source supports the statement |
| Cancellation could remain stale in a long-lived ORM session | Refresh the cancellation flag before model turns and tools, and after a model returns | Cancellation does not abort an HTTP request already sent |
| Token/deadline checks did not happen before each model turn | Added pre-call checks and bounded output/timeout settings | Monetary limits remain best-effort, not atomic reservations |
| Invalid tool arguments could fail the entire investigation | Return argument-validation feedback to the model within the bounded loop | Non-input failures still terminate or mark the package incomplete |
| A failed consistency tool could be marked as completed | Failed tools now remain incomplete and successful retries clear failure status | Regression tests verify the state transition |
| Equipment-by-ID lookup checked project but not document snapshot | Added the frozen-version predicate to that lookup | Integration test uploads a future revision and rejects its equipment from the old snapshot |
| Backend had no test suite | Added gateway, grounding and full-flow integration tests | Model doubles are labelled; they do not prove live provider compatibility |
| Existing React lint failures in graph selection and session initialization | Removed derived-state effect and made session hydration asynchronous with cleanup | Frontend lint and production build verification |
| Seed CLI printed a bearer token | Removed the token from CLI output | Project/snapshot IDs remain useful without exposing credentials |
| Development token route could run when environment was production | Disabled developer token issuance in production; added a server-authenticated Clerk session exchange with isolated new workspaces | Tests cover rejected credentials, weak production signing keys and separate workspaces; real hosted Clerk login still needs deployment verification |
| Live provider calls returned HTTP 403 | Read the gateway error and surfaced `customer_verification_required` as an actionable message | Vercel requires a payment card on file; account verification must be completed by the owner |

## A truthful interview explanation

“I extended a working engineering-records prototype into a model-selectable investigation and
report-analysis workflow. A major design choice was separating model interpretation from
deterministic engineering checks. I found and fixed a snapshot lookup problem, added output
validation and citation checks, and tested the upload-to-report path with synthetic data. The
remaining production work includes live-provider and hosted authentication verification and
durable execution across multiple API instances.”

Do not describe synthetic evaluation as a measured reduction in Spartan's engineering time.
Do not claim production deployment or live Claude/GPT verification unless those steps are
actually completed. No internal Spartan files or control systems were accessed.
