"""Output contract for walkthrough-question generation.

Deliberately thin: a WalkthroughQuestionSet is just a control_id plus the
list of racm.WalkthroughQuestion this stage produced. It is NOT a
RACMControlRecord and does not embed one - see app.validation.merge_control_section
for how a caller folds this result back into a control's master record.
"""
from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ensure_unique_ids
from app.schemas.racm import WalkthroughQuestion


class WalkthroughQuestionSet(BaseModel):
    """The result of generating walkthrough questions for one control.

    control_id is carried once here rather than on every individual
    WalkthroughQuestion - the canonical schema already avoids duplicating a
    control's identifier onto its own nested children (see Walkthrough,
    Gap, etc.), and doing the same here keeps this result consistent with
    that convention.
    """

    model_config = ConfigDict(extra="forbid")

    control_id: str = Field(min_length=1)
    questions: List[WalkthroughQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_question_ids(self) -> "WalkthroughQuestionSet":
        ensure_unique_ids([q.question_id for q in self.questions], "questions[].question_id")
        return self
