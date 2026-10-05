import json
import re
from pathlib import Path

import pytest

from app.pilot.models import ExpectedDesignConclusion, PilotScenario
from app.pilot.validation import validate_expected_reference, validate_manifest
from app.validation import validate_record

PILOT_DIR = Path(__file__).resolve().parents[2] / "pilot"

# Words that would indicate a secret/credential accidentally landed in a
# fixture file. Deliberately simple substring/regex checks - a guard, not an
# exhaustive secret scanner.
SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"\bpassword\s*[:=]", re.IGNORECASE),
    re.compile(r"\bsecret\s*[:=]", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id shape
]


def load_json(relative_path: str) -> dict:
    return json.loads((PILOT_DIR / relative_path).read_text(encoding="utf-8"))


def load_manifest():
    return validate_manifest(load_json("manifest.json"))


# ---------- Manifest-level checks ----------


def test_manifest_is_valid_and_has_five_cases():
    manifest = load_manifest()
    assert manifest.pilot_id == "PILOT-2026-01"
    assert len(manifest.cases) == 5
    assert {c.scenario for c in manifest.cases} == set(PilotScenario)


def test_every_case_id_and_control_id_is_unique():
    # Redundant with PilotManifest's own validator, but asserted directly
    # here per Step 9 item 2 ("every pilot control has a unique stable
    # identifier") so the guarantee is visible as its own test, not only as
    # a side effect of successful manifest parsing.
    manifest = load_manifest()
    case_ids = [c.case_id for c in manifest.cases]
    control_ids = [c.control_id for c in manifest.cases]
    assert len(case_ids) == len(set(case_ids))
    assert len(control_ids) == len(set(control_ids))


# ---------- Per-case checks (parametrized over the manifest) ----------


def _cases():
    return load_manifest().cases


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.case_id)
def test_racm_input_is_valid_against_the_canonical_schema(case):
    record = validate_record(load_json(case.racm_input_path))
    assert record.control.control_id == case.control_id
    # RACM input must not pre-populate AI-generated conclusions.
    assert record.control.documentation.what.value is None
    assert record.control.design_assessment.first_pass_design_conclusion.value == "not_assessed"
    assert record.control.gap_assessment.gaps == []
    assert record.control.review.decision.value == "not_reviewed"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.case_id)
def test_walkthrough_input_file_exists_and_links_to_its_control(case):
    transcript_path = PILOT_DIR / case.walkthrough_input_path
    assert transcript_path.exists(), f"missing walkthrough input for {case.case_id}"
    text = transcript_path.read_text(encoding="utf-8")
    assert case.control_id in text
    assert "SYNTHETIC" in text.upper()


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.case_id)
def test_expected_reference_is_valid_and_matches_its_case(case):
    reference = validate_expected_reference(load_json(case.expected_reference_path))
    assert reference.case_id == case.case_id
    assert reference.control_id == case.control_id


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.case_id)
def test_source_references_resolve_to_the_synthetic_transcript(case):
    """Every expected_traceability entry's locator must exist in the
    transcript, and its excerpt must actually appear on that line - proving
    the reference's citations are real, not fabricated ground truth."""
    reference = validate_expected_reference(load_json(case.expected_reference_path))
    transcript = (PILOT_DIR / case.walkthrough_input_path).read_text(encoding="utf-8")

    for entry in reference.expected_traceability:
        locator_tags = [f"[{tag}]" for tag in entry.source.locator.replace(",", "-").split("-")]
        assert any(tag in transcript for tag in locator_tags), (
            f"{case.case_id}: locator {entry.source.locator!r} for {entry.field!r} "
            "does not resolve to any line in the transcript"
        )
        if entry.source.excerpt:
            assert entry.source.excerpt in transcript, (
                f"{case.case_id}: excerpt for {entry.field!r} is not an exact substring "
                "of the transcript - possible fabricated/altered ground truth"
            )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.case_id)
def test_no_traceability_without_a_determined_value(case):
    """General invariant (Step 9 item 5, automatable half): you cannot cite
    support for a fact that was never determined. Also enforced by
    ExpectedReference's own validator - checked again here directly against
    the fixture files as a regression guard."""
    reference = validate_expected_reference(load_json(case.expected_reference_path))
    attributes = {
        "documentation.what": reference.expected_what,
        "documentation.who": reference.expected_who,
        "documentation.when": reference.expected_when,
        "documentation.why": reference.expected_why,
        "documentation.where": reference.expected_where,
        "documentation.how": reference.expected_how,
    }
    cited_fields = {e.field for e in reference.expected_traceability}
    for field, attribute in attributes.items():
        if attribute.value is None:
            assert field not in cited_fields, (
                f"{case.case_id}: {field!r} has no determined value but is cited "
                "in expected_traceability"
            )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.case_id)
def test_no_secrets_or_credentials_in_fixture_files(case):
    all_paths = [
        case.racm_input_path,
        case.walkthrough_input_path,
        case.expected_reference_path,
    ]
    if case.racm_source_extract_path:
        all_paths.append(case.racm_source_extract_path)

    for rel_path in all_paths:
        text = (PILOT_DIR / rel_path).read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(text), f"possible secret pattern in {rel_path}"


# ---------- Scenario-specific checks ----------


def test_incomplete_case_truly_omits_when_and_why():
    reference = validate_expected_reference(load_json("incomplete/expected_reference.json"))
    transcript = (PILOT_DIR / "incomplete/walkthrough_transcript.txt").read_text(encoding="utf-8")

    assert reference.expected_when.value is None
    assert reference.expected_why.value is None
    missing_fields = {m.field for m in reference.expected_missing_information}
    assert {"documentation.when", "documentation.why"} <= missing_fields

    # The transcript itself contains the interviewee's own admission that
    # these are unknown, not just an absence of the words "when"/"why".
    assert "not sure there's an official timeframe" in transcript
    assert "couldn't tell you why" in transcript


def test_insufficient_information_case_has_no_accidentally_obvious_conclusion():
    reference = validate_expected_reference(
        load_json("insufficient_information/expected_reference.json")
    )

    assert reference.design_conclusion_determinable is False
    assert reference.expected_design_conclusion == ExpectedDesignConclusion.INSUFFICIENT_INFORMATION
    assert reference.expected_traceability == []
    for attribute in (
        reference.expected_what,
        reference.expected_who,
        reference.expected_when,
        reference.expected_why,
        reference.expected_where,
        reference.expected_how,
    ):
        assert attribute.value is None
    assert len(reference.expected_missing_information) == 6


def test_potential_gap_case_is_fully_documented_with_no_false_missing_info():
    """Negative control: the gap here is operating-effectiveness, not
    documentation - there must be zero MissingInformation entries even
    though a real gap indicator is expected."""
    reference = validate_expected_reference(load_json("potential_gap/expected_reference.json"))

    assert reference.expected_missing_information == []
    assert reference.design_conclusion_determinable is True
    assert reference.expected_design_conclusion == ExpectedDesignConclusion.PASS
    assert reference.expected_gap_indicator.expected is True
    assert reference.expected_gap_indicator.gap_type.value == "operating_effectiveness_gap"


def test_design_issue_case_flags_alignment_despite_complete_documentation():
    reference = validate_expected_reference(load_json("design_issue/expected_reference.json"))

    assert reference.expected_missing_information == []
    assert reference.expected_risk_objective_control_alignment.result.value == "fail"
    assert reference.expected_design_conclusion == ExpectedDesignConclusion.FAIL


def test_well_documented_case_has_full_traceability_and_a_pass_conclusion():
    reference = validate_expected_reference(load_json("well_documented/expected_reference.json"))

    assert reference.expected_missing_information == []
    assert len(reference.expected_traceability) == 6  # one per attribute
    assert reference.expected_design_conclusion == ExpectedDesignConclusion.PASS


def test_comparable_scenario_pairs_share_a_subprocess_family_for_consistency_checks():
    """well_documented/incomplete and potential_gap/insufficient_information
    are meant to be comparable pairs for the consistency evaluation
    dimension - verify they actually share engagement/subprocess family."""
    a = validate_record(load_json("well_documented/racm_input.json"))
    b = validate_record(load_json("incomplete/racm_input.json"))
    d = validate_record(load_json("potential_gap/racm_input.json"))
    e = validate_record(load_json("insufficient_information/racm_input.json"))

    assert a.engagement.engagement_id == b.engagement.engagement_id == d.engagement.engagement_id == e.engagement.engagement_id
    assert "User Access Management" in a.engagement.process
    assert "User Access Management" in b.engagement.process
    assert "Change Management" in d.engagement.process
    assert "Change Management" in e.engagement.process
    # All four share the same higher-level RACM hierarchy (mega process/area).
    for record in (a, b, d, e):
        assert record.engagement.mega_process == "IT General Controls"
        assert record.engagement.area == "Information Technology"
