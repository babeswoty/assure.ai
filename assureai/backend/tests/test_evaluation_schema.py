import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.enums import (
    FieldComparisonResult,
    MaterialDiscrepancyType,
    MissingInfoDetectionResult,
    TraceabilityAssessmentResult,
    UsefulnessRating,
)
from app.evaluation.models import (
    ConsistencyFinding,
    ControlEvaluation,
    FieldComparison,
    MaterialDiscrepancy,
    MissingInformationComparison,
    TraceabilityAssessment,
    UsefulnessAssessment,
)
from app.evaluation.validation import (
    build_pilot_summary,
    try_validate_control_evaluation,
    validate_control_evaluation,
)

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "examples" / "sample_control_evaluation.json"
)


def load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def base_evaluation(**overrides) -> dict:
    data = {
        "pilot_id": "PILOT-2026-01",
        "control_id": "P2P-VEN-001",
        "control_schema_version": "1.0",
    }
    data.update(overrides)
    return data


# ---------- Example file / basic schema integrity ----------


def test_example_file_is_valid():
    evaluation = validate_control_evaluation(load_example())

    assert isinstance(evaluation, ControlEvaluation)
    assert evaluation.control_id == "FC-JE-003"
    # Computed summaries reflect the underlying lists, not a stored value.
    assert evaluation.quality_summary["aligned"] == 2
    assert evaluation.quality_summary["partially_aligned"] == 1
    assert evaluation.quality_summary["not_aligned"] == 1
    assert evaluation.traceability_summary["supported"] == 1
    assert evaluation.traceability_summary["no_reference"] == 1


def test_missing_required_identifiers_are_rejected():
    with pytest.raises(ValidationError):
        ControlEvaluation(control_id="C-1", control_schema_version="1.0")  # no pilot_id

    with pytest.raises(ValidationError):
        ControlEvaluation(pilot_id="PILOT-1", control_schema_version="1.0")  # no control_id


def test_duplicate_field_path_within_field_comparisons_is_rejected():
    with pytest.raises(ValidationError):
        ControlEvaluation(
            **base_evaluation(),
            field_comparisons=[
                {"field": "documentation.who", "comparison": "aligned"},
                {"field": "documentation.who", "comparison": "not_aligned"},
            ],
        )


def test_duplicate_discrepancy_id_is_rejected():
    with pytest.raises(ValidationError):
        ControlEvaluation(
            **base_evaluation(),
            material_discrepancies=[
                {
                    "discrepancy_id": "MD-1",
                    "discrepancy_type": "unsupported_conclusion",
                    "description": "a",
                },
                {
                    "discrepancy_id": "MD-1",
                    "discrepancy_type": "fabricated_source_reference",
                    "description": "b",
                },
            ],
        )


def test_invalid_comparison_enum_is_rejected():
    with pytest.raises(ValidationError):
        FieldComparison(field="documentation.who", comparison="mostly_fine_i_guess")


def test_consistency_finding_requires_at_least_two_controls():
    with pytest.raises(ValidationError):
        ConsistencyFinding(
            aspect="x", finding="y", control_ids=["C-1"]  # only one control - not a comparison
        )


# ---------- Scenario 1: exact agreement ----------


def test_scenario_exact_agreement():
    fc = FieldComparison(
        field="design_assessment.first_pass_design_conclusion",
        assureai_value="pass",
        reference_value="pass",
        comparison=FieldComparisonResult.ALIGNED,
    )
    assert fc.comparison == FieldComparisonResult.ALIGNED
    assert fc.assureai_value == fc.reference_value


# ---------- Scenario 2: different wording, same substantive conclusion ----------


def test_scenario_different_wording_same_conclusion():
    fc = FieldComparison(
        field="documentation.who",
        assureai_value="Preparer: any FR team member. Reviewer: FR Manager or Senior Accountant.",
        reference_value="Anyone in FR can prepare; approval sits with the FR Manager or a Senior Accountant.",
        comparison=FieldComparisonResult.ALIGNED,
        reviewer_comment="Same substance, different phrasing.",
    )
    assert fc.comparison == FieldComparisonResult.ALIGNED
    assert fc.assureai_value != fc.reference_value  # schema never requires string equality


# ---------- Scenario 3: partial agreement ----------


def test_scenario_partial_agreement():
    fc = FieldComparison(
        field="documentation.why",
        assureai_value=None,
        reference_value="Threshold exists to focus review effort on entries large enough to matter.",
        comparison=FieldComparisonResult.PARTIALLY_ALIGNED,
        reviewer_comment="AssureAI correctly abstained; reviewer supplied outside knowledge.",
    )
    assert fc.comparison == FieldComparisonResult.PARTIALLY_ALIGNED


# ---------- Scenario 4: material disagreement ----------


def test_scenario_material_disagreement():
    evaluation = ControlEvaluation(
        **base_evaluation(),
        field_comparisons=[
            {
                "field": "design_assessment.first_pass_design_conclusion",
                "assureai_value": "pass",
                "reference_value": "fail",
                "comparison": "not_aligned",
                "material_discrepancy": True,
            }
        ],
        material_discrepancies=[
            {
                "discrepancy_id": "MD-1",
                "discrepancy_type": "materially_different_design_conclusion",
                "field": "design_assessment.first_pass_design_conclusion",
                "description": "AssureAI concluded PASS; reviewer concluded FAIL due to an unmitigated segregation-of-duties issue AssureAI did not identify.",
            }
        ],
    )
    assert evaluation.field_comparisons[0].material_discrepancy is True
    assert (
        evaluation.material_discrepancies[0].discrepancy_type
        == MaterialDiscrepancyType.MATERIALLY_DIFFERENT_DESIGN_CONCLUSION
    )


# ---------- Scenario 5: correctly detected missing information (TRUE_POSITIVE) ----------


def test_scenario_missing_information_true_positive():
    mic = MissingInformationComparison(
        field="documentation.why",
        assureai_flagged_missing=True,
        reviewer_flagged_missing=True,
        result=MissingInfoDetectionResult.TRUE_POSITIVE,
    )
    assert mic.result == MissingInfoDetectionResult.TRUE_POSITIVE


# ---------- Scenario 6: missed missing information (FALSE_NEGATIVE) ----------


def test_scenario_missing_information_false_negative_links_to_discrepancy():
    evaluation = ControlEvaluation(
        **base_evaluation(),
        missing_information_comparisons=[
            {
                "field": "documentation.when",
                "assureai_flagged_missing": False,
                "reviewer_flagged_missing": True,
                "result": "false_negative",
                "reviewer_comment": "Transcript never actually established timing; AssureAI documented it anyway without flagging the gap.",
            }
        ],
        material_discrepancies=[
            {
                "discrepancy_id": "MD-1",
                "discrepancy_type": "missing_info_not_detected",
                "field": "documentation.when",
                "description": "AssureAI stated a timing assumption as fact instead of flagging it as unconfirmed.",
            }
        ],
    )
    assert evaluation.missing_information_summary["false_negative"] == 1
    assert len(evaluation.material_discrepancies) == 1


# ---------- Scenario 7: false missing-information flag (FALSE_POSITIVE) ----------


def test_scenario_missing_information_false_positive():
    mic = MissingInformationComparison(
        field="documentation.where",
        assureai_flagged_missing=True,
        reviewer_flagged_missing=False,
        result=MissingInfoDetectionResult.FALSE_POSITIVE,
        reviewer_comment="The system name was stated clearly in the transcript; AssureAI missed it and flagged the field as unknown.",
    )
    assert mic.result == MissingInfoDetectionResult.FALSE_POSITIVE


# ---------- Scenario 8: correct source, supported conclusion ----------


def test_scenario_traceability_supported():
    ta = TraceabilityAssessment(
        field="documentation.who",
        cited_source_references=[
            {
                "source_id": "WT-1",
                "source_type": "walkthrough_transcript",
                "source_name": "Walkthrough",
                "locator": "00:03:12",
                "excerpt": "Anyone on the FR team can key a manual JE.",
            }
        ],
        result=TraceabilityAssessmentResult.SUPPORTED,
    )
    assert ta.result == TraceabilityAssessmentResult.SUPPORTED


# ---------- Scenario 9: source exists but does not support the conclusion ----------


def test_scenario_traceability_unsupported():
    ta = TraceabilityAssessment(
        field="gap_assessment.gaps[GAP-1].impact",
        cited_source_references=[
            {
                "source_id": "WT-1",
                "source_type": "walkthrough_transcript",
                "source_name": "Walkthrough",
                "locator": "00:09:00",
                "excerpt": "We haven't had an issue with this in a while.",
            }
        ],
        result=TraceabilityAssessmentResult.UNSUPPORTED,
        reviewer_comment="The cited excerpt is about frequency of past issues, not about impact severity - it doesn't actually back a 'low impact' rating.",
    )
    assert ta.result == TraceabilityAssessmentResult.UNSUPPORTED


# ---------- Scenario 10: invalid/fabricated source reference ----------


def test_scenario_traceability_incorrect_reference_with_discrepancy():
    evaluation = ControlEvaluation(
        **base_evaluation(),
        traceability_assessments=[
            {
                "field": "gap_assessment.gaps[GAP-1].root_cause_category",
                "cited_source_references": [
                    {
                        "source_id": "WT-99",
                        "source_type": "walkthrough_transcript",
                        "source_name": "FC-JE-003 Walkthrough - J. Adebayo",
                        "locator": "01:45:00",
                    }
                ],
                "result": "incorrect_reference",
                "reviewer_comment": "The walkthrough session was only 15 minutes long; there is no 01:45:00 timestamp, and no source_id WT-99 exists in this engagement.",
            }
        ],
        material_discrepancies=[
            {
                "discrepancy_id": "MD-1",
                "discrepancy_type": "fabricated_source_reference",
                "field": "gap_assessment.gaps[GAP-1].root_cause_category",
                "description": "Cited transcript timestamp does not exist.",
            }
        ],
    )
    assert evaluation.traceability_summary["incorrect_reference"] == 1


# ---------- Scenario 11: correctly refusing to conclude (insufficient evidence) ----------


def test_scenario_correct_refusal_to_conclude():
    fc = FieldComparison(
        field="design_assessment.risk_objective_control_alignment",
        assureai_value="unknown",
        reference_value="unknown",
        comparison=FieldComparisonResult.ALIGNED,
        reviewer_comment="Both AssureAI and the reviewer agree the walkthrough evidence does not support a conclusion either way - correctly left as UNKNOWN rather than guessed.",
    )
    assert fc.comparison == FieldComparisonResult.ALIGNED


# ---------- Scenario 12: AI concluded despite insufficient evidence ----------


def test_scenario_conclusion_despite_insufficient_evidence():
    evaluation = ControlEvaluation(
        **base_evaluation(),
        field_comparisons=[
            {
                "field": "design_assessment.completeness",
                "assureai_value": "pass",
                "reference_value": "unknown",
                "comparison": "not_aligned",
                "material_discrepancy": True,
                "reviewer_comment": "AssureAI marked completeness PASS despite the transcript never covering two of the six attributes.",
            }
        ],
        material_discrepancies=[
            {
                "discrepancy_id": "MD-1",
                "discrepancy_type": "conclusion_despite_insufficient_evidence",
                "field": "design_assessment.completeness",
                "description": "PASS conclusion reached without evidence for 'when' or 'why'.",
            }
        ],
    )
    assert (
        evaluation.material_discrepancies[0].discrepancy_type
        == MaterialDiscrepancyType.CONCLUSION_DESPITE_INSUFFICIENT_EVIDENCE
    )


# ---------- Scenario 13: useful draft requiring minor edits ----------


def test_scenario_usefulness_minor_amendment():
    ua = UsefulnessAssessment(
        field="documentation.control_description",
        rating=UsefulnessRating.MINOR_AMENDMENT,
        reviewer_comment="Accurate; tightened wording only.",
    )
    assert ua.rating == UsefulnessRating.MINOR_AMENDMENT


# ---------- Scenario 14: draft requiring substantial rewrite ----------


def test_scenario_usefulness_substantial_amendment():
    ua = UsefulnessAssessment(
        field="gap_assessment.gaps[GAP-1].recommendation",
        rating=UsefulnessRating.SUBSTANTIAL_AMENDMENT,
        reviewer_comment="Right direction, but the proposed remediation had to be substantially rewritten to be actionable.",
    )
    assert ua.rating == UsefulnessRating.SUBSTANTIAL_AMENDMENT


# ---------- Scenario 15: reviewer completely rejects a generated draft ----------


def test_scenario_usefulness_reject_replace():
    ua = UsefulnessAssessment(
        field="design_assessment.conclusion_rationale",
        rating=UsefulnessRating.REJECT_REPLACE,
        reviewer_comment="Rationale misread the control's purpose; reviewer wrote a new one from scratch.",
    )
    assert ua.rating == UsefulnessRating.REJECT_REPLACE


# ---------- Pilot-level aggregation ----------


def test_build_pilot_summary_aggregates_without_losing_discrepancy_visibility():
    eval_1 = ControlEvaluation(
        **base_evaluation(control_id="C-1"),
        field_comparisons=[{"field": "documentation.who", "comparison": "aligned"}],
        material_discrepancies=[
            {
                "discrepancy_id": "MD-1",
                "discrepancy_type": "significant_gap_missed",
                "description": "Reviewer found an unremediated gap AssureAI never raised.",
            }
        ],
    )
    eval_2 = ControlEvaluation(
        **base_evaluation(control_id="C-2"),
        field_comparisons=[{"field": "documentation.who", "comparison": "not_aligned"}],
    )

    summary = build_pilot_summary("PILOT-2026-01", [eval_1, eval_2])

    assert summary.control_ids == ["C-1", "C-2"]
    assert summary.field_alignment_counts["documentation.who"] == {"aligned": 1, "not_aligned": 1}
    # The discrepancy is individually visible, not folded into a count.
    assert len(summary.material_discrepancies) == 1
    assert summary.material_discrepancies[0].control_id == "C-1"
