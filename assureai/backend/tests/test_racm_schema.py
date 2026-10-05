import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.racm import (
    AssessmentDimension,
    AssessmentResult,
    Control,
    ControlReview,
    Engagement,
    Gap,
    GapAssessment,
    RACMControlRecord,
    Risk,
    SourceReference,
    Walkthrough,
    WalkthroughQuestion,
)
from app.validation import merge_control_section, try_validate_record, validate_record

EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "examples" / "sample_control_record.json"


def load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def minimal_engagement() -> dict:
    return {
        "engagement_id": "ENG-1",
        "client": "Acme Corp",
        "process": "Procure to Pay",
        "subprocess": "Vendor Setup",
    }


def minimal_risk() -> dict:
    return {"risk_id": "R-1", "risk_description": "Fictitious vendors could be onboarded."}


# ---------- 1. Valid, complete record ----------


def test_valid_complete_record_from_example_file():
    record = validate_record(load_example())

    assert isinstance(record, RACMControlRecord)
    assert record.control.control_id == "FC-JE-003"
    # An unresolved documentation gap was captured, not an invented value.
    assert record.control.documentation.why.value is None
    assert len(record.control.documentation.missing_information) == 1
    # Different attributes are traceable to different evidence.
    assert record.control.documentation.what.source_references[0].locator == "00:04:05"
    assert record.control.documentation.who.source_references[0].locator == "00:03:12"
    # AI draft conclusions must not be silently treated as approved.
    assert record.control.review.decision.value == "not_reviewed"
    assert record.control.design_assessment.first_pass_design_conclusion == AssessmentResult.PARTIAL


# ---------- 2. Partial / in-progress record ----------


def test_partial_in_progress_record_is_valid():
    """A control just created from RACM input, before any walkthrough has
    happened, should still validate - most sections are optional/defaulted."""
    data = {
        "schema_version": "1.0",
        "engagement": minimal_engagement(),
        "control": {
            "control_id": "P2P-VEN-001",
            "control_title": "New Vendor Approval",
            "risk": minimal_risk(),
        },
    }

    record = validate_record(data)

    assert record.control.documentation.what.value is None
    assert record.control.design_assessment.first_pass_design_conclusion == AssessmentResult.NOT_ASSESSED
    assert record.control.gap_assessment.gaps == []
    assert record.control.review.decision.value == "not_reviewed"


# ---------- 3. Invalid enum/value ----------


def test_invalid_gap_type_enum_is_rejected():
    data = {
        "schema_version": "1.0",
        "engagement": minimal_engagement(),
        "control": {
            "control_id": "P2P-VEN-001",
            "control_title": "New Vendor Approval",
            "risk": minimal_risk(),
            "gap_assessment": {
                "gaps": [
                    {
                        "gap_id": "GAP-1",
                        "gap_type": "totally_made_up_type",
                        "gap_title": "x",
                        "gap_description": "x",
                    }
                ]
            },
        },
    }

    with pytest.raises(ValidationError):
        validate_record(data)


def test_invalid_review_decision_enum_is_rejected():
    with pytest.raises(ValidationError):
        Control(
            control_id="C-1",
            control_title="Some Control",
            risk=Risk(**minimal_risk()),
            review={"decision": "sort_of_approved_i_guess"},
        )


# ---------- 4. Malformed source reference ----------


def test_malformed_source_reference_missing_id_is_rejected():
    with pytest.raises(ValidationError):
        SourceReference(
            source_id="",  # violates min_length=1
            source_type="walkthrough_transcript",
            source_name="Some Transcript",
        )


def test_malformed_source_reference_invalid_type_is_rejected():
    with pytest.raises(ValidationError):
        SourceReference(
            source_id="SRC-1",
            source_type="a_source_type_that_does_not_exist",
            source_name="Some Transcript",
        )


# ---------- 5. Missing required identifier ----------


def test_missing_control_id_is_rejected():
    with pytest.raises(ValidationError):
        Control(control_title="No ID Control", risk=Risk(**minimal_risk()))


def test_missing_engagement_id_is_rejected():
    with pytest.raises(ValidationError):
        Engagement(client="Acme Corp", process="Procure to Pay")


def test_missing_gap_id_is_rejected():
    with pytest.raises(ValidationError):
        Gap(
            gap_type="documentation_gap",
            gap_title="x",
            gap_description="x",
        )


# ---------- 6. Unknown / not-assessed state ----------


def test_unknown_and_not_assessed_are_distinct_valid_states():
    data = {
        "schema_version": "1.0",
        "engagement": minimal_engagement(),
        "control": {
            "control_id": "P2P-VEN-001",
            "control_title": "New Vendor Approval",
            "risk": minimal_risk(),
            "design_assessment": {
                "completeness": {"result": "unknown", "rationale": "Evidence was contradictory."},
                # relevance/alignment left at their NOT_ASSESSED default
            },
        },
    }

    record = validate_record(data)
    da = record.control.design_assessment

    assert da.completeness.result == AssessmentResult.UNKNOWN
    assert da.relevance.result == AssessmentResult.NOT_ASSESSED
    assert da.completeness.result != da.relevance.result
    assert AssessmentResult.UNKNOWN not in (AssessmentResult.PASS, AssessmentResult.FAIL)
    assert AssessmentResult.NOT_ASSESSED not in (AssessmentResult.PASS, AssessmentResult.FAIL)


# ---------- 7. HITL gate: AI draft conclusions cannot become "approved" for free ----------


def test_review_decision_requires_reviewer_identity():
    """A decision cannot be recorded without saying who made it - this is the
    mechanism that stops an AI draft from silently becoming an approved
    human conclusion."""
    data = {
        "schema_version": "1.0",
        "engagement": minimal_engagement(),
        "control": {
            "control_id": "P2P-VEN-001",
            "control_title": "New Vendor Approval",
            "risk": minimal_risk(),
            "review": {"decision": "approved"},  # no reviewer_id
        },
    }

    record, error = try_validate_record(data)

    assert record is None
    assert error is not None
    assert "reviewer_id" in str(error)


def test_review_decision_with_reviewer_identity_is_valid():
    data = {
        "schema_version": "1.0",
        "engagement": minimal_engagement(),
        "control": {
            "control_id": "P2P-VEN-001",
            "control_title": "New Vendor Approval",
            "risk": minimal_risk(),
            "review": {
                "decision": "approved_with_edits",
                "reviewer_id": "jsmith",
                "reviewer_comments": "Adjusted rationale wording; conclusion stands.",
                "reviewed_at": "2026-09-25T09:00:00Z",
            },
        },
    }

    record = validate_record(data)
    assert record.control.review.decision.value == "approved_with_edits"


# ---------- extra: source excerpt cannot be used to smuggle full documents ----------


def test_source_reference_excerpt_length_is_bounded():
    with pytest.raises(ValidationError):
        SourceReference(
            source_id="SRC-1",
            source_type="policy_document",
            source_name="Some Policy",
            excerpt="x" * 1001,
        )


# ---------- 8. NOT_APPLICABLE is a distinct, legitimate conclusion ----------


def test_not_applicable_is_distinct_from_every_other_result():
    dim = AssessmentDimension(
        result="not_applicable",
        rationale="This control has no linked risk objective yet, so alignment cannot apply.",
    )

    assert dim.result == AssessmentResult.NOT_APPLICABLE
    assert dim.result not in (
        AssessmentResult.PASS,
        AssessmentResult.FAIL,
        AssessmentResult.PARTIAL,
        AssessmentResult.NOT_ASSESSED,
        AssessmentResult.UNKNOWN,
    )


# ---------- 9. Duplicate ids within a control must be rejected ----------


def test_duplicate_gap_id_is_rejected():
    with pytest.raises(ValidationError):
        GapAssessment(
            gaps=[
                {
                    "gap_id": "GAP-1",
                    "gap_type": "documentation_gap",
                    "gap_title": "a",
                    "gap_description": "a",
                },
                {
                    "gap_id": "GAP-1",
                    "gap_type": "design_gap",
                    "gap_title": "b",
                    "gap_description": "b",
                },
            ]
        )


def test_duplicate_walkthrough_question_id_is_rejected():
    with pytest.raises(ValidationError):
        Walkthrough(
            questions=[
                WalkthroughQuestion(question_id="Q1", question_text="a"),
                WalkthroughQuestion(question_id="Q1", question_text="b"),
            ]
        )


# ---------- 10. Review decisions must leave a complete, actionable audit trail ----------


def test_review_decision_requires_reviewed_at():
    with pytest.raises(ValidationError) as exc_info:
        ControlReview(decision="approved", reviewer_id="jsmith")

    assert "reviewed_at" in str(exc_info.value)


def test_review_rejection_requires_comments():
    with pytest.raises(ValidationError) as exc_info:
        ControlReview(
            decision="rejected",
            reviewer_id="jsmith",
            reviewed_at="2026-09-25T09:00:00Z",
        )

    assert "reviewer_comments" in str(exc_info.value)


def test_review_rejection_with_comments_is_valid():
    review = ControlReview(
        decision="rejected",
        reviewer_id="jsmith",
        reviewed_at="2026-09-25T09:00:00Z",
        reviewer_comments="Root cause is not supported by the cited evidence - please re-assess.",
    )
    assert review.decision.value == "rejected"


# ---------- 11. Gap-level unknowns can be recorded explicitly, not guessed ----------


def test_gap_assessment_supports_its_own_missing_information():
    ga = GapAssessment(
        missing_information=[
            {
                "field": "gap_assessment.gaps",
                "reason": "Gap analysis has not started - awaiting design assessment sign-off.",
                "status": "open",
            }
        ]
    )
    assert ga.missing_information[0].status.value == "open"


# ---------- 12. Progressive enrichment must not lose earlier stages' work ----------


def test_progressive_enrichment_preserves_every_earlier_section():
    """Simulates several agents each writing only their own section, one
    after another, through the safe merge_control_section() path."""
    base = {
        "schema_version": "1.0",
        "engagement": minimal_engagement(),
        "control": {
            "control_id": "P2P-VEN-001",
            "control_title": "New Vendor Approval",
            "risk": minimal_risk(),
        },
    }
    record = validate_record(base)

    record = merge_control_section(
        record,
        "walkthrough",
        {"questions": [{"question_id": "Q1", "question_text": "Who approves new vendors?"}]},
    )
    record = merge_control_section(
        record,
        "documentation",
        {"who": {"value": "Accounts Payable Manager"}},
    )
    record = merge_control_section(
        record,
        "design_assessment",
        {"first_pass_design_conclusion": "pass"},
    )
    record = merge_control_section(
        record,
        "gap_assessment",
        {
            "gaps": [
                {
                    "gap_id": "GAP-1",
                    "gap_type": "documentation_gap",
                    "gap_title": "Approval evidence not retained",
                    "gap_description": "No record of approval is kept once a vendor is onboarded.",
                }
            ]
        },
    )

    # Everything written by earlier stages is still present after later
    # stages ran - none of them constructed a fresh, blank Control.
    assert record.control.walkthrough.questions[0].question_text == "Who approves new vendors?"
    assert record.control.documentation.who.value == "Accounts Payable Manager"
    assert record.control.design_assessment.first_pass_design_conclusion == AssessmentResult.PASS
    assert record.control.gap_assessment.gaps[0].gap_id == "GAP-1"
    # Identity fields fixed at record creation are untouched throughout.
    assert record.control.control_id == "P2P-VEN-001"
    assert record.control.risk.risk_id == "R-1"
    # The still-untouched review section keeps its safe default.
    assert record.control.review.decision.value == "not_reviewed"
