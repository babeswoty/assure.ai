import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.pilot.validation import validate_manifest
from app.question_generation.generator import generate_walkthrough_questions
from app.schemas.racm import Control, Risk
from app.transcript_extraction.extractor import extract_control_documentation
from app.transcript_extraction.models import Transcript, TranscriptSegment
from app.transcript_extraction.parser import parse_line_tagged_transcript
from app.validation import validate_record

PILOT_DIR = Path(__file__).resolve().parents[2] / "pilot"


def minimal_control(**overrides) -> Control:
    data = {
        "control_id": "CTRL-001",
        "control_title": "Monthly Bank Reconciliation Review",
        "risk": Risk(risk_id="R-1", risk_description="Errors in cash balances could go undetected."),
        "control_objective": "The Finance Manager reviews the monthly bank reconciliation prepared by the accountant.",
    }
    data.update(overrides)
    return Control(**data)


def transcript_from_lines(control_id: str, lines: list[str], transcript_id: str = "WT-TEST-01") -> Transcript:
    raw = "\n".join(f"[L{i:02d}] {line}" for i, line in enumerate(lines, start=1))
    return parse_line_tagged_transcript(raw, transcript_id=transcript_id, control_id=control_id, source_name="test transcript")


def load_pilot_case(case_id: str):
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))
    case = next(c for c in manifest.cases if c.case_id == case_id)
    record = validate_record(json.loads((PILOT_DIR / case.racm_input_path).read_text(encoding="utf-8")))
    raw = (PILOT_DIR / case.walkthrough_input_path).read_text(encoding="utf-8")
    transcript = parse_line_tagged_transcript(
        raw, transcript_id=f"WT-{case_id}", control_id=record.control.control_id, source_name="pilot fixture"
    )
    questions = generate_walkthrough_questions(record.control, engagement=record.engagement)
    return record, questions, transcript


# ---------- 1. Valid transcript links to the correct control ----------


def test_transcript_links_to_correct_control_via_control_id():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        [
            "Interviewer: Who performs the review?",
            "Interviewee: The Finance Manager reviews it.",
        ],
    )
    result = extract_control_documentation(control, questions, transcript)
    assert result.control_id == control.control_id
    assert result.transcript_id == transcript.transcript_id


def test_mismatched_control_id_across_inputs_is_rejected():
    control = minimal_control(control_id="CTRL-001")
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines("CTRL-999", ["Interviewer: Who performs this?", "Interviewee: Someone."])
    with pytest.raises(ValueError):
        extract_control_documentation(control, questions, transcript)


# ---------- 2 & 3. Supported values extracted, with source references ----------


def test_supported_values_are_extracted_with_source_references():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        [
            "Interviewer: Can you walk me through how the reconciliation review happens?",
            "Interviewee: The accountant prepares the reconciliation and the Finance Manager reviews it.",
            "Interviewer: Who performs the review?",
            "Interviewee: The Finance Manager reviews it each time.",
            "Interviewer: How often does this happen?",
            "Interviewee: Every month, after the bank statement is received.",
            "Interviewer: Why is this review performed?",
            "Interviewee: To catch posting errors before the books are closed.",
            "Interviewer: Where is this recorded?",
            "Interviewee: In the shared finance drive, in the monthly close folder.",
            "Interviewer: How exactly is the review carried out?",
            "Interviewee: The Finance Manager checks every reconciling item against supporting bank statements.",
        ],
    )
    result = extract_control_documentation(control, questions, transcript)
    doc = result.documentation

    assert doc.what.value is not None and doc.what.source_references
    assert doc.who.value is not None and doc.who.source_references
    assert doc.when.value is not None and doc.when.source_references
    assert doc.why.value is not None and doc.why.source_references
    assert doc.where.value is not None and doc.where.source_references
    assert doc.how.value is not None and doc.how.source_references

    for attr_name in ("what", "who", "when", "why", "where", "how"):
        attr = getattr(doc, attr_name)
        for ref in attr.source_references:
            assert ref.source_id == transcript.transcript_id
            assert ref.locator is not None


def test_no_source_references_when_value_is_unresolved():
    """Mirrors the invariant already enforced on ExpectedReference fixtures:
    never cite support for a fact that was never determined."""
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        ["Interviewer: What happens during this control?", "Interviewee: Not sure, I've never actually done it."],
    )
    result = extract_control_documentation(control, questions, transcript)
    for attr_name in ("who", "when", "why", "where", "how"):
        attr = getattr(result.documentation, attr_name)
        if attr.value is None:
            assert attr.source_references == []


# ---------- 4/5/6. Missing performer/frequency/system -> no invented fact ----------


def test_missing_performer_does_not_invent_a_person():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        [
            "Interviewer: What happens during this control?",
            "Interviewee: The reconciliation gets reviewed before month end.",
        ],
    )
    result = extract_control_documentation(control, questions, transcript)
    assert result.documentation.who.value is None
    who_missing = next(m for m in result.documentation.missing_information if m.field == "documentation.who")
    # The follow_up_question legitimately echoes the control's own real
    # title/objective (reused from the stage-1 generated question, per
    # design - see _primary_question_text) - that's accurate context, not
    # an invented fact, so it's excluded from this check. The extracted
    # VALUE and the system-authored REASON are what must never contain a
    # fabricated name.
    for name in ("Finance Manager", "Accountant", "Controller"):
        assert name not in (result.documentation.who.value or "")
        assert name not in who_missing.reason


def test_missing_frequency_does_not_invent_one():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        ["Interviewer: Who performs the review?", "Interviewee: The Finance Manager does."],
    )
    result = extract_control_documentation(control, questions, transcript)
    assert result.documentation.when.value is None
    when_missing = next(m for m in result.documentation.missing_information if m.field == "documentation.when")
    # Same exclusion as above: follow_up_question may legitimately echo the
    # control's own title (which happens to contain "monthly" in this test
    # fixture) - check the extracted value and system-authored reason only.
    for invented in ("monthly", "quarterly", "daily", "weekly", "annually"):
        assert invented not in (result.documentation.when.value or "").lower()
        assert invented not in when_missing.reason.lower()


def test_missing_system_does_not_invent_one():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        ["Interviewer: Who performs the review?", "Interviewee: The Finance Manager does."],
    )
    result = extract_control_documentation(control, questions, transcript)
    assert result.documentation.where.value is None
    dumped = json.dumps(result.documentation.model_dump(mode="json"))
    for invented_system in ("SAP", "Excel", "SharePoint", "Oracle"):
        assert invented_system not in dumped


# ---------- 7. Missing information produces structured output ----------


def test_missing_information_uses_the_existing_model_with_reason():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(control.control_id, ["Interviewer: Who performs this?", "Interviewee: Not sure, honestly."])
    result = extract_control_documentation(control, questions, transcript)
    who_missing = next(m for m in result.documentation.missing_information if m.field == "documentation.who")
    assert who_missing.reason  # non-empty, explains why
    assert who_missing.status.value == "open"


def test_missing_information_reuses_the_stage_one_question_as_follow_up():
    """follow_up_question must be populated by reusing the already-generated
    stage-1 WalkthroughQuestion for that category - not left blank, and not
    drafted again from scratch (that would duplicate question-generation
    logic)."""
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    who_question = next(q for q in questions.questions if q.category.value == "who" and q.required)

    transcript = transcript_from_lines(control.control_id, ["Interviewer: What happens?", "Interviewee: Something happens."])
    result = extract_control_documentation(control, questions, transcript)

    who_missing = next(m for m in result.documentation.missing_information if m.field == "documentation.who")
    assert who_missing.follow_up_question == who_question.question_text


# ---------- 8. Draft control description uses only supported information ----------


def test_draft_description_omits_unresolved_dimensions():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        ["Interviewer: Who performs the review?", "Interviewee: The Finance Manager reviews it."],
    )
    result = extract_control_documentation(control, questions, transcript)
    description = result.documentation.control_description
    assert description is not None
    assert "Finance Manager" in description
    # Nothing invented for the unresolved dimensions.
    for invented in ("Monthly", "Quarterly", "SAP", "Excel"):
        assert invented not in description


def test_draft_description_gives_each_attribute_its_own_paragraph():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        [
            "Interviewer: Who performs the review?",
            "Interviewee: The Finance Manager reviews it.",
            "Interviewer: How often does this happen?",
            "Interviewee: Monthly.",
        ],
    )
    result = extract_control_documentation(control, questions, transcript)
    description = result.documentation.control_description
    paragraphs = description.split("\n\n")
    assert len(paragraphs) == 2
    assert paragraphs[0].startswith("Who:")
    assert paragraphs[1].startswith("When:")
    # Not run together on one line.
    assert "Who: The Finance Manager reviews it. When:" not in description


def test_draft_description_is_none_when_nothing_was_resolved():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        ["Interviewer: Who performs this?", "Interviewee: I'm not sure, I couldn't tell you."],
    )
    result = extract_control_documentation(control, questions, transcript)
    assert result.documentation.control_description is None


# ---------- 9. Conflicting information is preserved, not silently resolved ----------


def test_short_conflicting_answers_are_flagged_not_merged():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        [
            "Interviewer: How often is this performed?",
            "Interviewee: Weekly.",
            "Interviewer: How frequently does this control run?",
            "Interviewee: Monthly.",
        ],
    )
    result = extract_control_documentation(control, questions, transcript)
    assert result.documentation.when.value is None
    reason = next(m.reason for m in result.documentation.missing_information if m.field == "documentation.when")
    assert "weekly" in reason.lower() and "monthly" in reason.lower()


def test_long_complementary_answers_for_the_same_category_are_combined_not_flagged():
    """Regression test for a real bug found reviewing the potential_gap pilot
    fixture: two long, topically-different-but-non-contradictory HOW answers
    were being falsely treated as a conflict because they scored low on
    lexical similarity. Length is now used to distinguish "different
    sub-topic" from "actually competing short facts"."""
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        [
            "Interviewer: How is the review actually carried out?",
            "Interviewee: The reviewer opens the reconciliation file and checks each line item against the bank statement for that period, noting any discrepancies found along the way.",
            "Interviewer: How reliably does this actually happen every month in practice?",
            "Interviewee: Honestly it is fairly consistent, though a couple of months this year the review slipped past month end because the reviewer was on leave and no one covered it.",
        ],
    )
    result = extract_control_documentation(control, questions, transcript)
    assert result.documentation.how.value is not None
    assert "discrepancies" in result.documentation.how.value
    assert "on leave" in result.documentation.how.value
    assert len(result.documentation.how.source_references) == 2


# ---------- 10. Invalid input follows existing validation behaviour ----------


def test_invalid_transcript_missing_segments_is_rejected():
    with pytest.raises(ValidationError):
        Transcript(transcript_id="WT-1", control_id="CTRL-1", source_name="x", segments=[])


def test_duplicate_segment_id_is_rejected():
    with pytest.raises(ValidationError):
        Transcript(
            transcript_id="WT-1",
            control_id="CTRL-1",
            source_name="x",
            segments=[
                TranscriptSegment(segment_id="L01", speaker="Interviewer", text="Who?"),
                TranscriptSegment(segment_id="L01", speaker="Interviewee", text="Someone."),
            ],
        )


# ---------- 11. Output conforms to the canonical model ----------


def test_output_documentation_is_valid_control_documentation_and_json_serializable():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        ["Interviewer: Who performs the review?", "Interviewee: The Finance Manager does."],
    )
    result = extract_control_documentation(control, questions, transcript)
    dumped = result.documentation.model_dump(mode="json")
    json.dumps(dumped)  # must be plain JSON
    assert "who" in dumped and "missing_information" in dumped and "metadata" in dumped
    assert dumped["metadata"]["generated_by"] == "ai"


# ---------- 12. Generated documentation remains unapproved ----------


def test_extraction_never_sets_review_decision():
    control = minimal_control()
    questions = generate_walkthrough_questions(control)
    transcript = transcript_from_lines(
        control.control_id,
        ["Interviewer: Who performs the review?", "Interviewee: The Finance Manager does."],
    )
    result = extract_control_documentation(control, questions, transcript)
    # ExtractionResult has no review field at all - it cannot set one.
    assert not hasattr(result, "review")
    assert control.review.decision.value == "not_reviewed"  # untouched on the original record


# ---------- 13. Existing pilot fixtures can be processed ----------


@pytest.mark.parametrize(
    "case_id",
    ["well_documented", "incomplete", "design_issue", "potential_gap", "insufficient_information"],
)
def test_extraction_runs_cleanly_against_every_pilot_fixture(case_id):
    record, questions, transcript = load_pilot_case(case_id)
    result = extract_control_documentation(record.control, questions, transcript)
    assert result.control_id == record.control.control_id
    # At least one of the six attributes resolved for every case, including
    # the insufficient_information one (its HOW resolves to an unreliable
    # hedge our soft-hedge detector doesn't catch - see known limitations).
    resolved = [
        attr
        for attr in ("what", "who", "when", "why", "where", "how")
        if getattr(result.documentation, attr).value is not None
    ]
    assert len(resolved) >= 1


def test_well_documented_pilot_case_has_no_missing_information():
    record, questions, transcript = load_pilot_case("well_documented")
    result = extract_control_documentation(record.control, questions, transcript)
    assert result.documentation.missing_information == []


def test_incomplete_pilot_case_flags_when_and_why_as_missing():
    record, questions, transcript = load_pilot_case("incomplete")
    result = extract_control_documentation(record.control, questions, transcript)
    missing_fields = {m.field for m in result.documentation.missing_information}
    assert {"documentation.when", "documentation.why"} <= missing_fields
    assert result.documentation.what.value is not None  # not swallowed by the WHEN misclassification bug


def test_potential_gap_pilot_case_has_no_missing_information():
    """Regression test for the compound-question bug found in review: 'Who
    is involved, and when does approval happen?' must resolve BOTH who and
    when, not just one at the other's expense."""
    record, questions, transcript = load_pilot_case("potential_gap")
    result = extract_control_documentation(record.control, questions, transcript)
    assert result.documentation.missing_information == []
    assert result.documentation.who.value is not None
    assert result.documentation.when.value is not None


def test_insufficient_information_pilot_case_flags_most_attributes_missing():
    record, questions, transcript = load_pilot_case("insufficient_information")
    result = extract_control_documentation(record.control, questions, transcript)
    missing_fields = {m.field for m in result.documentation.missing_information}
    assert {
        "documentation.what",
        "documentation.who",
        "documentation.when",
        "documentation.why",
        "documentation.where",
    } <= missing_fields


def test_walkthrough_questions_receive_answers_linked_to_the_same_sources():
    """Preserves WalkthroughQuestion -> transcript -> attribute ->
    SourceReference (Step 11)."""
    record, questions, transcript = load_pilot_case("well_documented")
    result = extract_control_documentation(record.control, questions, transcript)
    who_questions = [q for q in result.questions.questions if q.category is not None and q.category.value == "who"]
    assert who_questions
    primary = who_questions[0]
    assert primary.answer is not None
    assert primary.source_references
    assert primary.source_references[0].locator == result.documentation.who.source_references[0].locator
