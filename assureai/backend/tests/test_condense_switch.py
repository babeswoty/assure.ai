import json
from pathlib import Path

from app.design_assessment.assessor import assess_control_design, rating_label
from app.pilot.validation import validate_manifest
from app.question_generation.generator import generate_walkthrough_questions
from app.schemas.common import SourceReference, SourceType
from app.schemas.racm import AssessmentResult, DocumentedAttribute
from app.transcript_extraction.extractor import extract_control_documentation
from app.transcript_extraction.parser import parse_transcript_text
from app.validation import merge_control_section, validate_record

from tests.test_design_assessment import fully_documented_aligned_control, with_who

PILOT_DIR = Path(__file__).resolve().parents[2] / "pilot"


def _extract(case_id: str):
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))
    case = next(c for c in manifest.cases if c.case_id == case_id)
    record = validate_record(json.loads((PILOT_DIR / case.racm_input_path).read_text(encoding="utf-8")))
    questions = generate_walkthrough_questions(record.control, engagement=record.engagement)
    raw = (PILOT_DIR / case.walkthrough_input_path).read_text(encoding="utf-8")
    transcript = parse_transcript_text(
        raw, transcript_id=f"WT-{case_id}", control_id=record.control.control_id, source_name="pilot"
    )
    return record, extract_control_documentation(record.control, questions, transcript).documentation


def test_condensing_is_on_by_default(monkeypatch):
    monkeypatch.delenv("ASSUREAI_CONDENSE")  # the product default, not the test default
    _, doc = _extract("design_issue")
    assert doc.when.value == "Quarterly"
    assert doc.where.value == "Shared Drive Folder “Access Reviews”"


def test_condensing_can_be_switched_off_to_keep_the_full_wording(monkeypatch):
    monkeypatch.setenv("ASSUREAI_CONDENSE", "0")
    _, doc = _extract("design_issue")
    assert "Last week of every quarter" in doc.when.value


def test_condensing_never_touches_the_verbatim_source_excerpts(monkeypatch):
    _, full = _extract("well_documented")
    monkeypatch.setenv("ASSUREAI_CONDENSE", "1")
    _, short = _extract("well_documented")
    assert short.who.value != full.who.value
    for field in ("what", "who", "when", "why", "where", "how"):
        assert [r.excerpt for r in getattr(short, field).source_references] == [
            r.excerpt for r in getattr(full, field).source_references
        ]


def test_the_independence_conflict_is_still_found_with_condensing_on(monkeypatch):
    monkeypatch.setenv("ASSUREAI_CONDENSE", "1")
    record, doc = _extract("design_issue")
    control = merge_control_section(record, "documentation", doc.model_dump(mode="json")).control
    design = assess_control_design(control)

    assert rating_label(design.first_pass_design_conclusion) == "Inadequate"
    assert "also the one who grants admin access" in design.conclusion_rationale


def test_the_independence_check_reads_the_verbatim_excerpt_when_the_who_value_is_just_a_role():
    """A condensed WHO such as "Engineer" no longer says the same person did both jobs;
    the interviewee's own words, kept as the source excerpt, still do."""
    control = fully_documented_aligned_control()
    who = DocumentedAttribute(
        value="Engineer",
        source_references=[
            SourceReference(
                source_id="WT-1",
                source_type=SourceType.WALKTHROUGH_TRANSCRIPT,
                source_name="t",
                locator="L04",
                excerpt="I make the change and I review it myself as well, so it is the same person.",
            )
        ],
    )
    control = control.model_copy(update={"documentation": control.documentation.model_copy(update={"who": who})})

    design = assess_control_design(control)

    assert design.risk_objective_control_alignment.result == AssessmentResult.FAIL
    assert "same person" in design.risk_objective_control_alignment.rationale


def test_a_role_only_who_with_no_self_review_evidence_is_not_flagged():
    control = with_who(fully_documented_aligned_control(), "Engineer")
    assert assess_control_design(control).risk_objective_control_alignment.result != AssessmentResult.FAIL
