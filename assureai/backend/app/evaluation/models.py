"""Pilot evaluation domain model.

Compares one AssureAI-drafted RACMControlRecord against an experienced
reviewer's independent reference conclusions for the same control, across
the five pilot areas: quality, consistency, traceability, missing-information
detection, and usefulness. See ../../../PILOT_EVALUATION_FRAMEWORK.md for the
methodology this model implements.

This module intentionally does NOT embed full RACM sub-objects. Every
comparison references the RACM control by `control_id` and a field's dotted
path (the same convention MissingInformation.field already uses), and
carries only short textual snapshots of the compared values - not copies of
the underlying record.
"""
import enum
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.schemas.common import SourceReference, ensure_unique_ids
from app.schemas.racm import ReviewDecision

from app.evaluation.enums import (
    EvaluationMethod,
    FieldComparisonResult,
    MaterialDiscrepancyType,
    MissingInfoDetectionResult,
    TraceabilityAssessmentResult,
    UsefulnessRating,
)


def _tally(values: List[enum.Enum], enum_cls: type[enum.Enum]) -> Dict[str, int]:
    """Counts occurrences by enum value, including zero counts for every
    member of enum_cls, so consumers never have to guess whether a missing
    key means zero or means "not computed"."""
    counts = {member.value: 0 for member in enum_cls}
    for value in values:
        counts[value.value] += 1
    return counts


# ---------- Quality (field-level comparison) ----------


class FieldComparison(BaseModel):
    """One field/output compared between the AssureAI draft and the
    reviewer's reference conclusion, judged on substantive meaning.

    `assureai_value`/`reference_value` are short textual snapshots (e.g. the
    documentation string, or an enum's value) taken at evaluation time - not
    a live link to the RACM record, and not the full nested RACM sub-object.
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, description="Dotted path into the control, e.g. 'documentation.who'.")
    assureai_value: Optional[str] = None
    reference_value: Optional[str] = None
    comparison: FieldComparisonResult = FieldComparisonResult.NOT_ASSESSABLE
    material_discrepancy: bool = False
    reviewer_comment: Optional[str] = None
    supporting_source_references: List[SourceReference] = Field(default_factory=list)


# ---------- Traceability ----------


class TraceabilityAssessment(BaseModel):
    """Whether a significant AI-generated statement is actually supported by
    what it cites. `field` uses the same dotted-path convention as
    FieldComparison.field, so the two can be cross-referenced for the same
    statement without duplicating its value again here.
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    cited_source_references: List[SourceReference] = Field(
        default_factory=list,
        description="Exactly what AssureAI cited for this statement (empty means it cited nothing).",
    )
    result: TraceabilityAssessmentResult = TraceabilityAssessmentResult.NOT_APPLICABLE
    reviewer_comment: Optional[str] = None


# ---------- Missing-information detection ----------


class MissingInformationComparison(BaseModel):
    """Compares AssureAI's missing-information flags against what the
    reviewer independently determines was actually missing.

    True negatives (neither side flags the field, and nothing was in fact
    missing) are not recorded as individual rows here - there would be one
    per untouched field per control, which duplicates the RACM record for
    no evaluative benefit. `PilotSummary` tracks the total number of fields
    checked separately, so recall/precision-style rollups remain computable
    without materializing every non-event.
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    assureai_flagged_missing: bool = Field(
        description="Whether the RACM record has a MissingInformation entry for this field."
    )
    reviewer_flagged_missing: bool = Field(
        description="Whether the reviewer independently considers this field's information missing."
    )
    result: MissingInfoDetectionResult
    reviewer_comment: Optional[str] = None


# ---------- Usefulness ----------


class UsefulnessAssessment(BaseModel):
    """Reviewer's rating of one drafted output as a starting point for their
    own work - not a judgement of factual correctness (that's `quality`)."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, description="Dotted path to the drafted output, e.g. 'gap_assessment.gaps[GAP-1].recommendation'.")
    rating: UsefulnessRating
    reviewer_comment: Optional[str] = None


# ---------- Consistency ----------


class ConsistencyObservation(BaseModel):
    """A fact about *this* control relevant to judging consistency across
    the pilot - not a verdict. A verdict requires comparing multiple
    controls, which only PilotSummary.consistency_findings can do.
    """

    model_config = ConfigDict(extra="forbid")

    aspect: str = Field(min_length=1, description="e.g. 'use of UNKNOWN vs NOT_ASSESSED', 'missing-info handling'.")
    observation: str = Field(min_length=1)
    compared_control_ids: List[str] = Field(
        default_factory=list,
        description="Other control_ids this observation was already compared against, if known.",
    )
    reviewer_comment: Optional[str] = None


class ConsistencyFinding(BaseModel):
    """A cross-control consistency verdict - lives on PilotSummary, since it
    inherently spans more than one ControlEvaluation.

    Differences between controls are not automatically contradictions:
    `is_contradiction` must be set deliberately, and controls with
    legitimately different facts should have `is_contradiction=False`.
    """

    model_config = ConfigDict(extra="forbid")

    aspect: str = Field(min_length=1)
    finding: str = Field(min_length=1)
    control_ids: List[str] = Field(min_length=2)
    is_contradiction: bool = False
    reviewer_comment: Optional[str] = None


# ---------- Material discrepancies ----------


class MaterialDiscrepancy(BaseModel):
    """A serious, individually-tracked failure. Never averaged into a score
    - a pilot summary must list these, not just count them (see
    MaterialDiscrepancyRef on PilotSummary).
    """

    model_config = ConfigDict(extra="forbid")

    discrepancy_id: str = Field(min_length=1)
    discrepancy_type: MaterialDiscrepancyType
    field: Optional[str] = Field(
        default=None, description="Dotted path this discrepancy is tied to, if any."
    )
    description: str = Field(min_length=1)
    reviewer_comment: Optional[str] = None
    source_references: List[SourceReference] = Field(default_factory=list)


# ---------- Control evaluation (the per-control pilot record) ----------


class ControlEvaluation(BaseModel):
    """One pilot comparison of a single control's AssureAI draft against an
    experienced reviewer's reference conclusions.

    `quality`, `traceability_summary`, `missing_information_summary`, and
    `usefulness_summary` are computed from the corresponding list fields,
    never stored independently - this avoids the exact mistake found in the
    RACM schema review, where a standalone `reviewed` flag could silently
    disagree with the record it was meant to summarize.
    """

    model_config = ConfigDict(extra="forbid")

    pilot_id: str = Field(min_length=1)
    control_id: str = Field(min_length=1)
    evaluation_version: str = "1.0"

    control_schema_version: str = Field(
        description="RACMControlRecord.schema_version at the time this evaluation was performed."
    )
    control_snapshot_ref: Optional[str] = Field(
        default=None,
        description=(
            "Identifier (hash, revision id, or timestamp) pinning exactly which "
            "version of the RACMControlRecord was evaluated. The master record "
            "is progressively enriched and can change after an evaluation is "
            "recorded; without this, a ControlEvaluation can silently go stale."
        ),
    )

    evaluator_id: Optional[str] = None
    evaluated_at: Optional[datetime] = None

    field_comparisons: List[FieldComparison] = Field(default_factory=list)
    traceability_assessments: List[TraceabilityAssessment] = Field(default_factory=list)
    missing_information_comparisons: List[MissingInformationComparison] = Field(
        default_factory=list
    )
    usefulness_assessments: List[UsefulnessAssessment] = Field(default_factory=list)
    consistency_notes: List[ConsistencyObservation] = Field(default_factory=list)
    material_discrepancies: List[MaterialDiscrepancy] = Field(default_factory=list)

    # What the actual RACM control review concluded, for reference - a
    # pointer to racm.ControlReview.decision, not a duplicate concept.
    reviewer_decision: Optional[ReviewDecision] = None
    reviewer_decision_notes: Optional[str] = None

    @model_validator(mode="after")
    def _unique_field_paths_and_discrepancy_ids(self) -> "ControlEvaluation":
        ensure_unique_ids(
            [c.field for c in self.field_comparisons], "field_comparisons[].field"
        )
        ensure_unique_ids(
            [t.field for t in self.traceability_assessments],
            "traceability_assessments[].field",
        )
        ensure_unique_ids(
            [m.field for m in self.missing_information_comparisons],
            "missing_information_comparisons[].field",
        )
        ensure_unique_ids(
            [u.field for u in self.usefulness_assessments], "usefulness_assessments[].field"
        )
        ensure_unique_ids(
            [d.discrepancy_id for d in self.material_discrepancies],
            "material_discrepancies[].discrepancy_id",
        )
        return self

    @computed_field  # type: ignore[misc]
    @property
    def quality_summary(self) -> Dict[str, int]:
        return _tally([c.comparison for c in self.field_comparisons], FieldComparisonResult)

    @computed_field  # type: ignore[misc]
    @property
    def traceability_summary(self) -> Dict[str, int]:
        return _tally(
            [t.result for t in self.traceability_assessments], TraceabilityAssessmentResult
        )

    @computed_field  # type: ignore[misc]
    @property
    def missing_information_summary(self) -> Dict[str, int]:
        return _tally(
            [m.result for m in self.missing_information_comparisons], MissingInfoDetectionResult
        )

    @computed_field  # type: ignore[misc]
    @property
    def usefulness_summary(self) -> Dict[str, int]:
        return _tally([u.rating for u in self.usefulness_assessments], UsefulnessRating)


# ---------- Pilot-level summary (cross-control aggregation) ----------


class MaterialDiscrepancyRef(BaseModel):
    """A pointer to one control's material discrepancy, kept individually
    visible at the pilot level rather than folded into a count."""

    model_config = ConfigDict(extra="forbid")

    control_id: str = Field(min_length=1)
    discrepancy_id: str = Field(min_length=1)
    discrepancy_type: MaterialDiscrepancyType
    description: str = Field(min_length=1)


class PilotSummary(BaseModel):
    """Cross-control rollup answering the STEP-11 questions, built from a set
    of ControlEvaluations by app.evaluation.validation.build_pilot_summary().

    Unlike ControlEvaluation's computed summaries, these fields are plain
    stored data: PilotSummary is a point-in-time report generated from
    ControlEvaluations that may live elsewhere (separate files/rows), not a
    live view over data held inline, so there is nothing for it to drift
    against once produced. Re-run build_pilot_summary() to refresh it.
    """

    model_config = ConfigDict(extra="forbid")

    pilot_id: str = Field(min_length=1)
    generated_at: Optional[datetime] = None
    control_ids: List[str] = Field(default_factory=list)

    # field path -> {comparison_value: count}, e.g. which fields recur as NOT_ALIGNED.
    field_alignment_counts: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    traceability_counts: Dict[str, int] = Field(default_factory=dict)
    missing_information_counts: Dict[str, int] = Field(default_factory=dict)
    usefulness_counts: Dict[str, int] = Field(default_factory=dict)

    material_discrepancies: List[MaterialDiscrepancyRef] = Field(default_factory=list)
    consistency_findings: List[ConsistencyFinding] = Field(default_factory=list)

    # Qualitative, reviewer-authored notes - deliberately free text rather
    # than a score; "what should improve before the next iteration" is a
    # judgement call, not something to compute.
    open_items_for_next_iteration: List[str] = Field(default_factory=list)
