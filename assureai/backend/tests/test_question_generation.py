import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.pilot.validation import validate_manifest
from app.question_generation.generator import generate_walkthrough_questions
from app.schemas.racm import Control, Risk, WalkthroughQuestionCategory
from app.validation import validate_record

PILOT_DIR = Path(__file__).resolve().parents[2] / "pilot"


def minimal_control(**overrides) -> Control:
    data = {
        "control_id": "CTRL-001",
        "control_title": "Monthly Bank Reconciliation Review",
        "risk": Risk(risk_id="R-1", risk_description="Errors in cash balances could go undetected."),
        "control_objective": "The Finance Manager reviews the monthly bank reconciliation prepared by the accountant.",
    }
    data.update(overrides)
    return Control(**data)


def load_pilot_control(case_id: str) -> Control:
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))
    case = next(c for c in manifest.cases if c.case_id == case_id)
    record = validate_record(json.loads((PILOT_DIR / case.racm_input_path).read_text(encoding="utf-8")))
    return record.control


# ---------- 1. Valid control produces structured questions ----------


def test_valid_control_produces_structured_questions():
    result = generate_walkthrough_questions(minimal_control())
    assert len(result.questions) > 0
    for q in result.questions:
        assert isinstance(q.question_text, str) and q.question_text.strip()
        assert isinstance(q.category, WalkthroughQuestionCategory)


# ---------- 2. Every question references the correct control_id ----------


def test_every_question_id_is_prefixed_with_the_control_id():
    control = minimal_control(control_id="CTRL-XYZ")
    result = generate_walkthrough_questions(control)
    assert result.control_id == "CTRL-XYZ"
    for q in result.questions:
        assert q.question_id.startswith("CTRL-XYZ-Q")


# ---------- 3. Question IDs are unique ----------


def test_question_ids_are_unique():
    result = generate_walkthrough_questions(minimal_control())
    ids = [q.question_id for q in result.questions]
    assert len(ids) == len(set(ids))


# ---------- 4. WHAT/WHO/WHEN/WHY/WHERE/HOW coverage ----------


def test_core_six_categories_are_covered_for_a_bare_control():
    result = generate_walkthrough_questions(minimal_control())
    categories = {q.category for q in result.questions}
    for expected in (
        WalkthroughQuestionCategory.WHAT,
        WalkthroughQuestionCategory.WHO,
        WalkthroughQuestionCategory.WHEN,
        WalkthroughQuestionCategory.WHY,
        WalkthroughQuestionCategory.WHERE,
        WalkthroughQuestionCategory.HOW,
    ):
        assert expected in categories, f"missing {expected} coverage"


# ---------- 5. Missing performer -> clarification, not an invented person ----------


def test_missing_performer_asks_open_who_question_without_inventing_a_person():
    control = minimal_control(control_objective=None)
    result = generate_walkthrough_questions(control)
    who_questions = [q for q in result.questions if q.category == WalkthroughQuestionCategory.WHO]
    assert who_questions
    combined = " ".join(q.question_text for q in who_questions)
    # No invented name/role appears - only a request to identify who performs it.
    assert "who is responsible for performing" in combined.lower()
    for name in ("Finance Manager", "Accountant", "Analyst"):
        assert name not in combined


# ---------- 6. Missing frequency -> clarification, not an invented frequency ----------


def test_missing_frequency_asks_open_when_question():
    control = minimal_control()
    assert control.control_frequency is None
    result = generate_walkthrough_questions(control)
    when_questions = [q for q in result.questions if q.category == WalkthroughQuestionCategory.WHEN]
    assert len(when_questions) == 1
    assert "how frequently" in when_questions[0].question_text.lower()
    for invented in ("daily", "weekly", "monthly", "quarterly", "annually"):
        assert invented not in when_questions[0].question_text.lower()


def test_present_frequency_produces_a_tailored_when_question():
    control = minimal_control(control_frequency="quarterly")
    result = generate_walkthrough_questions(control)
    when_questions = [q for q in result.questions if q.category == WalkthroughQuestionCategory.WHEN]
    assert len(when_questions) == 1
    assert "quarterly" in when_questions[0].question_text.lower()
    assert "control.control_frequency" in when_questions[0].source_fields


# ---------- 7. Missing system/location -> open question, not an invented system ----------


def test_missing_evidence_detail_asks_open_evidence_question():
    control = minimal_control()
    assert control.expected_evidence is None
    result = generate_walkthrough_questions(control)
    evidence_questions = [q for q in result.questions if q.category == WalkthroughQuestionCategory.EVIDENCE]
    assert len(evidence_questions) == 1
    assert "SAP" not in evidence_questions[0].question_text
    assert "screenshot" not in evidence_questions[0].question_text.lower()


def test_present_expected_evidence_produces_a_tailored_evidence_question():
    control = minimal_control(expected_evidence="a signed reconciliation checklist")
    result = generate_walkthrough_questions(control)
    evidence_questions = [q for q in result.questions if q.category == WalkthroughQuestionCategory.EVIDENCE]
    assert len(evidence_questions) == 1
    assert "signed reconciliation checklist" in evidence_questions[0].question_text
    assert "control.expected_evidence" in evidence_questions[0].source_fields


def test_where_question_never_invents_a_system_name():
    result = generate_walkthrough_questions(minimal_control())
    where_questions = [q for q in result.questions if q.category == WalkthroughQuestionCategory.WHERE]
    assert len(where_questions) == 1
    for invented_system in ("SAP", "ServiceNow", "Oracle", "Active Directory"):
        assert invented_system not in where_questions[0].question_text


# ---------- 8. Existing RACM details are incorporated into tailored questions ----------


def test_control_title_and_risk_are_incorporated_verbatim():
    control = minimal_control()
    result = generate_walkthrough_questions(control)
    what_q = next(q for q in result.questions if q.category == WalkthroughQuestionCategory.WHAT)
    why_q = next(q for q in result.questions if q.category == WalkthroughQuestionCategory.WHY)
    assert control.control_title in what_q.question_text
    assert "Errors in cash balances could go undetected" in why_q.question_text


def test_fallback_questions_are_not_used_as_the_only_output_when_context_exists():
    """The bad, generic 'What is the control?'/'Who performs the control?'
    style questions should not appear verbatim - context must be woven in."""
    result = generate_walkthrough_questions(minimal_control())
    texts_lower = [q.question_text.lower() for q in result.questions]
    assert "what is the control?" not in texts_lower
    assert "who performs the control?" not in texts_lower
    assert "when is the control performed?" not in texts_lower


# ---------- 9. Questions don't mutate facts from the source RACM ----------


def test_generation_does_not_mutate_the_input_control():
    control = minimal_control()
    snapshot = control.model_dump(mode="json")
    generate_walkthrough_questions(control)
    assert control.model_dump(mode="json") == snapshot


# ---------- 10. Duplicate questions are avoided ----------


def test_deduplication_drops_near_identical_questions_in_the_same_category():
    """Exercises the STEP 10 example pair directly ('who performs' vs 'who
    is responsible for') at threshold=0.5, rather than the generator's own
    conservative default of 0.8. The rule set never actually produces this
    exact pair (see generator.py's LLM/architecture note and _rule_who),
    so this test targets the deduplication MECHANISM in isolation; the
    production default stays conservative per STEP 10's own caution against
    dropping legitimately different follow-ups."""
    from app.question_generation.generator import _Draft, _deduplicate
    from app.schemas.racm import WalkthroughQuestionCategory as Cat

    drafts = [
        _Draft(category=Cat.WHO, question_text="Who performs this control?", purpose="p"),
        _Draft(category=Cat.WHO, question_text="Who is responsible for this control?", purpose="p"),
        _Draft(category=Cat.WHY, question_text="Who performs this control?", purpose="p"),
    ]
    deduped = _deduplicate(drafts, threshold=0.5)
    who_texts = [d.question_text for d in deduped if d.category == Cat.WHO]
    assert len(who_texts) == 1  # the two near-identical WHO drafts collapse to one
    assert any(d.category == Cat.WHY for d in deduped)  # different category is untouched


def test_no_near_duplicate_questions_in_generated_output():
    from app.question_generation.generator import _normalize, _jaccard

    result = generate_walkthrough_questions(minimal_control(control_frequency="monthly"))
    for i, a in enumerate(result.questions):
        for b in result.questions[i + 1 :]:
            if a.category != b.category:
                continue
            similarity = _jaccard(_normalize(a.question_text), _normalize(b.question_text))
            assert similarity < 0.8, f"near-duplicate questions: {a.question_text!r} / {b.question_text!r}"


# ---------- 11. Empty/invalid RACM input follows existing validation behaviour ----------


def test_invalid_control_is_rejected_by_the_existing_schema_before_generation():
    with pytest.raises(ValidationError):
        Control(control_title="No ID", risk=Risk(risk_id="R-1", risk_description="x"))


# ---------- 12. Output conforms to the structured question schema ----------


def test_output_is_a_valid_walkthrough_question_set_and_json_serializable():
    result = generate_walkthrough_questions(minimal_control())
    dumped = result.model_dump(mode="json")
    json.dumps(dumped)  # must be plain JSON, not markdown/prose
    assert dumped["control_id"] == "CTRL-001"
    assert isinstance(dumped["questions"], list)
    for q in dumped["questions"]:
        assert set(q.keys()) >= {"question_id", "question_text", "category", "purpose", "source_fields", "required"}


# ---------- 13. Deterministic output for the same input ----------


def test_same_input_produces_identical_output():
    control = minimal_control(control_frequency="quarterly", expected_evidence="a sign-off log")
    result_a = generate_walkthrough_questions(control)
    result_b = generate_walkthrough_questions(control)
    assert result_a.model_dump(mode="json") == result_b.model_dump(mode="json")


# ---------- Pilot fixtures: behave differently across the 5 real scenarios ----------


@pytest.mark.parametrize(
    "case_id",
    ["well_documented", "incomplete", "design_issue", "potential_gap", "insufficient_information"],
)
def test_generator_runs_cleanly_against_every_pilot_control(case_id):
    control = load_pilot_control(case_id)
    result = generate_walkthrough_questions(control)
    assert result.control_id == control.control_id
    assert len(result.questions) >= 6  # at least the six core categories


def test_pilot_controls_produce_different_question_sets():
    """Sanity check that generation is genuinely tailored per control, not a
    fixed boilerplate list repeated for every case."""
    texts_by_case = {
        case_id: {q.question_text for q in generate_walkthrough_questions(load_pilot_control(case_id)).questions}
        for case_id in ["well_documented", "incomplete", "design_issue", "potential_gap", "insufficient_information"]
    }
    all_sets = list(texts_by_case.values())
    for i, a in enumerate(all_sets):
        for b in all_sets[i + 1 :]:
            assert a != b


def test_pilot_controls_with_review_or_approval_language_get_those_categories():
    # well_documented's control_objective mentions "approved" - approval-flavoured.
    control = load_pilot_control("well_documented")
    result = generate_walkthrough_questions(control)
    categories = {q.category for q in result.questions}
    assert WalkthroughQuestionCategory.APPROVAL in categories or WalkthroughQuestionCategory.REVIEW in categories


def test_pilot_it_general_controls_trigger_system_category():
    # All 5 pilot controls sit under engagement.process == "IT General Controls".
    from app.pilot.validation import validate_manifest as _vm
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))
    case = manifest.cases[0]
    record = validate_record(json.loads((PILOT_DIR / case.racm_input_path).read_text(encoding="utf-8")))
    result = generate_walkthrough_questions(record.control, engagement=record.engagement)
    categories = {q.category for q in result.questions}
    assert WalkthroughQuestionCategory.SYSTEM in categories
