"""Reusable primitives shared across the RACM master domain model.

These types are intentionally generic (not RACM-specific) so later phases
(walkthrough extraction, design assessment, gap assessment, recommendations)
can all reuse the same traceability and missing-information building blocks
instead of inventing their own per-agent shapes.
"""
import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


def ensure_unique_ids(ids: list[str], label: str) -> None:
    """Raises ValueError on the first duplicate id found in a list.

    Shared by the RACM schema (gap_id, question_id, ...) and the pilot
    evaluation schema (discrepancy_id, ...) so two independent writers can
    never silently collide on the same identifier.
    """
    seen: set[str] = set()
    for value in ids:
        if value in seen:
            raise ValueError(f"Duplicate id in {label}: {value!r}")
        seen.add(value)


class SourceType(str, enum.Enum):
    """Where an AI-generated statement or extracted fact came from."""

    RACM_INPUT = "racm_input"
    WALKTHROUGH_TRANSCRIPT = "walkthrough_transcript"
    POLICY_DOCUMENT = "policy_document"
    EVIDENCE_DOCUMENT = "evidence_document"
    INTERVIEW_NOTE = "interview_note"
    SYSTEM_SCREENSHOT = "system_screenshot"
    EMAIL_CORRESPONDENCE = "email_correspondence"
    PRIOR_ASSESSMENT = "prior_assessment"
    OTHER = "other"


class GenerationSource(str, enum.Enum):
    """Who/what produced the content of a section."""

    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"


class MissingInformationStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"


class SourceReference(BaseModel):
    """Points at where a piece of AI-generated or extracted content came from.

    Deliberately does not embed full document contents - only enough to
    locate and spot-check the claim (an id/name/locator and a short excerpt),
    so the master record never becomes a copy of the underlying evidence.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_type: SourceType
    source_name: str = Field(min_length=1)
    locator: Optional[str] = Field(
        default=None,
        description="Where within the source, e.g. page 4, cell B12, transcript timestamp 00:14:32.",
    )
    excerpt: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Short supporting quote only - never the full source document.",
    )


class MissingInformation(BaseModel):
    """Represents a fact that could not be determined, instead of guessing.

    `field` uses a dotted path relative to the enclosing Control, e.g.
    "documentation.who" or "gap_assessment.gaps[0].root_cause_category", so a
    reviewer or downstream agent can locate exactly what is unresolved.
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    follow_up_question: Optional[str] = None
    status: MissingInformationStatus = MissingInformationStatus.OPEN


class GenerationMetadata(BaseModel):
    """Lightweight provenance stamp for a section of the record.

    Attached at the section level (documentation / design_assessment / each
    gap) rather than on every leaf field, so it stays cheap to produce while
    still answering "did a human or the AI write this?". Whether the record
    as a whole has been reviewed is answered exclusively by
    Control.review.decision - deliberately not duplicated here, so there is
    only one place that can say "this is approved".
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    generated_by: GenerationSource = GenerationSource.AI
    generated_at: Optional[datetime] = None
    model_or_author: Optional[str] = Field(
        default=None,
        description="e.g. 'claude-sonnet-5' for AI output, or a reviewer's name/id for human edits.",
    )
