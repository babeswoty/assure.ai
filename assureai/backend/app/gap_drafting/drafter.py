"""Deterministic, rules-based gap drafting (Prompt 4: "Gap Drafting Agent").

Reads a control's design assessment conclusion and, only when it found a
specific, evidence-backed design flaw (first_pass_design_conclusion ==
FAIL), drafts a Gap describing it. Never drafts a gap from a "Requires
Human Review" (UNKNOWN) conclusion - an unresolved question is not a
confirmed gap, and turning "we couldn't tell" into a gap would itself be a
fabrication.

Output fields, mapped onto the EXISTING Gap model (no new/redundant fields
added):
    Gap Title     -> gap_title
    Observation   -> gap_description (what was actually observed/found)
    Risk          -> control.risk.risk_description (already linked at the
                     control level - reused as-is, not duplicated onto Gap)
    Root Cause    -> root_cause_category
    Recommendation -> recommendation

Boundary (v1): only drafts a gap for the specific, structurally-detectable
design flaw app.design_assessment can currently find (an independence /
segregation-of-duties conflict). It does NOT attempt to infer an
OPERATING-effectiveness gap from free-text documentation (e.g. "4 of 6
approvals are still open") - recognising that kind of gap requires real
language understanding of arbitrary prose, which is deliberately out of
scope for this deterministic v1. See the pilot fixture
`potential_gap/expected_reference.json`'s `expected_gap_indicator` - that
exact scenario is documented future work, not something this agent claims
to catch today.
"""
from app.schemas.racm import (
    AssessmentResult,
    Control,
    DesignAssessment,
    Gap,
    GapAssessment,
    GapImpact,
    RemediationAlignment,
)
from app.schemas.racm import GapType

_INDEPENDENCE_PHRASE = "independen"


def draft_gaps(control: Control, design_assessment: DesignAssessment) -> GapAssessment:
    if design_assessment.first_pass_design_conclusion != AssessmentResult.FAIL:
        return GapAssessment(gaps=[])

    failed_dimensions = [
        (name, dimension)
        for name, dimension in (
            ("relevance", design_assessment.relevance),
            ("risk/objective/control alignment", design_assessment.risk_objective_control_alignment),
        )
        if dimension.result == AssessmentResult.FAIL
    ]
    if not failed_dimensions:
        # The overall conclusion says FAIL but no dimension actually failed -
        # should not happen given how assess_control_design builds its
        # conclusion, but never draft a gap without a specific failed
        # dimension's rationale to point to.
        return GapAssessment(gaps=[])

    gaps = []
    for i, (name, dimension) in enumerate(failed_dimensions, start=1):
        is_independence_issue = _INDEPENDENCE_PHRASE in dimension.rationale.lower()
        gaps.append(
            Gap(
                gap_id=f"{control.control_id}-GAP-{i:02d}",
                gap_type=GapType.DESIGN_GAP,
                gap_title=(
                    "Lack of independence between control roles"
                    if is_independence_issue
                    else f"Design deficiency identified in {name}"
                ),
                gap_description=dimension.rationale,
                root_cause_category="Segregation of duties" if is_independence_issue else None,
                impact=GapImpact.UNKNOWN,
                recommendation=(
                    "Assign the review/approval responsibility to an individual independent of "
                    "whoever initiates or performs the underlying activity."
                    if is_independence_issue
                    else "Reviewer judgement required to determine an appropriate remediation."
                ),
                action_addresses_gap=RemediationAlignment.NOT_ASSESSED,
            )
        )
    return GapAssessment(gaps=gaps)
