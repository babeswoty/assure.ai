"""Runtime validation and aggregation entry points for pilot evaluations."""
from datetime import datetime, timezone
from typing import Any, List, Tuple

from pydantic import ValidationError

from app.evaluation.models import (
    ControlEvaluation,
    MaterialDiscrepancyRef,
    PilotSummary,
)


def validate_control_evaluation(data: dict[str, Any]) -> ControlEvaluation:
    """Raises pydantic.ValidationError if the data is invalid."""
    return ControlEvaluation.model_validate(data)


def try_validate_control_evaluation(
    data: dict[str, Any],
) -> Tuple[ControlEvaluation | None, ValidationError | None]:
    try:
        return ControlEvaluation.model_validate(data), None
    except ValidationError as exc:
        return None, exc


def build_pilot_summary(pilot_id: str, evaluations: List[ControlEvaluation]) -> PilotSummary:
    """Aggregates a set of ControlEvaluations into a PilotSummary.

    Pure data transformation - no scoring, no thresholds, no dashboard.
    Re-run this whenever the underlying ControlEvaluations change; the
    result is a snapshot, not a live view (see PilotSummary's docstring).
    """
    field_alignment_counts: dict[str, dict[str, int]] = {}
    traceability_counts: dict[str, int] = {}
    missing_information_counts: dict[str, int] = {}
    usefulness_counts: dict[str, int] = {}
    material_discrepancies: list[MaterialDiscrepancyRef] = []

    for evaluation in evaluations:
        for comparison in evaluation.field_comparisons:
            per_field = field_alignment_counts.setdefault(comparison.field, {})
            per_field[comparison.comparison.value] = per_field.get(comparison.comparison.value, 0) + 1

        for key, count in evaluation.traceability_summary.items():
            traceability_counts[key] = traceability_counts.get(key, 0) + count

        for key, count in evaluation.missing_information_summary.items():
            missing_information_counts[key] = missing_information_counts.get(key, 0) + count

        for key, count in evaluation.usefulness_summary.items():
            usefulness_counts[key] = usefulness_counts.get(key, 0) + count

        for discrepancy in evaluation.material_discrepancies:
            material_discrepancies.append(
                MaterialDiscrepancyRef(
                    control_id=evaluation.control_id,
                    discrepancy_id=discrepancy.discrepancy_id,
                    discrepancy_type=discrepancy.discrepancy_type,
                    description=discrepancy.description,
                )
            )

    return PilotSummary(
        pilot_id=pilot_id,
        generated_at=datetime.now(timezone.utc),
        control_ids=[e.control_id for e in evaluations],
        field_alignment_counts=field_alignment_counts,
        traceability_counts=traceability_counts,
        missing_information_counts=missing_information_counts,
        usefulness_counts=usefulness_counts,
        material_discrepancies=material_discrepancies,
        # consistency_findings and open_items_for_next_iteration are
        # reviewer-authored, not derivable from the evaluations alone - left
        # for the pilot lead to fill in on the returned object.
    )
