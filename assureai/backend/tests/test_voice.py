from app.transcript_extraction.voice import to_documentation_voice


def test_none_and_empty_pass_through_unchanged():
    assert to_documentation_voice(None) is None
    assert to_documentation_voice("") == ""


def test_simple_first_person_sentence_is_passivized():
    result = to_documentation_voice("I create the account in Active Directory using our standard templates.")
    assert result == "The account was created in Active Directory using our standard templates."


def test_we_form_is_passivized():
    result = to_documentation_voice("We check the requested access against the standard profile.")
    assert result == "The requested access was checked against the standard profile."


def test_object_already_has_a_determiner_is_not_double_prefixed():
    result = to_documentation_voice("I save the reviewed spreadsheet with my sign-off date.")
    assert result == "The reviewed spreadsheet was saved with my sign-off date."
    assert "the the" not in result.lower()


def test_indefinite_article_object_keeps_its_own_article():
    result = to_documentation_voice("I take a screenshot of the final group membership.")
    assert result.startswith("A screenshot was taken of")


def test_mid_sentence_match_is_not_force_capitalized():
    result = to_documentation_voice("Every quarter, I pull a report of everyone with admin access.")
    assert result.startswith("Every quarter, a report was pulled")


def test_unrecognized_verb_is_left_unchanged():
    # "go" is deliberately not in the whitelist - too irregular/ambiguous
    # to guess a confident passive form for.
    original = "I go through it line by line and confirm each person still needs access."
    assert to_documentation_voice(original) == original


def test_non_answer_text_is_left_unchanged():
    original = "I'm honestly not sure there's an official timeframe."
    assert to_documentation_voice(original) == original


# ---------- Regression tests for real bugs found reviewing pilot output ----------


def test_phrasal_verb_particle_is_not_treated_as_an_object():
    """'sign off' -> the object-detector previously grabbed the particle
    'off' as if it were a noun and produced 'the off was signed on the
    review' - nonsensical. Must now leave this clause untouched."""
    original = "I go through it line by line, and I sign off on the review."
    assert to_documentation_voice(original) == original


def test_wh_clause_object_is_not_mangled():
    """'We look at what was changed...' previously produced an object
    starting with the preposition 'at' ('The at what was changed... was
    looked'), because a comma broke up the whitespace the boundary-word
    lookahead needed. Must now leave this clause untouched rather than
    guess a broken sentence."""
    original = "We look at what was changed, why, whether it worked, and whether it should also go through a proper change request."
    assert to_documentation_voice(original) == original


def test_source_reference_excerpt_stays_verbatim_regardless_of_voice_rewrite():
    """The voice rewrite must only ever touch DocumentedAttribute.value -
    never the evidence excerpt, which must remain an exact quote."""
    from app.schemas.racm import Control, Risk
    from app.question_generation.generator import generate_walkthrough_questions
    from app.transcript_extraction.extractor import extract_control_documentation
    from app.transcript_extraction.parser import parse_transcript_text

    control = Control(
        control_id="CTRL-VOICE-01",
        control_title="Test Control",
        risk=Risk(risk_id="R-1", risk_description="A risk."),
    )
    questions = generate_walkthrough_questions(control)
    raw = (
        "[L01] Interviewer: Who performs the review?\n"
        "[L02] Interviewee: I create the account in Active Directory using standard templates.\n"
    )
    transcript = parse_transcript_text(raw, transcript_id="WT-1", control_id=control.control_id, source_name="t")
    result = extract_control_documentation(control, questions, transcript)

    who = result.documentation.who
    assert who.value == "The account was created in Active Directory using standard templates."
    assert who.source_references[0].excerpt == "I create the account in Active Directory using standard templates."


def test_second_verb_joined_to_a_passive_clause_is_passivised_too():
    assert (
        to_documentation_voice("I prepare the journal in the finance system and attach the supporting schedule.")
        == "The journal was prepared in the finance system and the supporting schedule was attached."
    )


def test_a_joined_clause_with_its_own_verb_is_left_alone():
    text = "I check the journal against the supporting schedule and confirm the accounts and amounts are correct."
    assert to_documentation_voice(text) == (
        "The journal was checked against the supporting schedule and confirm the accounts and amounts are correct."
    )


def test_conjunct_is_not_rewritten_when_the_clause_before_it_is_not_passive():
    text = "The clerk prepares a run and exports the report."
    assert to_documentation_voice(text) == text
