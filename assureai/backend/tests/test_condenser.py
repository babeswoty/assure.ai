"""The condenser turns conversational answers into short documentation phrases."""
import re

import pytest

from app.transcript_extraction.condenser import (
    condense_how,
    condense_what,
    condense_when,
    condense_where,
    condense_who,
    condense_why,
)

# ---------------------------------------------------------------------- WHEN


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("Every Thursday, as part of the weekly payment run.", "Weekly"),
        ("Every Thursday.", "Weekly"),
        ("Each Monday morning.", "Weekly"),
        ("It happens daily.", "Daily"),
        ("Every business day before close.", "Daily"),
        ("We do it every month, at month end.", "Monthly"),
        ("Last week of every quarter - it's on my calendar as a recurring task.", "Quarterly"),
        ("Once a year, after the audit.", "Yearly"),
        ("It is done annually.", "Yearly"),
        ("Every year in March.", "Yearly"),
        ("Twice a year.", "Twice a year"),
        ("It is reviewed semi-annually.", "Twice a year"),
        ("Every six months.", "Twice a year"),
        ("Three times a year.", "Three times a year"),
        ("Every two weeks.", "Fortnightly"),
    ],
)
def test_when_pulls_the_frequency_keyword(answer, expected):
    assert condense_when(answer) == expected


@pytest.mark.parametrize(
    "answer, expected",
    [
        (
            "It's triggered every time HR notifies us of a new starter, so it happens continuously, not on a schedule.",
            "Triggered every time HR notifies of a new starter",
        ),
        ("Whenever a supplier changes their bank details.", "Triggered whenever a supplier changes their bank details"),
        ("When an emergency change is raised, we do it straight away.", "Triggered when an emergency change is raised"),
        ("As soon as the invoice is approved.", "Triggered as soon as the invoice is approved"),
    ],
)
def test_when_phrases_an_event_as_a_trigger(answer, expected):
    assert condense_when(answer) == expected


def test_when_keeps_both_a_frequency_and_a_trigger():
    assert (
        condense_when("Weekly, and also whenever there is an urgent payment.")
        == "Weekly; triggered whenever there is an urgent payment"
    )


def test_when_an_every_period_is_a_frequency_not_a_trigger():
    assert condense_when("Every quarter.") == "Quarterly"


def test_when_without_a_recognisable_frequency_keeps_the_original_wording():
    assert condense_when("Sure. After the board meeting in the afternoon.") == "After the board meeting in the afternoon"


# ---------------------------------------------------------------------- WHO


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("The AP Supervisor reviews it and the Finance Manager approves.", "AP Supervisor and Finance Manager"),
        (
            "I review it as the AP Supervisor, and the Finance Manager approves the final run. Neither of us prepares it.",
            "AP Supervisor and Finance Manager",
        ),
        ("Usually whoever's free on the helpdesk team picks it up from the queue.", "Helpdesk Team"),
        ("I do, along with one of my colleagues in IT Security.", "IT Security"),
        ("The engineer deploys first, then it goes to the CAB.", "Engineer and CAB"),
        ("Our Head of Finance and the Senior Systems Administrator.", "Head and Senior Systems Administrator"),
    ],
)
def test_who_pulls_the_role_names_not_the_sentence(answer, expected):
    assert condense_who(answer) == expected


def test_who_with_no_role_named_keeps_what_was_said_so_nothing_is_lost():
    result = condense_who("That's me too, actually - I'm also the one who grants admin access.")
    assert "me too" in result and "grants admin access" in result


# ---------------------------------------------------------------------- WHY


@pytest.mark.parametrize(
    "answer, expected",
    [
        (
            "Because managers don't always know the technical access needed, and this is our way of preventing "
            "over-provisioning or granting access outside someone's role.",
            "To prevent over-provisioning or granting access outside someone's role",
        ),
        (
            "Because once a payment is released it is hard to recover, so this prevents unauthorised, duplicate or "
            "incorrect payments to suppliers. An independent approver also stops one person from both creating and approving.",
            "To prevent unauthorised, duplicate or incorrect payments to suppliers",
        ),
        (
            "To make sure nobody's still got admin rights from a role they've since moved out of.",
            "To ensure nobody still has admin rights from a role they have since moved out of",
        ),
        (
            "The point is to allow the fix to happen fast, then have someone check it afterwards.",
            "To allow the fix to happen fast, then have someone check it afterwards",
        ),
    ],
)
def test_why_is_phrased_as_a_purpose(answer, expected):
    assert condense_why(answer) == expected


# ---------------------------------------------------------------------- WHERE


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("Everything lives in ServiceNow - the request form, our approval, and the provisioning ticket.", "ServiceNow"),
        ("In the finance system - the payment run and both approvals are stored there.", "Finance System"),
        ("In the change management tool - there's a ticket for the emergency change.", "Change Management Tool"),
        ("There's a helpdesk ticket in our ticketing system for each one.", "Ticketing System"),
        (
            'The reviewed spreadsheet was saved in a shared drive folder called "Access Reviews."',
            "Shared Drive Folder “Access Reviews”",
        ),
        ("We create the account in Active Directory and record it in ServiceNow.", "Active Directory, ServiceNow"),
    ],
)
def test_where_pulls_the_system_or_location(answer, expected):
    assert condense_where(answer) == expected


# ---------------------------------------------------------------------- WHAT / HOW


def test_what_drops_filler_and_the_speaker():
    result = condense_what(
        "Sure. I go through the report line by line and confirm each person still needs that access, and I sign off on the review."
    )
    assert result == "Go through the report line by line and confirm each person still needs that access, and sign off on the review"


def test_what_keeps_at_most_two_sentences_and_never_cuts_mid_clause():
    text = (
        "Each week the AP clerk prepares a payment run in the finance system from all approved supplier invoices that are due. "
        "The run is exported as a payment run report showing each supplier, invoice number and amount. "
        "Then something else happens that should not be included."
    )
    result = condense_what(text)
    assert result.startswith("Each week the AP clerk prepares a payment run")
    assert "should not be included" not in result
    assert not result.rstrip().endswith((" and", " the", ",", " of"))


def test_how_keeps_numbered_steps_without_the_speaker_or_filler():
    result = condense_how("Okay. We look at the change. Then we confirm it worked. I then sign off in the system.")
    assert result == "1. Look at the change\n2. Confirm it worked\n3. Sign off in the system"


def test_how_with_a_single_step_is_not_numbered():
    assert condense_how("I save the signed report in the payment run record.") == "Save the signed report in the payment run record"


def test_a_pronoun_inside_a_relative_clause_is_kept_so_the_sentence_still_works():
    assert condense_how("Remove access from the groups we remember to check.") == "Remove access from the groups we remember to check"


def test_contractions_are_expanded():
    assert condense_what("It's done when there's an approval and they don't skip it.") == "It is done when there is an approval and they do not skip it"


# ---------------------------------------------------------------------- general


@pytest.mark.parametrize("fn", [condense_what, condense_who, condense_when, condense_why, condense_where, condense_how])
def test_empty_values_pass_through(fn):
    assert fn(None) is None
    assert fn("") == ""


def _words(text: str) -> set:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


@pytest.mark.parametrize(
    "fn, answer",
    [
        (condense_who, "I review it as the AP Supervisor, and the Finance Manager approves the final run."),
        (condense_who, "Usually whoever's free on the helpdesk team picks it up."),
        (condense_where, "Everything lives in ServiceNow - the request form and the provisioning ticket."),
        (condense_where, "In the finance system - the payment run is stored there."),
        (condense_what, "Sure. When someone joins, their manager submits an access request form through the ServiceNow portal."),
    ],
)
def test_condensed_text_only_uses_words_from_the_answer(fn, answer):
    """Nothing is invented: every word of the result was in the interviewee's answer."""
    result = fn(answer)
    # "their" -> "the" and expanded contractions are the only wording changes allowed
    allowed = {"the", "is", "not", "have", "has", "will", "cannot", "are"}
    assert _words(result) - _words(answer) <= allowed


def test_who_ignores_a_role_that_is_only_mentioned_as_unavailable():
    answer = "I approve it myself because the Finance Manager is rarely available at month end."
    assert condense_who(answer) != "Finance Manager"


def test_who_still_returns_a_role_that_does_the_work():
    assert condense_who("The Finance Manager approves it in the system.") == "Finance Manager"
