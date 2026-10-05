import json
from pathlib import Path

from app.design_assessment.assessor import assess_control_design, rating_label
from app.gap_drafting.drafter import draft_gaps
from app.pilot.validation import validate_manifest
from app.question_generation.generator import generate_walkthrough_questions
from app.schemas.racm import AssessmentResult, Control, ControlDocumentation, DocumentedAttribute, Risk
from app.transcript_extraction.extractor import extract_control_documentation
from app.transcript_extraction.parser import parse_transcript_text
from app.validation import merge_control_section, validate_record

PILOT_DIR = Path(__file__).resolve().parents[2] / "pilot"


def _attr(value: str) -> DocumentedAttribute:
    return DocumentedAttribute(value=value, source_references=[])


def control_with_documentation(**doc_overrides) -> Control:
    """doc_overrides values should be plain strings - wrapped into real
    DocumentedAttribute objects here, since Control.model_copy(update=...)
    does not validate/coerce raw dicts into the actual model."""
    attrs = {field: _attr(value) for field, value in doc_overrides.items()}
    control = Control(
        control_id="CTRL-001",
        control_title="Test Control",
        risk=Risk(risk_id="R-1", risk_description="Unauthorized changes could be deployed without review."),
        control_objective="Changes are reviewed by an individual independent of the person who made them, before deployment.",
    )
    return control.model_copy(update={"documentation": ControlDocumentation(**attrs)})


def fully_documented_aligned_control() -> Control:
    return control_with_documentation(
        what="Changes are reviewed before deployment.",
        who="A second engineer reviews the change.",
        when="Before every deployment.",
        why="To make sure changes are reviewed by an individual independent of the person who made them before deployment.",
        where="In the change management tool.",
        how="The reviewer checks the diff and approves it.",
    )


def with_who(control: Control, who_value: str) -> Control:
    return control.model_copy(
        update={"documentation": control.documentation.model_copy(update={"who": _attr(who_value)})}
    )


def pilot_control_with_real_documentation(case_id: str) -> Control:
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))
    case = next(c for c in manifest.cases if c.case_id == case_id)
    record = validate_record(json.loads((PILOT_DIR / case.racm_input_path).read_text(encoding="utf-8")))
    questions = generate_walkthrough_questions(record.control, engagement=record.engagement)
    raw = (PILOT_DIR / case.walkthrough_input_path).read_text(encoding="utf-8")
    transcript = parse_transcript_text(raw, transcript_id=f"WT-{case_id}", control_id=record.control.control_id, source_name="pilot")
    extraction = extract_control_documentation(record.control, questions, transcript)
    updated_record = merge_control_section(record, "documentation", extraction.documentation.model_dump(mode="json"))
    return updated_record.control


# ---------- Completeness ----------


def test_fully_documented_control_gets_adequate_completeness():
    control = fully_documented_aligned_control()
    design = assess_control_design(control)
    assert design.completeness.result == AssessmentResult.PASS
    assert rating_label(design.completeness.result) == "Adequate"


def test_bare_control_gets_inadequate_completeness():
    control = control_with_documentation()  # nothing filled in
    design = assess_control_design(control)
    assert design.completeness.result == AssessmentResult.FAIL
    assert rating_label(design.completeness.result) == "Inadequate"
    assert "0 of 6" in design.completeness.rationale


def test_partially_documented_control_requires_human_review():
    control = control_with_documentation(
        what="Something happens.",
        who="Someone does it.",
        when="Monthly.",
        why="To manage risk.",
    )
    design = assess_control_design(control)
    assert design.completeness.result == AssessmentResult.PARTIAL
    assert rating_label(design.completeness.result) == "Requires Human Review"


# ---------- Incomplete documentation -> overall UNKNOWN, never guessed ----------


def test_incomplete_documentation_never_concludes_adequate_or_inadequate():
    control = control_with_documentation(what="Something happens.")
    design = assess_control_design(control)
    assert design.first_pass_design_conclusion == AssessmentResult.UNKNOWN
    assert rating_label(design.first_pass_design_conclusion) == "Requires Human Review"
    assert design.relevance.result == AssessmentResult.UNKNOWN
    assert design.risk_objective_control_alignment.result == AssessmentResult.UNKNOWN


# ---------- Independence / segregation-of-duties conflict ----------


def test_self_review_conflict_is_detected_as_inadequate():
    control = with_who(fully_documented_aligned_control(), "I'm also the one who approves my own changes.")
    design = assess_control_design(control)
    assert design.risk_objective_control_alignment.result == AssessmentResult.FAIL
    assert design.first_pass_design_conclusion == AssessmentResult.FAIL
    assert rating_label(design.first_pass_design_conclusion) == "Inadequate"
    assert "independence" in design.conclusion_rationale.lower()


def test_independence_check_only_fires_when_objective_actually_requires_it():
    """No independence requirement in the objective/risk -> the self-review
    phrase alone must not trigger a FAIL; this is a targeted check, not a
    generic penalty for first-person phrasing."""
    control = Control(
        control_id="CTRL-002",
        control_title="Test Control",
        risk=Risk(risk_id="R-1", risk_description="Reports could contain errors."),
        control_objective="Reports are reviewed for accuracy before distribution.",
    )
    attrs = {
        "what": _attr("The report is checked."),
        "who": _attr("I'm also the one who prepares it."),
        "when": _attr("Monthly."),
        "why": _attr("Reports are reviewed for accuracy before distribution."),
        "where": _attr("In the shared drive."),
        "how": _attr("Checked line by line."),
    }
    control = control.model_copy(update={"documentation": ControlDocumentation(**attrs)})
    design = assess_control_design(control)
    assert design.risk_objective_control_alignment.result != AssessmentResult.FAIL


# ---------- Adequate end-to-end ----------


def test_fully_documented_aligned_control_is_adequate_overall():
    control = fully_documented_aligned_control()
    design = assess_control_design(control)
    assert design.first_pass_design_conclusion == AssessmentResult.PASS
    assert rating_label(design.first_pass_design_conclusion) == "Adequate"


# ---------- Gap drafting ----------


def test_no_gap_drafted_for_adequate_or_review_conclusions():
    control = fully_documented_aligned_control()
    design = assess_control_design(control)
    assert draft_gaps(control, design).gaps == []

    incomplete_control = control_with_documentation()
    incomplete_design = assess_control_design(incomplete_control)
    assert draft_gaps(incomplete_control, incomplete_design).gaps == []


def test_gap_is_drafted_only_for_inadequate_conclusion_with_full_field_mapping():
    control = with_who(fully_documented_aligned_control(), "I'm also the one who approves my own changes.")
    design = assess_control_design(control)
    gaps = draft_gaps(control, design)
    assert len(gaps.gaps) == 1
    gap = gaps.gaps[0]
    assert gap.gap_title  # Gap Title
    assert gap.gap_description  # Observation
    assert gap.root_cause_category  # Root Cause
    assert gap.recommendation  # Recommendation
    # Risk is reused from the control, not duplicated onto Gap.
    assert control.risk.risk_description


# ---------- Pilot fixtures: real end-to-end behaviour ----------


def test_well_documented_pilot_control_is_adequate_with_no_gaps():
    control = pilot_control_with_real_documentation("well_documented")
    design = assess_control_design(control)
    gaps = draft_gaps(control, design)
    assert design.first_pass_design_conclusion == AssessmentResult.PASS
    assert gaps.gaps == []


def test_incomplete_pilot_control_requires_human_review_with_no_gaps():
    control = pilot_control_with_real_documentation("incomplete")
    design = assess_control_design(control)
    gaps = draft_gaps(control, design)
    assert design.first_pass_design_conclusion == AssessmentResult.UNKNOWN
    assert gaps.gaps == []


def test_design_issue_pilot_control_is_inadequate_with_one_independence_gap():
    control = pilot_control_with_real_documentation("design_issue")
    design = assess_control_design(control)
    gaps = draft_gaps(control, design)
    assert design.first_pass_design_conclusion == AssessmentResult.FAIL
    assert len(gaps.gaps) == 1
    assert "independence" in gaps.gaps[0].gap_title.lower()


def test_insufficient_information_pilot_control_requires_human_review_with_no_gaps():
    control = pilot_control_with_real_documentation("insufficient_information")
    design = assess_control_design(control)
    gaps = draft_gaps(control, design)
    assert design.first_pass_design_conclusion == AssessmentResult.UNKNOWN
    assert gaps.gaps == []


def test_assessment_never_reads_the_transcript_directly():
    """Boundary check: assess_control_design's signature only accepts a
    Control - there is no way for it to access the raw transcript, only the
    already-extracted documentation."""
    import inspect

    sig = inspect.signature(assess_control_design)
    assert list(sig.parameters) == ["control"]
