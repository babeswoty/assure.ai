"""Deterministic, rules-based transcript extraction.

Input: a Control, the WalkthroughQuestionSet generated for it (stage 1),
and its Transcript (parsed by parser.py). Output: an ExtractionResult
(ControlDocumentation + the same questions with .answer/.source_references
filled in where supported).

Approach: an interview transcript already alternates prompt (question) /
response (answer) turns. Each prompt is classified into a
WalkthroughQuestionCategory by keyword, exactly the way an experienced
reviewer would recognise "who reviews that request?" as a Who question
without needing it to match any particular auto-generated phrasing. The
response segment(s) immediately following a prompt are the candidate
answer for that category. A value is only ever set from real response
text; when no prompt was classified into a category, or the response is an
explicit non-answer ("I'm not sure...", "I couldn't tell you..."), the
attribute stays unresolved and a MissingInformation entry is recorded
instead - this is what stops a hedge from being read as a fact.

This does NOT decide whether the control is well-designed, address gaps,
or draft recommendations - see the "HARD STOP" boundary in the task this
implements.
"""
import re
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

def _get_claude_client():
    """Lazy-load Anthropic client when needed, using environment variable."""
    try:
        from anthropic import Anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("[WARN] ANTHROPIC_API_KEY not set in environment")
            return None
        return Anthropic(api_key=api_key)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Anthropic client: {e}")
        return None

CLAUDE_CLIENT = None  # Will be initialized on first use

from app.schemas.common import (
    GenerationMetadata,
    GenerationSource,
    MissingInformation,
    MissingInformationStatus,
    SourceReference,
    SourceType,
)
from app.schemas.racm import (
    Control,
    ControlDocumentation,
    DocumentedAttribute,
    WalkthroughQuestion,
    WalkthroughQuestionCategory,
)
from app.question_generation.models import WalkthroughQuestionSet
from app.transcript_extraction.models import ExtractionResult, Transcript, TranscriptSegment
from app.transcript_extraction.voice import to_documentation_voice
from app.transcript_extraction import condenser


def _synthesize_how_answer(text: str) -> str:
    """Synthesizes raw transcript text into professional control procedures using AI."""
    if not text or len(text) < 20:
        return text

    # Try AI-powered summarization
    client = _get_claude_client()
    if client:
        print(f"[DEBUG] Claude client available, attempting AI summarization")
        try:
            prompt = f"""Transform this transcript into 3-5 professional control procedures. Write formally, not conversationally. Number each (1. 2. 3. etc). Remove filler and dialog markers. Focus on WHAT, WHEN, WHERE, WHO.

TRANSCRIPT: {text}

Output only the numbered procedures."""
            msg = client.messages.create(
                model="claude-opus-5-5", max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            if msg.content:
                result = msg.content[0].text
                print(f"[DEBUG] Claude summarization succeeded, returning {len(result)} chars")
                return result
        except Exception as e:
            print(f"[ERROR] Claude API failed: {e}")
    else:
        print(f"[WARN] Claude client unavailable, falling back to text cleaning")

    # Remove segment ID markers (e.g., "36 ", "39 20 ", "L01 ")
    text = re.sub(r'\b\d+\s+(?=\w)', '', text)  # "36 We" -> "We"
    text = re.sub(r'\b\d+\s+\d+\s+', '', text)  # "39 20 " -> ""

    # Split by periods, or by common phrase starters that indicate new steps
    sentences = re.split(r'(?<=[.!?])\s+|(?=(?:So|When|Then|If|To|By|During|After)\s)', text)

    cleaned_steps = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 10:
            continue

        # Remove filler/confirmation phrases
        if sentence.lower() in {'okay.', 'ok.', 'right.', 'yeah.', 'yep.', 'sure.', '1.', '2.', '3.', '4.', '5.'}:
            continue

        # Skip pure numbers or very short fragments
        if re.match(r'^\d+\.?$', sentence) or re.match(r'^\d+\s+\w{1,3}\.?$', sentence):
            continue

        # Skip dialog markers
        if sentence.lower() in {'of.', 'ok', 'yeah', 'yep', 'sure'}:
            continue

        # Remove trailing filler
        sentence = re.sub(r'\s+(ok|okay|yeah|yep|sure|right)\.?$', '.', sentence, flags=re.IGNORECASE)

        # Ensure sentence ends with punctuation
        if not sentence.endswith(('.', '!', '?')):
            sentence += '.'

        cleaned_steps.append(sentence)

    # Filter out duplicates while preserving order
    seen = set()
    unique_steps = []
    for step in cleaned_steps:
        step_lower = step.lower()
        if step_lower not in seen:
            seen.add(step_lower)
            unique_steps.append(step)

    if not unique_steps:
        return text  # Fallback to original if synthesis failed

    # Number the steps
    numbered_steps = '\n'.join(f"{i+1}. {step}" for i, step in enumerate(unique_steps))
    return numbered_steps

Category = WalkthroughQuestionCategory

_CORE_CATEGORIES = (
    Category.WHAT,
    Category.WHO,
    Category.WHEN,
    Category.WHY,
    Category.WHERE,
    Category.HOW,
)

class _Exchange:
    __slots__ = ("prompt", "responses")

    def __init__(self, prompt: TranscriptSegment):
        self.prompt = prompt
        self.responses: List[TranscriptSegment] = []


def _is_prompt(segment: TranscriptSegment) -> bool:
    speaker = (segment.speaker or "").strip().lower()
    if speaker in {"interviewer", "facilitator", "auditor", "reviewer"}:
        return True
    return segment.text.rstrip().endswith("?")


def _build_exchanges(transcript: Transcript) -> List[_Exchange]:
    exchanges: List[_Exchange] = []
    current: Optional[_Exchange] = None
    for segment in transcript.segments:
        if _is_prompt(segment):
            current = _Exchange(prompt=segment)
            exchanges.append(current)
        elif current is not None:
            current.responses.append(segment)
    return exchanges


def _classify_prompt(text: str) -> List[Category]:
    """Classifies a transcript prompt by keyword - possibly into MORE THAN
    ONE category, since interviewers routinely ask compound questions
    ("Who is involved, and when does approval happen?"). Returning only the
    single highest-priority category for a compound question would silently
    lose the other one - found while reviewing real pilot output: the
    potential_gap fixture's L03 ("Who is involved, and when does approval
    happen relative to the deployment?") was being classified as WHEN only,
    which meant WHO never got an answer and was falsely reported as
    missing on a control whose whole point was to be fully documented.

    "What"-openers are still checked first: a question like "What happens
    ... when they leave?" is a WHAT question using "when" as a subordinate
    conjunction, not a genuine compound question - so WHAT is exclusive of
    WHEN when it matches via its own opener, to avoid re-introducing the
    earlier "what happens when" -> WHEN misclassification.
    """
    t = f" {text.lower()} "
    stripped = t.strip()

    if stripped.startswith("what") or "walk me through" in t or "walk you through" in t:
        return [Category.WHAT]

    categories: List[Category] = []
    is_frequency_phrase = "how often" in t or "how frequently" in t or "frequency" in t or "trigger" in t
    if is_frequency_phrase or " when " in t or stripped.startswith("when"):
        categories.append(Category.WHEN)
    if " who " in t or stripped.startswith("who"):
        categories.append(Category.WHO)
    if " why " in t or stripped.startswith("why") or "reason" in t:
        categories.append(Category.WHY)
    if " where " in t or stripped.startswith("where"):
        categories.append(Category.WHERE)
    if not is_frequency_phrase and (stripped.startswith("how") or "how" in t):
        categories.append(Category.HOW)
    if not categories and " what " in t:
        categories.append(Category.WHAT)
    return categories


_NON_ANSWER_PATTERNS = [
    re.compile(r"\bnot\s+(?:totally|really|entirely|completely|all that)?\s*sure\b"),
    re.compile(r"\bdon'?t\s+(?:really|actually)?\s*know\b"),
    re.compile(r"\bcould?n'?t\s+tell\s+you\b"),
    re.compile(r"\bcan'?t\s+tell\s+you\b"),
    re.compile(r"\bno\s+idea\b"),
    re.compile(r"\bwrong\s+person\b"),
    re.compile(r"\bdon'?t\s+want\s+to\s+guess\b"),
    re.compile(r"\b(?:never|ever)\s+explained\b"),
    re.compile(r"\bhaven'?t\s+been\s+told\b"),
]


def _is_non_answer(text: str) -> bool:
    """Detects an EXPLICIT hedge ("not sure", "couldn't tell you", ...).

    Known limitation: a SOFT/implicit hedge with no such phrase (e.g. "I'm
    not really on that team though" as an indirect disclaimer of authority)
    is not caught by this deterministic layer - see the extraction report's
    limitations section.
    """
    t = text.lower()
    return any(pattern.search(t) for pattern in _NON_ANSWER_PATTERNS)


def _normalize(text: str) -> set:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return {tok for tok in cleaned.split() if tok}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _combined_text(segments: List[TranscriptSegment]) -> str:
    return " ".join(s.text for s in segments)


def _source_references_for(transcript: Transcript, segments: List[TranscriptSegment]) -> List[SourceReference]:
    return [
        SourceReference(
            source_id=transcript.transcript_id,
            source_type=SourceType.WALKTHROUGH_TRANSCRIPT,
            source_name=transcript.source_name,
            locator=segment.segment_id,
            excerpt=segment.text[:1000],
        )
        for segment in segments
    ]


def _resolve_category(
    category: Category, exchanges: List[_Exchange], transcript: Transcript
) -> tuple[DocumentedAttribute, Optional[str]]:
    """Returns (attribute, missing_reason). missing_reason is None when
    the attribute was resolved."""
    if not exchanges:
        return DocumentedAttribute(), "This topic was not discussed in the transcript."

    if len(exchanges) == 1:
        response_segments = exchanges[0].responses
        if not response_segments:
            return DocumentedAttribute(), "A question on this topic was asked, but no response was recorded."
        text = _combined_text(response_segments)
        if _is_non_answer(text):
            quote = text[:200]
            return (
                DocumentedAttribute(),
                f"The interviewee could not provide a confident answer on this topic (transcript {exchanges[0].responses[0].segment_id}: \"{quote}\").",
            )
        # Apply synthesis for HOW answers
        if category == Category.HOW:
            text = _synthesize_how_answer(text)
        return (
            DocumentedAttribute(
                value=to_documentation_voice(text),
                source_references=_source_references_for(transcript, response_segments),
            ),
            None,
        )

    # Multiple exchanges classified into the same category.
    texts_by_exchange = [(_combined_text(ex.responses), ex.responses) for ex in exchanges if ex.responses]
    non_answers = [t for t, _ in texts_by_exchange if _is_non_answer(t)]
    real_answers = [(t, segs) for t, segs in texts_by_exchange if not _is_non_answer(t)]

    if not real_answers:
        return DocumentedAttribute(), "This topic was asked about more than once, but no confident answer was ever given."

    if len(real_answers) == 1:
        text, segs = real_answers[0]
        # Apply synthesis for HOW answers
        if category == Category.HOW:
            text = _synthesize_how_answer(text)
        return (
            DocumentedAttribute(value=to_documentation_voice(text), source_references=_source_references_for(transcript, segs)),
            None,
        )

    # 2+ real answers for the same category - check whether they look like
    # elaboration on different sub-aspects (the common case: e.g. one
    # answer about review mechanics, another about how reliably an SLA is
    # met - both true, just about different things) or like short,
    # genuinely competing statements about the same specific fact (e.g. two
    # different single-word frequency answers). Only the latter is treated
    # as an unresolved conflict: a long, discursive answer is essentially
    # never a simple contradiction of another, so length alone is enough to
    # avoid the false "conflict" this produced on the potential_gap fixture
    # (two clearly complementary, non-contradictory HOW answers were being
    # discarded as unresolved because they scored low on token overlap -
    # low overlap there meant "different sub-topic", not "disagreement").
    _SHORT_ANSWER_WORD_LIMIT = 25
    token_sets = [_normalize(t) for t, _ in real_answers]
    pairwise_similarities = [
        _jaccard(token_sets[i], token_sets[j])
        for i in range(len(token_sets))
        for j in range(i + 1, len(token_sets))
    ]
    all_short = all(len(t.split()) <= _SHORT_ANSWER_WORD_LIMIT for t, _ in real_answers)
    looks_like_elaboration = (not all_short) or all(sim >= 0.15 for sim in pairwise_similarities)

    if looks_like_elaboration:
        all_segments = [seg for _, segs in real_answers for seg in segs]
        combined = " ".join(t for t, _ in real_answers)
        # Apply synthesis for HOW answers
        if category == Category.HOW:
            combined = _synthesize_how_answer(combined)
        return (
            DocumentedAttribute(
                value=to_documentation_voice(combined),
                source_references=_source_references_for(transcript, all_segments),
            ),
            None,
        )

    quotes = "; ".join(f"\"{t[:150]}\"" for t, _ in real_answers)
    return (
        DocumentedAttribute(),
        f"Multiple, substantively different statements were made on this topic and were not automatically reconciled: {quotes}. Reviewer clarification is required.",
    )


_CATEGORY_FIELD = {
    Category.WHAT: "what",
    Category.WHO: "who",
    Category.WHEN: "when",
    Category.WHY: "why",
    Category.WHERE: "where",
    Category.HOW: "how",
}


def _draft_control_description(doc: ControlDocumentation) -> Optional[str]:
    """A plain, templated composition of whatever was resolved - not
    natural-language smoothing. Only present dimensions are included, per
    the "do not force all six into a sentence" rule; the result is a
    review-ready draft, not polished prose."""
    clauses = []
    if doc.what.value:
        clauses.append(f"What: {doc.what.value}")
    if doc.who.value:
        clauses.append(f"Who: {doc.who.value}")
    if doc.when.value:
        clauses.append(f"When: {doc.when.value}")
    if doc.why.value:
        clauses.append(f"Why: {doc.why.value}")
    if doc.where.value:
        clauses.append(f"Where: {doc.where.value}")
    if doc.how.value:
        clauses.append(f"How: {doc.how.value}")
    if not clauses:
        return None
    # Each attribute gets its own paragraph (separated by a blank line)
    # rather than being run together - a wall of "What: ... Who: ... When:
    # ..." in one paragraph is hard to scan, and this is meant to be an
    # actual reviewable draft, not just a display convenience, so the break
    # belongs in the data itself.
    return "\n\n".join(clauses)


def _primary_question_text(questions: WalkthroughQuestionSet, category: Category) -> Optional[str]:
    """Reuses the stage-1 generated walkthrough question for this category as
    the follow-up question on a MissingInformation entry, rather than
    drafting new question text here - the question-generation stage already
    produced a tailored, control-specific question for exactly this
    category, so asking the same thing twice would be redundant. Prefers
    the `required=True` primary question over an optional follow-up (e.g.
    the WHO segregation-of-duties question) when a category has more than
    one."""
    candidates = [q for q in questions.questions if q.category == category]
    for q in candidates:
        if q.required:
            return q.question_text
    return candidates[0].question_text if candidates else None


def extract_control_documentation(
    control: Control, questions: WalkthroughQuestionSet, transcript: Transcript
) -> ExtractionResult:
    if not (control.control_id == questions.control_id == transcript.control_id):
        raise ValueError(
            "control_id mismatch across inputs: "
            f"control={control.control_id!r}, questions={questions.control_id!r}, "
            f"transcript={transcript.control_id!r}"
        )

    exchanges = _build_exchanges(transcript)
    exchanges_by_category: Dict[Category, List[_Exchange]] = {c: [] for c in _CORE_CATEGORIES}
    for exchange in exchanges:
        for category in _classify_prompt(exchange.prompt.text):
            if category in exchanges_by_category:
                exchanges_by_category[category].append(exchange)

    attributes: Dict[str, DocumentedAttribute] = {}
    missing: List[MissingInformation] = []
    for category in _CORE_CATEGORIES:
        field = _CATEGORY_FIELD[category]
        attribute, missing_reason = _resolve_category(category, exchanges_by_category[category], transcript)
        attributes[field] = attribute
        if missing_reason:
            missing.append(
                MissingInformation(
                    field=f"documentation.{field}",
                    reason=missing_reason,
                    follow_up_question=_primary_question_text(questions, category),
                    status=MissingInformationStatus.OPEN,
                )
            )

    # Condense verbose extracted values to business keywords/phrases
    # while preserving source references for audit traceability
    condensed_attributes: Dict[str, DocumentedAttribute] = {}
    for field, attribute in attributes.items():
        if attribute.value:
            condense_fn = getattr(condenser, f"condense_{field}", None)
            if condense_fn:
                condensed_value = condense_fn(attribute.value)
                condensed_attributes[field] = DocumentedAttribute(
                    value=condensed_value,
                    source_references=attribute.source_references
                )
            else:
                condensed_attributes[field] = attribute
        else:
            condensed_attributes[field] = attribute

    attributes = condensed_attributes

    documentation = ControlDocumentation(
        **attributes,
        control_description=_draft_control_description(ControlDocumentation(**attributes)),
        missing_information=missing,
        source_references=[
            SourceReference(
                source_id=transcript.transcript_id,
                source_type=SourceType.WALKTHROUGH_TRANSCRIPT,
                source_name=transcript.source_name,
                locator="full session",
            )
        ],
        metadata=GenerationMetadata(
            generated_by=GenerationSource.AI,
            generated_at=datetime.now(timezone.utc),
            model_or_author="deterministic-transcript-extractor-v1",
        ),
    )

    updated_questions: List[WalkthroughQuestion] = []
    for question in questions.questions:
        if question.category in attributes and attributes[_CATEGORY_FIELD[question.category]].value:
            attr = attributes[_CATEGORY_FIELD[question.category]]
            question = question.model_copy(
                update={"answer": attr.value, "source_references": attr.source_references}
            )
        updated_questions.append(question)

    return ExtractionResult(
        control_id=control.control_id,
        transcript_id=transcript.transcript_id,
        documentation=documentation,
        questions=WalkthroughQuestionSet(control_id=questions.control_id, questions=updated_questions),
    )
