# Three-minute demonstration

1. Open the seeded pumping station and show its document revisions and frozen snapshot.
2. Request: “Investigate replacing CP-101. Identify recorded dependencies, contradictions,
   work items, pricing gaps and proposed verification steps.”
3. Select a model if credentials are configured, or explicitly choose deterministic mode.
4. Follow the run's persisted events. Explain that a model may choose tools but cannot approve
   a package or create a price. Point out the model/fallback label.
5. Open the report. Inspect a range conflict and its original evidence. Show the estimate's
   unpriced lines and the distinction between a proposed check and an executed test.
6. With a live key, use “Ask about this report” and compare Claude/GPT interpretations by
   submitting the same question with each model. Treat differences as review material.
7. Export the report. Explain that uploading a new revision can mark this report stale and
   block approval until a fresh investigation is run.

If AI is unavailable, say: “This is the deterministic engineering path. The model integration
is implemented, but I am not representing a fallback run as live AI reasoning.”

Suggested follow-up evaluation: have an automation engineer label dependencies and conflicts
in representative records, then compare review time, missed issues, false positives and
unsupported claims against the current manual process.
