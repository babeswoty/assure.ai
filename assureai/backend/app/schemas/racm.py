"""Canonical RACM master-output domain model.

One control has exactly one RACMControlRecord. Every stage of the pipeline

    RACM input -> walkthrough questions -> transcript extraction
    -> structured control documentation -> design assessment
    -> RFI/testing procedure drafts -> gap assessment
    -> recommendations/actions -> human review

reads this same record and enriches its own section(s) in place, rather than
returning an incompatible shape. See ../../../README.md for how a given
agent should read and write it.
"""
import enum
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import (
    GenerationMetadata,
    MissingInformation,
    SourceReference,
    ensure_unique_ids,
)

SCHEMA_VERSION = "1.0"


# ---------- Assessment / review / gap enums (constrained, finite state) ----------


class AssessmentResult(str, enum.Enum):
    """Shared result enum for design-assessment dimensions and the overall
    first-pass design conclusion.

    NOT_ASSESSED, UNKNOWN, and NOT_APPLICABLE are kept distinct from each
    other and from PASS/FAIL/PARTIAL:
    - NOT_ASSESSED: the assessment has not been attempted yet (the default).
    - UNKNOWN: it was attempted but the available evidence was insufficient
      (including evidence that is simply unavailable) to reach a conclusion.
    - NOT_APPLICABLE: the dimension does not apply to this control, which is
      a distinct, legitimate conclusion - never modeled as PASS or FAIL.
    """

    NOT_ASSESSED = "not_assessed"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class GapType(str, enum.Enum):
    DESIGN_GAP = "design_gap"
    DOCUMENTATION_GAP = "documentation_gap"
    OPERATING_EFFECTIVENESS_GAP = "operating_effectiveness_gap"
    MONITORING_GAP = "monitoring_gap"
    OTHER = "other"


class GapImpact(str, enum.Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RemediationAlignment(str, enum.Enum):
    """Whether the proposed action actually addresses the identified gap."""

    NOT_ASSESSED = "not_assessed"
    YES = "yes"
    PARTIAL = "partial"
    NO = "no"


class ReviewDecision(str, enum.Enum):
    NOT_REVIEWED = "not_reviewed"
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


class WalkthroughQuestionCategory(str, enum.Enum):
    """What kind of information a walkthrough question is trying to elicit.

    The six core categories cover the What/Who/When/Why/Where/How of a
    control. The remaining five are kept deliberately narrow - only used
    when a control's context genuinely calls for them (see
    app.question_generation) - rather than added for completeness.
    """

    WHAT = "what"
    WHO = "who"
    WHEN = "when"
    WHY = "why"
    WHERE = "where"
    HOW = "how"
    EVIDENCE = "evidence"
    REVIEW = "review"
    APPROVAL = "approval"
    EXCEPTION_HANDLING = "exception_handling"
    SYSTEM = "system"


# ---------- Engagement / risk ----------


class Engagement(BaseModel):
    """`process`/`subprocess` keep their existing meaning (e.g. "User Access
    Management" / "Provisioning"). `opco`/`area`/`mega_process` are the
    broader levels of a client's RACM hierarchy sitting above them (e.g.
    OpCo "Acme Corp (South Africa)" > Area "Information Technology" >
    Mega Process "IT General Controls" > Process "User Access Management"
    > Sub-process "Provisioning") - added because a real client RACM
    tracker carries this full hierarchy, not just two levels."""

    model_config = ConfigDict(extra="forbid")

    engagement_id: str = Field(min_length=1)
    client: str = Field(min_length=1)
    opco: Optional[str] = Field(
        default=None,
        description="Operating company / country / market entity within the client group, e.g. 'Acme Corp (South Africa)'.",
    )
    area: Optional[str] = None
    mega_process: Optional[str] = None
    process: str = Field(min_length=1)
    subprocess: Optional[str] = None


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_id: str = Field(min_length=1)
    risk_description: str = Field(min_length=1)


# ---------- Walkthrough ----------


class WalkthroughQuestion(BaseModel):
    """One walkthrough question, from generation through to its eventual
    answer.

    `category`/`purpose`/`source_fields`/`required` are populated by the
    question-generation stage (app.question_generation) for explainability -
    which RACM field(s) prompted this question, and why. They are optional
    so a question added directly by a human (with no generation metadata)
    remains a valid WalkthroughQuestion. `answer`/`source_references` are
    filled in later, by transcript extraction.
    """

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    question_text: str = Field(min_length=1)
    category: Optional[WalkthroughQuestionCategory] = None
    purpose: Optional[str] = None
    source_fields: List[str] = Field(
        default_factory=list,
        description="Dotted paths into the RACM control/engagement that prompted this question, e.g. 'control.control_objective'.",
    )
    required: bool = True
    answer: Optional[str] = None
    source_references: List[SourceReference] = Field(default_factory=list)


class Walkthrough(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: List[WalkthroughQuestion] = Field(default_factory=list)
    source_references: List[SourceReference] = Field(default_factory=list)
    metadata: GenerationMetadata = Field(default_factory=GenerationMetadata)

    @model_validator(mode="after")
    def _unique_question_ids(self) -> "Walkthrough":
        ensure_unique_ids(
            [q.question_id for q in self.questions], "walkthrough.questions[].question_id"
        )
        return self


# ---------- Documentation (What/Who/When/Why/Where/How) ----------


class DocumentedAttribute(BaseModel):
    """One documented fact (e.g. the "who" of a control) together with the
    evidence it was drawn from.

    Each of the six control attributes gets its own source_references
    instead of sharing one document-level list, because they are commonly
    extracted from different parts of a transcript (or different documents
    entirely) and a reviewer needs to know which evidence backs which
    specific fact.

    `value` defaults to None (not "") so "not yet known" can be told apart
    from "confirmed to be empty" - absence should be recorded via a
    MissingInformation entry on the enclosing ControlDocumentation, never
    inferred or guessed.
    """

    model_config = ConfigDict(extra="forbid")

    value: Optional[str] = None
    source_references: List[SourceReference] = Field(default_factory=list)


class ControlDocumentation(BaseModel):
    """Structured control documentation extracted from the walkthrough."""

    model_config = ConfigDict(extra="forbid")

    what: DocumentedAttribute = Field(default_factory=DocumentedAttribute)
    who: DocumentedAttribute = Field(default_factory=DocumentedAttribute)
    when: DocumentedAttribute = Field(default_factory=DocumentedAttribute)
    why: DocumentedAttribute = Field(default_factory=DocumentedAttribute)
    where: DocumentedAttribute = Field(default_factory=DocumentedAttribute)
    how: DocumentedAttribute = Field(default_factory=DocumentedAttribute)
    # Synthesized narrative summarizing the six attributes above; its
    # traceability is inherited transitively from theirs, so it is not
    # independently sourced.
    control_description: Optional[str] = None

    missing_information: List[MissingInformation] = Field(default_factory=list)
    follow_up_prompts: List[str] = Field(default_factory=list)
    # General/overall references for this section (e.g. "the whole
    # walkthrough transcript"), distinct from each attribute's own refs above.
    source_references: List[SourceReference] = Field(default_factory=list)
    metadata: GenerationMetadata = Field(default_factory=GenerationMetadata)


# ---------- Design assessment ----------


class AssessmentDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: AssessmentResult = AssessmentResult.NOT_ASSESSED
    rationale: Optional[str] = None
    source_references: List[SourceReference] = Field(default_factory=list)


class RFIItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfi_id: str = Field(min_length=1)
    request: str = Field(min_length=1)
    rationale: Optional[str] = None
    source_references: List[SourceReference] = Field(default_factory=list)


class TestingProcedure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    procedure_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    steps: List[str] = Field(default_factory=list)
    source_references: List[SourceReference] = Field(default_factory=list)


class DesignAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completeness: AssessmentDimension = Field(default_factory=AssessmentDimension)
    relevance: AssessmentDimension = Field(default_factory=AssessmentDimension)
    risk_objective_control_alignment: AssessmentDimension = Field(
        default_factory=AssessmentDimension
    )

    first_pass_design_conclusion: AssessmentResult = AssessmentResult.NOT_ASSESSED
    conclusion_rationale: Optional[str] = None

    rfi_items: List[RFIItem] = Field(default_factory=list)
    testing_procedures: List[TestingProcedure] = Field(default_factory=list)
    metadata: GenerationMetadata = Field(default_factory=GenerationMetadata)

    @model_validator(mode="after")
    def _unique_item_ids(self) -> "DesignAssessment":
        ensure_unique_ids(
            [i.rfi_id for i in self.rfi_items], "design_assessment.rfi_items[].rfi_id"
        )
        ensure_unique_ids(
            [p.procedure_id for p in self.testing_procedures],
            "design_assessment.testing_procedures[].procedure_id",
        )
        return self


# ---------- Gap assessment ----------


class Gap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_id: str = Field(min_length=1)
    gap_type: GapType
    gap_title: str = Field(min_length=1)
    gap_description: str = Field(min_length=1)
    root_cause_category: Optional[str] = None
    impact: GapImpact = GapImpact.UNKNOWN
    recommendation: Optional[str] = None
    proposed_action: Optional[str] = None
    action_addresses_gap: RemediationAlignment = RemediationAlignment.NOT_ASSESSED
    # Entered by the human reviewer against the drafted gap - never
    # inferred or defaulted by any agent, so both stay None until a
    # reviewer actually fills them in.
    action_owner: Optional[str] = None
    action_date: Optional[date] = None
    source_references: List[SourceReference] = Field(default_factory=list)
    metadata: GenerationMetadata = Field(default_factory=GenerationMetadata)


class GapAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gaps: List[Gap] = Field(default_factory=list)
    # For unknowns that aren't specific to one gap, e.g. "root cause could
    # not be determined for any finding because the change-management log
    # was unavailable" - mirrors ControlDocumentation.missing_information.
    missing_information: List[MissingInformation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_gap_ids(self) -> "GapAssessment":
        ensure_unique_ids([g.gap_id for g in self.gaps], "gap_assessment.gaps[].gap_id")
        return self


# ---------- Human review ----------


class ControlReview(BaseModel):
    """The human decision gate. AI-generated conclusions above (design_assessment,
    gap_assessment) remain drafts until a reviewer records a decision here -
    nothing in this schema promotes them to "approved" automatically.
    """

    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision = ReviewDecision.NOT_REVIEWED
    reviewer_comments: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    human_approval_required: bool = True

    @model_validator(mode="after")
    def _decision_requires_a_complete_audit_trail(self) -> "ControlReview":
        if self.decision == ReviewDecision.NOT_REVIEWED:
            return self

        if not self.reviewer_id:
            raise ValueError(
                "reviewer_id is required once a review decision has been recorded "
                f"(decision={self.decision.value!r})"
            )
        if not self.reviewed_at:
            raise ValueError(
                "reviewed_at is required once a review decision has been recorded "
                f"(decision={self.decision.value!r})"
            )
        if self.decision in (
            ReviewDecision.NEEDS_REVISION,
            ReviewDecision.REJECTED,
        ) and not (self.reviewer_comments and self.reviewer_comments.strip()):
            raise ValueError(
                "reviewer_comments is required when decision is "
                f"{self.decision.value!r}, so the requested changes or rejection "
                "reason is recorded"
            )
        return self


# ---------- Control / master record ----------


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_id: str = Field(min_length=1)
    control_title: str = Field(min_length=1)
    control_reference: Optional[str] = Field(
        default=None,
        description="Human-facing control code from the RACM tracker (e.g. 'ITGC-UAM-01') - distinct from control_id, which is this system's own identifier.",
    )
    risk: Risk
    control_objective: Optional[str] = None
    suggested_control_description: Optional[str] = Field(
        default=None,
        description=(
            "The control description exactly as suggested/written in the RACM tracker, "
            "before any walkthrough - source/input data. Distinct from "
            "documentation.control_description, which is synthesized by AI from the "
            "walkthrough transcript; the two must never be conflated."
        ),
    )

    # Pre-walkthrough RACM-tracker attributes, when the RACM input provides
    # them. Kept as free text rather than enums: real-world values are more
    # varied than a closed set would comfortably hold (e.g. "per event",
    # "IT-dependent manual"), and over-constraining them risks rejecting
    # legitimate input. Absence of any of these should be treated as
    # genuinely unknown, not as an invented default.
    control_frequency: Optional[str] = None
    control_nature: Optional[str] = None
    control_type: Optional[str] = None
    expected_evidence: Optional[str] = None
    suggested_test_procedures_tod: Optional[str] = Field(
        default=None,
        description=(
            "RACM-suggested test-of-design procedure - source data. Distinct from "
            "design_assessment.testing_procedures, which is drafted later in the "
            "pipeline, during design assessment."
        ),
    )
    suggested_test_procedures_toe: Optional[str] = Field(
        default=None,
        description="RACM-suggested test-of-operating-effectiveness procedure - source data, same distinction as suggested_test_procedures_tod.",
    )

    walkthrough: Walkthrough = Field(default_factory=Walkthrough)
    documentation: ControlDocumentation = Field(default_factory=ControlDocumentation)
    design_assessment: DesignAssessment = Field(default_factory=DesignAssessment)
    gap_assessment: GapAssessment = Field(default_factory=GapAssessment)
    review: ControlReview = Field(default_factory=ControlReview)


class RACMControlRecord(BaseModel):
    """The canonical, shared master record for a single control."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    engagement: Engagement
    control: Control
