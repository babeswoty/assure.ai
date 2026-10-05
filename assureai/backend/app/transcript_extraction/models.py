"""Minimal structured transcript model.

No transcript model existed in the repository. This one matches the format
the pilot fixtures already use (`[L01] Speaker: text` lines) rather than
inventing a new shape - see parser.py. Deliberately thin: a transcript is
raw source material, like racm_source_extract.json, not part of the
canonical RACM record.
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ensure_unique_ids
from app.schemas.racm import ControlDocumentation
from app.question_generation.models import WalkthroughQuestionSet


class TranscriptSegment(BaseModel):
    """One line of a transcript. `segment_id` doubles as the SourceReference
    locator once this segment is cited - e.g. segment_id "L05" is cited as
    SourceReference(locator="L05"), matching the convention already used in
    the pilot fixtures' expected_reference.json files.
    """

    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(min_length=1)
    speaker: Optional[str] = None
    text: str = Field(min_length=1)


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript_id: str = Field(min_length=1)
    control_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    segments: List[TranscriptSegment] = Field(default_factory=list, min_length=1)

    @model_validator(mode="after")
    def _unique_segment_ids(self) -> "Transcript":
        ensure_unique_ids([s.segment_id for s in self.segments], "segments[].segment_id")
        return self


class ExtractionResult(BaseModel):
    """The result of running extraction for one control against one
    transcript.

    Deliberately thin: `documentation` IS the existing canonical
    ControlDocumentation model (already the exact output contract this
    stage needs), and `questions` is the same WalkthroughQuestionSet from
    stage 1 with `.answer`/`.source_references` now filled in where the
    transcript supported an answer - preserving the WalkthroughQuestion ->
    transcript -> attribute -> SourceReference chain. No new "answer" or
    "output" model was invented. A caller writes this back into the master
    record with two app.validation.merge_control_section calls - one for
    "documentation", one for "walkthrough" - `control.review` is never
    touched here, so the record stays exactly as unreviewed as it was.
    """

    model_config = ConfigDict(extra="forbid")

    control_id: str = Field(min_length=1)
    transcript_id: str = Field(min_length=1)
    documentation: ControlDocumentation
    questions: WalkthroughQuestionSet
