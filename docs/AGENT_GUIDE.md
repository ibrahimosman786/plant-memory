# Using and specializing Plant Memory

## Current status

The local database, document pipeline and deterministic investigation/report workflow are tested.
Live Claude/GPT inference is blocked by Vercel `customer_verification_required` (November 2).
A saved key is not proof of access. The status card now shows a cached actual connection result
for the default model, expiring after 15 minutes. Use **Check AI connection** after completing
Vercel account verification; this sends one small paid-model request. Each run records its own
chosen model, whether inference succeeded, and any deterministic fallback reason.

## Open the agent

1. Open http://localhost:3000/login and use the local demo engineer login for the seeded data.
2. Open the pumping-station project, then **Investigate**.
3. Select an ingested document snapshot, enter the change request and equipment tags, choose
   gateway mode and a model, and start the investigation.
4. Follow tool events and any clarification request. Open the resulting report and inspect its sources.
5. Use the report AI analysis panel to ask questions about that report's evidence. It needs a
   functioning gateway; it does not silently pretend a rules-based answer is AI analysis.

Example request: “Investigate replacing CP-101. Identify affected equipment, conflicting range
specifications, missing evidence, required work and verification steps. Cite source records and
leave unresolved questions for an engineer.”

## What data can it access?

Upload documents, let ingestion finish, then create/select a snapshot. The model is given typed
tools that operate within that authorized project and snapshot. It can list documents/equipment
with `get_snapshot_inventory`, search evidence, read source spans, resolve tags, trace dependencies,
run consistency checks, and draft work, estimates and checklists. It gets tool results, not database
credentials. New revisions require a new snapshot; they do not silently change an existing run.

This is a scoped investigation workflow and report-analysis interface, not a general chat over
all company systems. It has no connection to Spartan's internal data, PLCs or live plant controls.
Report analysis receives a bounded subset of the report evidence; its returned limitations should
make omissions explicit. Inventory pagination is available; retrieval is not a guarantee that the
model has examined every source. Verify coverage when a decision depends on completeness.

## Specialization

The editable investigation system prompt is `services/api/plant_memory/prompts/investigation.txt`.
It directs the model to stay within industrial change investigations, retrieve evidence, preserve
source IDs, expose conflicts and gaps, redirect unrelated requests, and treat document text as
untrusted data. Restart/reload the API after changing it.

A useful instruction is: “Use only the selected snapshot as evidence. Retrieve before making
claims. If the evidence is missing or contradictory, say so and ask a precise question. Never
invent equipment, costs or citations. Produce a draft for engineer review.”

A prompt alone cannot guarantee grounding. Project permissions and snapshot filters constrain
access; validated tool inputs constrain actions; structured outputs and citation membership checks
catch some unsupported output; deterministic tools handle engineering checks and arithmetic.
Citation membership proves a cited record exists, not that it logically supports the claim.
Human review remains required. The agent cannot approve its own engineering package.

## Design choices and alternatives

- Retrieval rather than placing the entire database into a prompt: smaller context, source-level
  traceability and enforced scope. Tradeoff: retrieval can miss relevant evidence; use inventory,
  targeted queries and evaluation cases to measure coverage.
- Model orchestration plus deterministic engineering tools: repeatable calculations and checks,
  with flexible evidence interpretation. A rules-only mode remains useful during provider outages,
  but is explicitly labelled and has narrower capabilities.
- Frozen snapshots rather than always reading the newest records: reproducible reports and clear
  stale-report detection. Users must ingest revisions and deliberately run again.
- Approved model selection rather than hard-coded one-provider behavior: compare models using the
  same fixtures and outputs. Catalog presence does not guarantee account access or answer quality.
- For production: durable job execution, hosted authentication verification, atomic spending limits,
  backups and measured retrieval/answer quality still need deployment-specific work.
