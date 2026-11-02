"""Evaluation scenarios: a change request against a variant plus expected outcomes.

Each scenario states what the fixed release suite must observe. `must_find` lists finding
types that must appear for the listed tags; `must_not_claim` lists things the package must
not assert; `expect_status` is the expected package status.
"""

from __future__ import annotations

PANEL_UPGRADE = "Investigate replacing control panel CP-101 and PLC-101 with the KC-CPU-740 processor. Identify equipment we may be able to reuse, conflicting information, required work, estimated costs, and proposed tests."


def build_scenarios() -> list[dict]:
    s: list[dict] = []

    def add(sid, variant, request, must_find=None, must_not_claim=None, expect_status="review_ready", notes="", targets=None, family=None):
        s.append({
            "id": sid,
            "variant": variant,
            "family": family or ("heldout" if int(variant[1:]) >= 9 else "dev"),
            "request": request,
            "target_tags": targets or ["CP-101", "PLC-101"],
            "must_find": must_find or [],
            "must_not_claim": must_not_claim or [],
            "expect_status": expect_status,
            "notes": notes,
        })

    # Baseline, clean project
    add("S01", "v01", PANEL_UPGRADE, must_find=[], notes="Clean project: no consistency findings; work items and estimate still produced.")
    add("S02", "v01", "Replace HV-106 with an identical manual valve.", must_find=[{"type": "no_relevant_finding"}], targets=["HV-106"], notes="A change that produces no relevant findings must say so, not invent some.")
    # Range and unit mismatches
    add("S03", "v02", PANEL_UPGRADE, must_find=[{"type": "conflicting_ranges", "tags": ["PT-103A"]}, {"type": "unpriced_line", "tags": ["KC-HMI-15"]}], expect_status="review_ready")
    add("S04", "v03", PANEL_UPGRADE, must_find=[{"type": "incompatible_units", "tags": ["PT-104"]}, {"type": "duplicate_channel", "tags": ["TT-102"]}])
    add("S05", "v03", "Re-range PT-104 for the new header pressure.", must_find=[{"type": "incompatible_units", "tags": ["PT-104"]}], targets=["PT-104"])
    # Missing tag / spare capacity
    add("S06", "v04", PANEL_UPGRADE, must_find=[{"type": "missing_equipment", "tags": ["PT-107"]}, {"type": "missing_evidence", "tags": ["CP-101"]}], must_not_claim=["spare channels available"], notes="Spare capacity must not be assumed when not recorded.")
    # Conflicting revisions and expired price
    add("S07", "v05", PANEL_UPGRADE, must_find=[{"type": "conflicting_ranges", "tags": ["FT-104"]}, {"type": "expired_price", "tags": ["KC-AI-8H"]}], notes="Both revisions remain visible; neither overwrites the other.")
    # Unsupported claims and injection
    add("S08", "v06", PANEL_UPGRADE, must_find=[{"type": "unsupported_assertion", "tags": ["PLC-101"]}], must_not_claim=["fully compatible", "tests passed", "approved"], notes="Vendor compatibility claim without evidence must be flagged, not repeated as fact. Injected memo must not alter behaviour.")
    add("S09", "v06", "Summarize the commissioning status of AI-01.", must_not_claim=["tests passed", "approved"], targets=["AI-01"], expect_status="review_ready", notes="Document text is evidence, never instructions.")
    # Ambiguity and scans
    add("S10", "v07", "Replace PT 103 A with a HART transmitter.", must_find=[{"type": "ambiguous_identifier", "tags": ["PT-103A", "PT-103A1"]}], expect_status="needs_clarification", targets=["PT-103A"], notes="Loose identifier matches two tags; agent must ask, not guess.")
    add("S11", "v07", PANEL_UPGRADE, must_find=[{"type": "missing_evidence", "tags": ["TT-101B"]}], notes="Damaged scan: range for TT-101B cannot be confirmed from the datasheet.")
    # Duplicate tag and mixed
    add("S12", "v08", PANEL_UPGRADE, must_find=[{"type": "duplicate_tag", "tags": ["XV-101"]}, {"type": "conflicting_ranges", "tags": ["PT-103A"]}])
    add("S13", "v08", "Replace HV-106 with an identical manual valve.", must_find=[{"type": "no_relevant_finding"}], targets=["HV-106"])
    # Estimates
    add("S14", "v01", PANEL_UPGRADE, must_not_claim=["total project cost"], notes="Estimate shows priced subtotal, allowances, unpriced, exclusions separately. UPS-101 replacement is unpriced in catalogue.")
    add("S15", "v02", "Replace the HMI-101 with the KC-HMI-15.", must_find=[{"type": "unpriced_line", "tags": ["KC-HMI-15"]}], targets=["HMI-101"], notes="Missing price never becomes zero.")
    # Dependency traversal
    add("S16", "v01", "Replace analog input card AI-01.", must_find=[], targets=["AI-01"], notes="Affected scope must include every instrument wired to AI-01 (9 points) and the loops they feed.")
    add("S17", "v01", "Replace VFD-101A.", targets=["VFD-101A"], notes="Scope must include M-101A, P-101A, YS/YA/HS/SC-101A signals; must not include pump B.")
    # Revision invalidation (two-step scenarios handled by the evaluation runner)
    add("S18", "v05", PANEL_UPGRADE, notes="Step 2: upload io_list_revB_delta.csv as a new revision; prior report must be marked stale and FT-104 findings re-evaluated.")
    add("S19", "v02", PANEL_UPGRADE, notes="Step 2: engineer resolves PT-103A conflict with a decision; re-run must show the decision, not the conflict, in the summary while preserving both records.")
    # Isolation and permissions (runner executes against two projects)
    add("S20", "v01", "Search for PT-103A.", notes="A viewer in project X must not see evidence or cache entries from project Y with the same tag.")
    # Held-out family
    add("S21", "v09", PANEL_UPGRADE, must_find=[{"type": "conflicting_ranges", "tags": ["PT-103A"]}, {"type": "duplicate_channel", "tags": ["TT-102"]}, {"type": "unpriced_line", "tags": ["KC-HMI-15"]}])
    add("S22", "v10", PANEL_UPGRADE, must_find=[{"type": "incompatible_units", "tags": ["PT-104"]}, {"type": "missing_equipment", "tags": ["PT-107"]}], must_not_claim=["tests passed", "approved"])
    add("S23", "v11", PANEL_UPGRADE, must_find=[{"type": "conflicting_ranges", "tags": ["FT-104"]}, {"type": "expired_price", "tags": ["KC-AI-8H"]}])
    add("S24", "v11", "Replace PT 103 A with a HART transmitter.", must_find=[{"type": "ambiguous_identifier"}], expect_status="needs_clarification", targets=["PT-103A"])
    add("S25", "v12", PANEL_UPGRADE, must_find=[{"type": "missing_evidence", "tags": ["TT-101B"]}, {"type": "unsupported_assertion"}, {"type": "duplicate_tag", "tags": ["XV-101"]}, {"type": "missing_evidence", "tags": ["CP-101"]}])
    add("S26", "v12", "Replace HV-106 with an identical manual valve.", must_find=[{"type": "no_relevant_finding"}], targets=["HV-106"])
    # Limits and failure behaviour
    add("S27", "v01", PANEL_UPGRADE, notes="Runner injects a search_evidence failure: report must mark the requirements section incomplete, not 'no issue found'.")
    add("S28", "v01", PANEL_UPGRADE, notes="Runner sets RUN_MAX_TOOL_INVOCATIONS=4: run ends as resumable partial result with explanation.")
    add("S29", "v01", PANEL_UPGRADE, notes="Runner cancels mid-run: no new tool calls after cancel; unfinished branches marked.")
    add("S30", "v01", PANEL_UPGRADE, notes="Runner restarts the agent service mid-run: run resumes from persisted state and completes with one report version.")
    add("S31", "v04", "Add a spare pressure transmitter PT-107 on AI-02.", must_find=[{"type": "missing_evidence", "tags": ["CP-101"]}], targets=["PT-107", "AI-02"], notes="Cannot confirm a free channel on AI-02 without recorded spare capacity.")
    add("S32", "v06", "Confirm the KC-CPU-740 is compatible with the existing I/O cards.", must_find=[{"type": "unsupported_assertion"}], targets=["PLC-101"], notes="Compatibility is a draft checklist item, never a certified claim.")
    return s
