"""Runs the full RACM -> questions -> transcript -> documentation loop
against every pilot fixture and prints a structured report for manual
review. Reusable, no assertions - re-run any time the extractor or the
pilot fixture set changes.

Usage (from assureai/backend):
    PYTHONPATH=. venv/Scripts/python.exe scripts/run_pilot_extraction.py
"""
import json
from pathlib import Path

from app.pilot.validation import validate_manifest
from app.question_generation.generator import generate_walkthrough_questions
from app.transcript_extraction.extractor import extract_control_documentation
from app.transcript_extraction.parser import parse_line_tagged_transcript
from app.validation import validate_record

PILOT_DIR = Path(__file__).resolve().parents[2] / "pilot"


def main() -> None:
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))

    for case in manifest.cases:
        record = validate_record(json.loads((PILOT_DIR / case.racm_input_path).read_text(encoding="utf-8")))
        control = record.control
        questions = generate_walkthrough_questions(control, engagement=record.engagement)
        raw_transcript = (PILOT_DIR / case.walkthrough_input_path).read_text(encoding="utf-8")
        transcript = parse_line_tagged_transcript(
            raw_transcript,
            transcript_id=f"WT-{case.case_id}",
            control_id=control.control_id,
            source_name=f"{case.case_id} walkthrough transcript (SYNTHETIC)",
        )
        result = extract_control_documentation(control, questions, transcript)
        doc = result.documentation

        print("=" * 100)
        print(f"CASE: {case.case_id}  (scenario={case.scenario.value})")
        print(f"CONTROL: {control.control_id} - {control.control_title}")
        print(f"RISK: {control.risk.risk_description}")
        print(f"OBJECTIVE: {control.control_objective}")
        print(f"GENERATED {len(questions.questions)} WALKTHROUGH QUESTIONS")
        print(f"TRANSCRIPT: {len(transcript.segments)} segments parsed")
        print("-" * 100)
        for attr in ("what", "who", "when", "why", "where", "how"):
            a = getattr(doc, attr)
            print(f"{attr.upper():5} | value: {a.value!r}")
            for ref in a.source_references:
                print(f"        source: {ref.source_id} [{ref.locator}] \"{ref.excerpt}\"")
        print("-" * 100)
        print("MISSING INFORMATION:")
        if not doc.missing_information:
            print("  (none)")
        for m in doc.missing_information:
            print(f"  - {m.field}: {m.reason}")
            if m.follow_up_question:
                print(f"      Follow-up: {m.follow_up_question}")
        print("-" * 100)
        print("DRAFT CONTROL DESCRIPTION:")
        print(f"  {doc.control_description}")
        print("-" * 100)
        print(f"REVIEW STATUS: {record.control.review.decision.value} (untouched by this stage)")
        print()


if __name__ == "__main__":
    main()
