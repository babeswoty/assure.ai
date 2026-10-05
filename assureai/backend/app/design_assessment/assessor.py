"""Deterministic, rules-based design assessment (Prompt 3: "Design
Assessment Agent").

Reads a control's ALREADY-EXTRACTED documentation (what/who/when/why/where/
how, produced by app.transcript_extraction) plus its risk/control_objective,
and returns a DesignAssessment: completeness, relevance, and
risk/objective/control alignment dimensions, an overall
first_pass_design_conclusion, and a rationale. It never re-reads the raw
transcript - only the structured documentation already extracted from it -
and it never concludes PASS/FAIL without a concrete, citable reason. When
the evidence doesn't confidently support a conclusion, the result is
UNKNOWN rather than guessed.

No new, redundant rating enum was added. Your Prompt 3 vocabulary maps onto
the schema's existing AssessmentResult enum:

    Adequate               -> AssessmentResult.PASS
    Inadequate             -> AssessmentResult.FAIL
    Requires Human Review  -> AssessmentResult.UNKNOWN / PARTIAL / NOT_APPLICABLE
                              (all three mean "a human needs to look at this",
                              just distinguishing why - see RATING_LABELS)

Call `rating_label()` to render a result in that product-facing vocabulary.
"""
from app.schemas.racm import (
    AssessmentDimension,
    AssessmentResult,
    Control,
    DesignAssessment,
)

_CORE_FIELDS = ("what", "who", "when", "why", "where", "how")

RATING_LABELS = {
    AssessmentResult.PASS: "Adequate",
    AssessmentResult.FAIL: "Inadequate",
    AssessmentResult.UNKNOWN: "Requires Human Review",
    AssessmentResult.PARTIAL: "Requires Human Review",
    AssessmentResult.NOT_APPLICABLE: "Requires Human Review",
    AssessmentResult.NOT_ASSESSED: "Not Assessed",
}


def rating_label(result: AssessmentResult) -> str:
    """Translates the schema's AssessmentResult into the Adequate/Inadequate/
    Requires Human Review vocabulary - a display mapping, not a second enum."""
    return RATING_LABELS[result]


_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "these", "those", "it", "its", "of", "in", "on", "to", "for", "and", "or", "do",
    "does", "did", "has", "have", "had", "by", "with", "as", "not", "no", "if", "will",
}


def _content_tokens(text: str) -> set:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return {tok for tok in cleaned.split() if tok and tok not in _STOPWORDS}


def _overlap_ratio(a: set, b: set) -> float:
    """Overlap coefficient (intersection / smaller set), not Jaccard: a
    short WHY sentence being well-represented inside a longer risk/objective
    text is what matters here, not being penalized for the size difference
    the way a union-based Jaccard score would."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


_RELEVANCE_OVERLAP_THRESHOLD = 0.15
_ALIGNMENT_OVERLAP_THRESHOLD = 0.15

_INDEPENDENCE_REQUIRED_KEYWORDS = ("independent", "segregat", "separation of duties")
_SELF_REVIEW_SIGNALS = (
    "i'm also", "im also", "that's me too", "thats me too", "same person",
    "myself as well", "both roles", "i do both", "me too",
)


def _assess_completeness(control: Control) -> AssessmentDimension:
    doc = control.documentation
    resolved = [f for f in _CORE_FIELDS if getattr(doc, f).value]
    missing = [f for f in _CORE_FIELDS if not getattr(doc, f).value]
    count = len(resolved)
    if count == 6:
        return AssessmentDimension(
            result=AssessmentResult.PASS,
            rationale="All six control attributes (What/Who/When/Why/Where/How) are documented.",
        )
    if count >= 4:
        return AssessmentDimension(
            result=AssessmentResult.PARTIAL,
            rationale=f"{count} of 6 control attributes are documented; still missing: {', '.join(missing)}.",
        )
    return AssessmentDimension(
        result=AssessmentResult.FAIL,
        rationale=f"Only {count} of 6 control attributes are documented; missing: {', '.join(missing)}.",
    )


def _assess_relevance(control: Control, completeness: AssessmentDimension) -> AssessmentDimension:
    if completeness.result == AssessmentResult.FAIL:
        return AssessmentDimension(
            result=AssessmentResult.UNKNOWN,
            rationale="Documentation is too incomplete to assess whether the documented activity relates to the stated risk.",
        )
    doc = control.documentation
    control_text = " ".join(filter(None, [doc.what.value, doc.how.value, doc.control_description]))
    risk_text = f"{control.risk.risk_description} {control.control_objective or ''}"
    overlap = _overlap_ratio(_content_tokens(control_text), _content_tokens(risk_text))
    if overlap >= _RELEVANCE_OVERLAP_THRESHOLD:
        return AssessmentDimension(
            result=AssessmentResult.PASS,
            rationale=f"The documented activity shares clear subject-matter overlap with the stated risk/objective (term overlap ratio {overlap:.2f}).",
        )
    return AssessmentDimension(
        result=AssessmentResult.UNKNOWN,
        rationale=(
            f"Term overlap between the documented activity and the stated risk/objective is low "
            f"(ratio {overlap:.2f}) - this may simply reflect differing wording rather than an actual "
            "relevance gap; human judgement is needed."
        ),
    )


def _assess_alignment(control: Control, completeness: AssessmentDimension) -> AssessmentDimension:
    if completeness.result == AssessmentResult.FAIL:
        return AssessmentDimension(
            result=AssessmentResult.UNKNOWN,
            rationale="Documentation is too incomplete to assess risk/objective/control alignment.",
        )

    doc = control.documentation
    objective_and_risk = f"{control.control_objective or ''} {control.risk.risk_description}".lower()
    who_value = doc.who.value or ""
    if any(kw in objective_and_risk for kw in _INDEPENDENCE_REQUIRED_KEYWORDS):
        who_lower = who_value.lower()
        if any(sig in who_lower for sig in _SELF_REVIEW_SIGNALS):
            return AssessmentDimension(
                result=AssessmentResult.FAIL,
                rationale=(
                    "The control objective/risk requires independence between roles, but the documented "
                    f"WHO indicates the same individual performs both: \"{who_value}\""
                ),
            )

    if not doc.why.value:
        return AssessmentDimension(
            result=AssessmentResult.UNKNOWN,
            rationale="WHY was not established, so alignment between the activity and the stated risk/objective cannot be assessed.",
        )
    overlap = _overlap_ratio(_content_tokens(doc.why.value), _content_tokens(objective_and_risk))
    if overlap >= _ALIGNMENT_OVERLAP_THRESHOLD:
        return AssessmentDimension(
            result=AssessmentResult.PASS,
            rationale=f"The stated WHY shares clear subject-matter overlap with the risk/objective (term overlap ratio {overlap:.2f}).",
        )
    return AssessmentDimension(
        result=AssessmentResult.UNKNOWN,
        rationale=(
            f"Term overlap between the stated WHY and the risk/objective is low (ratio {overlap:.2f}); "
            "human judgement is needed to confirm alignment."
        ),
    )


def assess_control_design(control: Control) -> DesignAssessment:
    completeness = _assess_completeness(control)
    relevance = _assess_relevance(control, completeness)
    alignment = _assess_alignment(control, completeness)

    if completeness.result != AssessmentResult.PASS:
        conclusion = AssessmentResult.UNKNOWN
        rationale = f"Design adequacy cannot be concluded: {completeness.rationale}"
    elif alignment.result == AssessmentResult.FAIL:
        conclusion = AssessmentResult.FAIL
        rationale = alignment.rationale
    elif relevance.result == AssessmentResult.PASS and alignment.result == AssessmentResult.PASS:
        conclusion = AssessmentResult.PASS
        rationale = (
            "Documentation is complete, the activity is relevant to the stated risk, and no "
            "independence or alignment issue was detected."
        )
    else:
        conclusion = AssessmentResult.UNKNOWN
        rationale = (
            "Documentation is complete, but relevance and/or alignment could not be confidently "
            "confirmed from the extracted evidence; human review required."
        )

    return DesignAssessment(
        completeness=completeness,
        relevance=relevance,
        risk_objective_control_alignment=alignment,
        first_pass_design_conclusion=conclusion,
        conclusion_rationale=rationale,
    )
