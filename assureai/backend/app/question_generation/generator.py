"""Deterministic, rules-based walkthrough-question generation.

Input: a RACM `Control` (+ optional `Engagement` for process/subprocess
context). Output: a `WalkthroughQuestionSet`. This module only produces
QUESTIONS - it never answers them, extracts anything from a transcript,
drafts a control description, or assesses design/gap/adequacy. See the
"LLM / generation architecture" note at the bottom of this file for why no
LLM is used here and what would change if one were added later.

Design shape: a fixed, ordered list of independent "rule" functions, each
inspecting the control (and, where relevant, engagement) and returning zero
or more draft questions. Fixed order + no randomness + no wall-clock data in
the questions themselves = deterministic output for a given input.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.racm import Control, Engagement, WalkthroughQuestion, WalkthroughQuestionCategory
from app.question_generation.models import WalkthroughQuestionSet

Category = WalkthroughQuestionCategory


@dataclass(frozen=True)
class _Draft:
    category: Category
    question_text: str
    purpose: str
    source_fields: List[str] = field(default_factory=list)
    required: bool = True


# ---------- keyword gating helpers ----------
# Deliberately simple substring checks over already-known RACM text (title,
# objective, risk description, process/subprocess) - never used to invent a
# fact, only to decide whether a context-specific follow-up is warranted.

_REVIEW_KEYWORDS = ("review", "reviewed", "reviewing")
_APPROVAL_KEYWORDS = ("approv", "sign-off", "sign off", "authoriz", "authoris")
_SOD_TRIGGER_KEYWORDS = _REVIEW_KEYWORDS + _APPROVAL_KEYWORDS + ("reconcil", "verif")
_IT_SYSTEM_KEYWORDS = (
    "system", "application", "platform", "software", "database", "network",
    "server", "infrastructure", "erp", "it general control", "information technology",
)


def _text_blob(*parts: Optional[str]) -> str:
    return " ".join(p for p in parts if p).lower()


def _quoted(text: str) -> str:
    """Strips a single trailing sentence-ending punctuation mark before
    quoting, so embedding RACM text mid-sentence doesn't read as '...ended.".'
    """
    return text[:-1] if text and text[-1] in ".!?" else text


def _any_keyword(text: str, keywords: tuple) -> bool:
    return any(kw in text for kw in keywords)


def _is_review_or_approval_flavoured(control: Control) -> bool:
    blob = _text_blob(control.control_title, control.control_objective)
    return _any_keyword(blob, _SOD_TRIGGER_KEYWORDS)


def _mentions_review(control: Control) -> bool:
    return _any_keyword(_text_blob(control.control_title, control.control_objective), _REVIEW_KEYWORDS)


def _mentions_approval(control: Control) -> bool:
    return _any_keyword(_text_blob(control.control_title, control.control_objective), _APPROVAL_KEYWORDS)


def _is_it_context(control: Control, engagement: Optional[Engagement]) -> bool:
    blob = _text_blob(
        control.control_title,
        control.control_objective,
        control.risk.risk_description,
        engagement.area if engagement else None,
        engagement.mega_process if engagement else None,
        engagement.process if engagement else None,
        engagement.subprocess if engagement else None,
    )
    return _any_keyword(blob, _IT_SYSTEM_KEYWORDS)


def _already_documented(control: Control, attribute: str) -> bool:
    return getattr(control.documentation, attribute).value is not None


# ---------- individual rules ----------
# Each rule returns 0+ drafts. A rule that finds the relevant fact already
# present in control.documentation skips its primary question rather than
# re-asking something already known.


def _rule_what(control: Control) -> List[_Draft]:
    if _already_documented(control, "what"):
        return []
    return [
        _Draft(
            category=Category.WHAT,
            question_text=(
                f"Please walk me through, step by step, how the control "
                f"\"{control.control_title}\" is actually carried out in practice."
            ),
            purpose="Establish what activity is actually performed, in the control owner's own words, before any conclusion is drawn about the control's design.",
            source_fields=["control.control_title"],
        )
    ]


def _rule_who(control: Control) -> List[_Draft]:
    drafts: List[_Draft] = []
    if not _already_documented(control, "who"):
        drafts.append(
            _Draft(
                category=Category.WHO,
                question_text=f"Who is responsible for performing the control \"{control.control_title}\"?",
                purpose="Identify the performer(s) of the control without assuming a specific role from the RACM alone.",
                source_fields=["control.control_title"],
            )
        )
    if _is_review_or_approval_flavoured(control):
        drafts.append(
            _Draft(
                category=Category.WHO,
                question_text=(
                    "If someone else prepares or initiates the item being reviewed or approved, "
                    f"who is that person or role, and are they different from whoever performs "
                    f"\"{control.control_title}\"?"
                ),
                purpose="Determine whether preparer and reviewer/approver are distinct, which matters for this control given its review/approval nature - without assuming an answer.",
                source_fields=["control.control_title", "control.control_objective"],
                required=False,
            )
        )
    return drafts


def _rule_when(control: Control) -> List[_Draft]:
    if _already_documented(control, "when"):
        return []
    if control.control_frequency:
        return [
            _Draft(
                category=Category.WHEN,
                question_text=(
                    f"The control is expected to be performed {control.control_frequency}. "
                    f"How is that {control.control_frequency} cadence monitored to ensure "
                    f"the control is actually completed each time, and what would trigger it "
                    f"outside of that schedule?"
                ),
                purpose="Confirm the stated frequency is actually monitored/enforced in practice, and capture any event-driven trigger in addition to the schedule.",
                source_fields=["control.control_frequency"],
            )
        ]
    return [
        _Draft(
            category=Category.WHEN,
            question_text="How frequently is this control performed, and what triggers its performance?",
            purpose="The RACM does not state a frequency or trigger for this control - this is needed to document When.",
            source_fields=["control.control_frequency"],
        )
    ]


def _rule_why(control: Control) -> List[_Draft]:
    if _already_documented(control, "why"):
        return []
    risk_text = _quoted(control.risk.risk_description)
    if control.control_objective:
        question = (
            f"The stated risk is: \"{risk_text}\". The stated control objective is: "
            f"\"{_quoted(control.control_objective)}\". Please explain how performing this control "
            f"addresses that risk."
        )
        source_fields = ["control.risk.risk_description", "control.control_objective"]
    else:
        question = (
            f"The stated risk is: \"{risk_text}\". What is this control intended to achieve, "
            f"and how does it address that risk?"
        )
        source_fields = ["control.risk.risk_description", "control.control_objective"]
    return [
        _Draft(
            category=Category.WHY,
            question_text=question,
            purpose="Understand the intended purpose of the activity relative to the stated risk, to support (not perform) the later design assessment.",
            source_fields=source_fields,
        )
    ]


def _rule_where(control: Control) -> List[_Draft]:
    if _already_documented(control, "where"):
        return []
    return [
        _Draft(
            category=Category.WHERE,
            question_text=(
                f"In which document, workflow, ticket, or repository is \"{control.control_title}\" "
                f"performed and/or its completion recorded?"
            ),
            purpose="The RACM does not identify a location or record-keeping mechanism for this control - needed to document Where.",
            source_fields=["control.control_title"],
        )
    ]


def _rule_system(control: Control, engagement: Optional[Engagement]) -> List[_Draft]:
    if not _is_it_context(control, engagement):
        return []
    return [
        _Draft(
            category=Category.SYSTEM,
            question_text=(
                f"Which system, application, or platform is used to perform or enforce "
                f"\"{control.control_title}\"?"
            ),
            purpose="This control sits within an IT-related process/risk context, so the specific system or platform involved is relevant beyond just where records are filed.",
            source_fields=[
                "engagement.area",
                "engagement.mega_process",
                "engagement.process",
                "engagement.subprocess",
                "control.risk.risk_description",
            ],
            required=False,
        )
    ]


def _rule_how(control: Control) -> List[_Draft]:
    if _already_documented(control, "how"):
        return []
    return [
        _Draft(
            category=Category.HOW,
            question_text=f"What are the specific steps performed to carry out \"{control.control_title}\"?",
            purpose="Capture the actual mechanics of the control, not just what it is called.",
            source_fields=["control.control_title"],
        )
    ]


def _rule_exception_handling(control: Control) -> List[_Draft]:
    return [
        _Draft(
            category=Category.EXCEPTION_HANDLING,
            question_text=(
                f"What happens when performing \"{control.control_title}\" identifies an exception "
                f"or an item that does not meet expectations?"
            ),
            purpose="Exception handling is rarely captured by a RACM's summary description but materially affects how the control actually operates.",
            source_fields=["control.control_title"],
            required=False,
        )
    ]


def _rule_evidence(control: Control) -> List[_Draft]:
    if control.expected_evidence:
        question = (
            f"The RACM indicates expected evidence of: \"{_quoted(control.expected_evidence)}\". "
            f"What evidence is actually retained in practice to demonstrate that "
            f"\"{control.control_title}\" was performed, and where is it stored?"
        )
    else:
        question = (
            f"What evidence is retained to demonstrate that \"{control.control_title}\" was "
            f"performed, and where is it stored?"
        )
    return [
        _Draft(
            category=Category.EVIDENCE,
            question_text=question,
            purpose="Evidence of performance is central to whether this control can later be tested, and is not assumed from the RACM's description alone.",
            source_fields=["control.expected_evidence", "control.control_title"],
        )
    ]


def _rule_review(control: Control) -> List[_Draft]:
    if not _mentions_review(control):
        return []
    return [
        _Draft(
            category=Category.REVIEW,
            question_text=(
                f"What specifically does the reviewer check or verify before concluding that "
                f"the review in \"{control.control_title}\" is complete?"
            ),
            purpose="The control's own description signals a review step - clarify what substantively happens during that review, not just that one occurs.",
            source_fields=["control.control_title", "control.control_objective"],
            required=False,
        )
    ]


def _rule_approval(control: Control) -> List[_Draft]:
    if not _mentions_approval(control):
        return []
    return [
        _Draft(
            category=Category.APPROVAL,
            question_text="How is the approval decision recorded and retained?",
            purpose="The control's own description signals an approval step - clarify how that approval is evidenced, distinct from how it is performed.",
            source_fields=["control.control_title", "control.control_objective"],
            required=False,
        )
    ]


_RULES_NO_ENGAGEMENT = (
    _rule_what,
    _rule_who,
    _rule_when,
    _rule_why,
    _rule_where,
    _rule_how,
    _rule_exception_handling,
    _rule_evidence,
    _rule_review,
    _rule_approval,
)


# ---------- deduplication ----------

# Small, deliberately conservative stopword list: filtered out only so that
# two questions differing mainly in filler words ("Who performs this
# control?" vs "Who is responsible for this control?") are recognized as
# asking essentially the same thing, per STEP 10's own example. Content
# words are never removed, so two substantively different questions that
# happen to share a few words still won't cross the similarity threshold.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "of", "in", "on", "to",
    "for", "and", "or", "do", "does", "did", "has", "have", "had",
}


def _normalize(text: str) -> set:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return {tok for tok in cleaned.split() if tok and tok not in _STOPWORDS}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _deduplicate(drafts: List[_Draft], threshold: float = 0.8) -> List[_Draft]:
    """Drops a draft whose question text is near-identical (by normalized
    token overlap) to an earlier draft in the SAME category. Comparing only
    within a category avoids accidentally dropping, e.g., a WHY question and
    a HOW question that happen to share several words."""
    kept: List[_Draft] = []
    kept_tokens_by_category: dict = {}
    for draft in drafts:
        tokens = _normalize(draft.question_text)
        prior = kept_tokens_by_category.get(draft.category, [])
        if any(_jaccard(tokens, other) >= threshold for other in prior):
            continue
        kept.append(draft)
        kept_tokens_by_category.setdefault(draft.category, []).append(tokens)
    return kept


# ---------- public entry point ----------


def generate_walkthrough_questions(
    control: Control, engagement: Optional[Engagement] = None
) -> WalkthroughQuestionSet:
    """Generates a deterministic, tailored set of walkthrough questions for
    one RACM control. Never answers a question, never invents a fact not
    present on `control`/`engagement`."""
    drafts: List[_Draft] = []
    for rule in _RULES_NO_ENGAGEMENT:
        drafts.extend(rule(control))
    drafts.extend(_rule_system(control, engagement))

    drafts = _deduplicate(drafts)

    questions = [
        WalkthroughQuestion(
            question_id=f"{control.control_id}-Q{i:02d}",
            question_text=draft.question_text,
            category=draft.category,
            purpose=draft.purpose,
            source_fields=draft.source_fields,
            required=draft.required,
        )
        for i, draft in enumerate(drafts, start=1)
    ]

    return WalkthroughQuestionSet(control_id=control.control_id, questions=questions)


def to_walkthrough_section(
    result: WalkthroughQuestionSet, model_or_author: str = "rules-based-generator-v1"
) -> dict:
    """Adapts a WalkthroughQuestionSet into the shape app.validation.merge_control_section
    expects for the "walkthrough" section, stamping generation provenance
    (including a fresh timestamp) at the point of merging - not inside the
    deterministic generation result itself, so generate_walkthrough_questions()
    remains pure and testable for determinism.
    """
    from datetime import datetime, timezone

    return {
        "questions": [q.model_dump(mode="json") for q in result.questions],
        "source_references": [],
        "metadata": {
            "generated_by": "ai",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_or_author": model_or_author,
        },
    }


# ---------- LLM / generation architecture note ----------
#
# This module is fully deterministic and rules-based: no LLM call, no API
# credentials, no external dependency. That is appropriate for this MVP
# foundation because walkthrough-question generation is a bounded,
# templatable task - the six W's plus a handful of conditional follow-ups -
# and a rules engine can already satisfy "tailored, not generic" by
# incorporating the control's own text (title/objective/risk/frequency/
# evidence) verbatim, while STRUCTURALLY guaranteeing it never invents a
# fact (a rule either uses a real field value, or asks an open question).
#
# If a future stage needs qualitatively more nuanced tailoring (e.g.
# reading the *content* of documentation.control_description prose to spot
# what's already implicitly answered, or generating idiomatic phrasing an
# experienced reviewer would use for an unusual control), an LLM-backed
# generator could be substituted behind the SAME public interface:
#
#   generate_walkthrough_questions(control: Control, engagement: Optional[Engagement]) -> WalkthroughQuestionSet
#
# - Structured input: the same Control (+ Engagement) Pydantic objects,
#   serialized to JSON - never free-form prose glued together by the caller.
# - Structured output: the LLM's response would be parsed and VALIDATED
#   through WalkthroughQuestionSet.model_validate(...) before being trusted -
#   a response that doesn't conform (wrong category enum value, missing
#   required field, duplicate question_id) is rejected, not silently
#   coerced.
# - Hallucination prevention/detection: every generated question's
#   `source_fields` would need to name real dotted paths that exist on the
#   input Control/Engagement (checkable automatically - a source_field that
#   doesn't resolve to an actual field is a detectable defect); the prompt
#   would explicitly forbid stating any person/system/frequency/evidence not
#   present in the input, mirroring the rules engine's own constraint; and
#   spot-checking generated questions against the pilot's expected
#   references (see PILOT_EVALUATION_FRAMEWORK.md) would need to happen
#   before this replaced the deterministic generator, not after.
#
# No LLM is added in this task. This note is a design placeholder only -
# adding a provider is a separate, explicit decision for a future task.
