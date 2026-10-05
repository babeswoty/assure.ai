"""Pilot fixture-pack models: the manifest and expected-reference shape used
by assureai/pilot/ test data.

These are deliberately NOT part of the canonical RACM or evaluation schemas
- they describe test fixtures (a manifest of cases, and a ground-truth
"what an experienced reviewer would conclude" reference per case), not
production data. Where a concept already exists in the canonical schemas
(SourceReference, MissingInformation, AssessmentResult, GapType), it is
reused directly rather than re-invented.
"""
import enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import MissingInformation, SourceReference, ensure_unique_ids
from app.schemas.racm import AssessmentResult, GapType
from app.evaluation.enums import PilotEvaluationDimension


class PilotScenario(str, enum.Enum):
    """The behaviours this pilot fixture pack is designed to exercise."""

    WELL_DOCUMENTED = "well_documented"
    INCOMPLETE = "incomplete"
    DESIGN_ISSUE = "design_issue"
    POTENTIAL_GAP = "potential_gap"
    INSUFFICIENT_INFORMATION = "insufficient_information"


# ---------- Expected reviewer reference ----------


class ExpectedAttribute(BaseModel):
    """Ground truth for one of the six control attributes (What/Who/When/
    Why/Where/How), as an experienced reviewer would read it from the
    synthetic source material - not what AssureAI is expected to output.

    `value=None` means the source material genuinely does not establish
    this attribute; `note` explains why, and there must be no
    `ExpectedTraceabilityEntry` for this field in that case (enforced by
    ExpectedReference's validator) - you cannot cite support for a fact
    that was never determined.
    """

    model_config = ConfigDict(extra="forbid")

    value: Optional[str] = None
    note: Optional[str] = Field(
        default=None, description="Why value is None, when it is."
    )


class ExpectedTraceabilityEntry(BaseModel):
    """Pairs a control field with the exact source that grounds its expected
    value, reusing SourceReference rather than inventing a citation shape."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, description="Dotted path, e.g. 'documentation.who'.")
    source: SourceReference


class ExpectedAssessmentDimension(BaseModel):
    """Ground truth for one design-assessment dimension, reusing the
    canonical AssessmentResult enum so the fixture's expectations are
    expressed in the same vocabulary the live system will eventually use."""

    model_config = ConfigDict(extra="forbid")

    result: AssessmentResult
    rationale: str = Field(min_length=1)
    source_locator: Optional[str] = None


class ExpectedDesignConclusion(str, enum.Enum):
    """Ground truth for the overall design conclusion a reviewer would reach.

    Distinct from racm.AssessmentResult: this describes what a REVIEWER's
    ground-truth conclusion for the fixture is, including the case where no
    conclusion should be drawn at all. INSUFFICIENT_INFORMATION is kept as
    its own explicit member (not reused from AssessmentResult.UNKNOWN)
    because the task defining this fixture pack calls for that exact,
    unambiguous token when a scenario intentionally lacks enough
    information - keeping it distinct avoids conflating "the reviewer's
    ground truth says no conclusion is possible" with "the live system's
    own assessment enum happened to have a matching value."
    """

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class ExpectedGapIndicator(BaseModel):
    """Ground truth for whether the synthetic facts support a gap, for
    forward compatibility with the not-yet-built gap-assessment agent.

    Only ever set when the synthetic material genuinely and unambiguously
    supports it (per the fixture-authoring rule: never establish an
    expected gap the facts don't support).
    """

    model_config = ConfigDict(extra="forbid")

    expected: bool = False
    gap_type: Optional[GapType] = None
    description: Optional[str] = None
    source_locator: Optional[str] = None


class ExpectedReference(BaseModel):
    """The ground-truth reviewer reference for one pilot case.

    This is NOT the AI output, and not a RACMControlRecord - it is what we
    expect an experienced reviewer to recognise from the synthetic facts,
    used later to score an actual AssureAI draft against (see
    app.evaluation.models.FieldComparison / TraceabilityAssessment /
    MissingInformationComparison, which this reference is designed to be
    compared through).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    control_id: str = Field(min_length=1)

    expected_what: ExpectedAttribute = Field(default_factory=ExpectedAttribute)
    expected_who: ExpectedAttribute = Field(default_factory=ExpectedAttribute)
    expected_when: ExpectedAttribute = Field(default_factory=ExpectedAttribute)
    expected_why: ExpectedAttribute = Field(default_factory=ExpectedAttribute)
    expected_where: ExpectedAttribute = Field(default_factory=ExpectedAttribute)
    expected_how: ExpectedAttribute = Field(default_factory=ExpectedAttribute)

    expected_missing_information: List[MissingInformation] = Field(default_factory=list)
    expected_traceability: List[ExpectedTraceabilityEntry] = Field(default_factory=list)

    design_conclusion_determinable: bool
    expected_design_conclusion: ExpectedDesignConclusion
    expected_design_rationale: Optional[str] = None

    expected_risk_objective_control_alignment: Optional[ExpectedAssessmentDimension] = None
    expected_gap_indicator: Optional[ExpectedGapIndicator] = None

    reviewer_notes: Optional[str] = None

    @model_validator(mode="after")
    def _determinability_matches_conclusion(self) -> "ExpectedReference":
        is_insufficient = self.expected_design_conclusion == ExpectedDesignConclusion.INSUFFICIENT_INFORMATION
        if self.design_conclusion_determinable and is_insufficient:
            raise ValueError(
                "design_conclusion_determinable=True is inconsistent with "
                "expected_design_conclusion=INSUFFICIENT_INFORMATION"
            )
        if not self.design_conclusion_determinable and not is_insufficient:
            raise ValueError(
                "design_conclusion_determinable=False requires "
                "expected_design_conclusion=INSUFFICIENT_INFORMATION"
            )
        return self

    @model_validator(mode="after")
    def _no_traceability_without_a_determined_value(self) -> "ExpectedReference":
        attribute_by_field = {
            "documentation.what": self.expected_what,
            "documentation.who": self.expected_who,
            "documentation.when": self.expected_when,
            "documentation.why": self.expected_why,
            "documentation.where": self.expected_where,
            "documentation.how": self.expected_how,
        }
        cited_fields = {entry.field for entry in self.expected_traceability}
        for field, attribute in attribute_by_field.items():
            if field in cited_fields and attribute.value is None:
                raise ValueError(
                    f"expected_traceability cites {field!r} but its value is None - "
                    "cannot cite support for a fact that was never determined"
                )
        return self


# ---------- Manifest ----------


class PilotCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    control_id: str = Field(min_length=1)
    scenario: PilotScenario

    racm_input_path: str = Field(min_length=1)
    racm_source_extract_path: Optional[str] = None
    walkthrough_input_path: str = Field(min_length=1)
    expected_reference_path: str = Field(min_length=1)

    evaluation_dimensions: List[PilotEvaluationDimension] = Field(min_length=1)
    expected_behavior: str = Field(
        min_length=1, description="What we want to observe when AssureAI processes this case."
    )


class PilotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pilot_id: str = Field(min_length=1)
    description: Optional[str] = None
    cases: List[PilotCase] = Field(default_factory=list, min_length=1)

    @model_validator(mode="after")
    def _unique_case_and_control_ids(self) -> "PilotManifest":
        ensure_unique_ids([c.case_id for c in self.cases], "cases[].case_id")
        ensure_unique_ids([c.control_id for c in self.cases], "cases[].control_id")
        return self
