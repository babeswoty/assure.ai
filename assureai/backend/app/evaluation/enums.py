"""Constrained result vocabularies for pilot evaluation.

Kept separate from app.schemas.racm's enums because these describe a
*comparison* between an AssureAI draft and a reviewer's reference conclusion
- a different concept from the RACM record's own assessment states, even
where the words sound similar.
"""
import enum


class FieldComparisonResult(str, enum.Enum):
    """How closely an AssureAI-drafted field matches the reviewer's reference
    value, judged on substantive meaning rather than wording.

    Four categories are sufficient for a pilot: the two "clean" ends
    (ALIGNED, NOT_ALIGNED), one middle ground for "same idea, incomplete or
    partly wrong" (PARTIALLY_ALIGNED), and an explicit escape hatch for when
    comparison itself isn't meaningful (NOT_ASSESSABLE) - e.g. the reviewer
    never produced a reference value for this field, or the field is
    structurally empty on both sides. A finer scale (e.g. splitting
    NOT_ALIGNED by severity) is not needed here because severity is already
    captured independently via `FieldComparison.material_discrepancy` and,
    for the worst cases, a linked MaterialDiscrepancy record.
    """

    ALIGNED = "aligned"
    PARTIALLY_ALIGNED = "partially_aligned"
    NOT_ALIGNED = "not_aligned"
    NOT_ASSESSABLE = "not_assessable"


class TraceabilityAssessmentResult(str, enum.Enum):
    """Whether a significant AI-generated statement is actually backed by
    the evidence it cites.

    This is a recommended improvement on a plain
    SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED/INCORRECT_REFERENCE/NOT_APPLICABLE
    scale: it adds NO_REFERENCE as its own value, distinct from UNSUPPORTED.
    "AssureAI drew a conclusion and cited nothing" (NO_REFERENCE) is a
    different, generally more serious, failure than "AssureAI cited a real,
    correctly-attributed source that simply doesn't back the claim"
    (UNSUPPORTED) - conflating them would hide which problem actually
    occurred (a citation-discipline gap vs. a comprehension gap).
    """

    NO_REFERENCE = "no_reference"
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    INCORRECT_REFERENCE = "incorrect_reference"
    NOT_APPLICABLE = "not_applicable"


class MissingInfoDetectionResult(str, enum.Enum):
    """Compares what AssureAI flagged as missing against what the reviewer
    determines was actually missing.

    Deliberately NOT auto-derived from two booleans (did AssureAI flag it /
    did the reviewer say it's missing): NOT_DETERMINABLE exists precisely
    for cases a simple truth table can't resolve (e.g. the evidence
    available to the pilot evaluator doesn't allow a confident call either
    way), and even TRUE_POSITIVE/FALSE_NEGATIVE/FALSE_POSITIVE calls can
    require judgement about whether AssureAI's flagged field and the
    reviewer's concern are actually the same thing. True negatives (neither
    side flags anything, and nothing is in fact missing) are not recorded
    as individual comparisons - see MissingInformationComparison's docstring.
    """

    TRUE_POSITIVE = "true_positive"
    FALSE_NEGATIVE = "false_negative"
    FALSE_POSITIVE = "false_positive"
    NOT_DETERMINABLE = "not_determinable"


class UsefulnessRating(str, enum.Enum):
    """Whether a drafted output gave the reviewer a useful starting point.

    "Useful" is not "accepted unchanged": MINOR_AMENDMENT and even
    SUBSTANTIAL_AMENDMENT still count as the draft having provided value,
    just with more reviewer rework. Only REJECT_REPLACE means the draft
    itself was not a useful starting point (reviewer wrote it from scratch).
    """

    ACCEPT_AS_IS = "accept_as_is"
    MINOR_AMENDMENT = "minor_amendment"
    SUBSTANTIAL_AMENDMENT = "substantial_amendment"
    REJECT_REPLACE = "reject_replace"
    NOT_ASSESSABLE = "not_assessable"


class MaterialDiscrepancyType(str, enum.Enum):
    """Categorizes a serious, individually-tracked failure.

    These are never rolled up into a single score - see
    MaterialDiscrepancy's docstring and the Material Discrepancy Framework
    section of PILOT_EVALUATION_FRAMEWORK.md.
    """

    UNSUPPORTED_CONCLUSION = "unsupported_conclusion"
    INCORRECT_SOURCE_ATTRIBUTION = "incorrect_source_attribution"
    MATERIAL_ATTRIBUTE_OMITTED = "material_attribute_omitted"
    MISSING_INFO_NOT_DETECTED = "missing_info_not_detected"
    CONCLUSION_DESPITE_INSUFFICIENT_EVIDENCE = "conclusion_despite_insufficient_evidence"
    MATERIALLY_DIFFERENT_DESIGN_CONCLUSION = "materially_different_design_conclusion"
    FABRICATED_SOURCE_REFERENCE = "fabricated_source_reference"
    SIGNIFICANT_GAP_MISSED = "significant_gap_missed"
    RECOMMENDATION_DOES_NOT_ADDRESS_GAP = "recommendation_does_not_address_gap"
    OTHER = "other"


class EvaluationMethod(str, enum.Enum):
    """How a given evaluation dimension/item is (or can be) evaluated."""

    AUTOMATIC = "automatic"
    HUMAN_REVIEW = "human_review"
    BOTH = "both"


class PilotEvaluationDimension(str, enum.Enum):
    """The five pilot evaluation areas, for tagging which dimensions a given
    pilot fixture/scenario is designed to exercise (see
    assureai/PILOT_EVALUATION_FRAMEWORK.md)."""

    QUALITY = "quality"
    CONSISTENCY = "consistency"
    TRACEABILITY = "traceability"
    MISSING_INFORMATION_DETECTION = "missing_information_detection"
    USEFULNESS = "usefulness"
