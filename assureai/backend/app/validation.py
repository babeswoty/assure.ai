"""Runtime validation entry points for the RACM master record.

Every agent in the pipeline should read and write the record through these
functions (or by calling RACMControlRecord.model_validate(...) /
.model_dump(mode="json") directly) rather than hand-rolling dict access, so
malformed or partially-invented data is rejected at the boundary instead of
silently propagating downstream.
"""
from typing import Any, Literal, Tuple

from pydantic import ValidationError

from app.schemas.racm import RACMControlRecord


def validate_record(data: dict[str, Any]) -> RACMControlRecord:
    """Validate a raw dict against the canonical schema.

    Raises pydantic.ValidationError if the data is invalid.
    """
    return RACMControlRecord.model_validate(data)


def try_validate_record(
    data: dict[str, Any],
) -> Tuple[RACMControlRecord | None, ValidationError | None]:
    """Non-raising variant: returns (record, None) or (None, error)."""
    try:
        return RACMControlRecord.model_validate(data), None
    except ValidationError as exc:
        return None, exc


ControlSection = Literal[
    "walkthrough", "documentation", "design_assessment", "gap_assessment", "review"
]


def merge_control_section(
    record: RACMControlRecord, section: ControlSection, data: dict[str, Any]
) -> RACMControlRecord:
    """Return a new record with only `control.<section>` replaced.

    This is the safe way for a single-purpose agent to write its output back
    into the shared record. It always starts from the *current* full record
    and only swaps out the one section the caller owns, so a design
    assessment agent (for example) can never accidentally wipe an earlier
    stage's walkthrough or documentation by constructing a fresh,
    partially-populated Control from scratch - which would otherwise
    validate successfully, since every other section has a safe default.

    `control_id`, `control_title`, `risk`, `control_objective`, and
    `engagement` are never touched here - they are set once when the record
    is created from the RACM input and are not owned by any enrichment stage.
    """
    current = record.model_dump(mode="json")
    current["control"][section] = data
    return RACMControlRecord.model_validate(current)
