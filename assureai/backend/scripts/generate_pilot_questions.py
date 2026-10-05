"""Runs walkthrough-question generation against every pilot RACM control and
prints a structured, human-readable report for manual review.

Usage (from assureai/backend):
    venv\\Scripts\\python.exe scripts\\generate_pilot_questions.py

This is a reusable review tool, not a test - it produces no assertions and
writes nothing back to the pilot fixtures. Re-run any time the generator or
the pilot fixture set changes.
"""
import json
from pathlib import Path

from app.pilot.validation import validate_manifest
from app.question_generation.generator import generate_walkthrough_questions
from app.validation import validate_record

PILOT_DIR = Path(__file__).resolve().parents[2] / "pilot"


def main() -> None:
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))

    for case in manifest.cases:
        record = validate_record(
            json.loads((PILOT_DIR / case.racm_input_path).read_text(encoding="utf-8"))
        )
        control = record.control
        result = generate_walkthrough_questions(control, engagement=record.engagement)

        print("=" * 100)
        print(f"CASE: {case.case_id}  (scenario={case.scenario.value})")
        print(f"CONTROL ID: {control.control_id}")
        print(f"CONTROL TITLE: {control.control_title}")
        print(f"PROCESS / SUBPROCESS: {record.engagement.process} / {record.engagement.subprocess}")
        print(f"RISK: {control.risk.risk_description}")
        print(f"CONTROL OBJECTIVE: {control.control_objective}")
        print("-" * 100)
        print(f"GENERATED {len(result.questions)} QUESTIONS:")
        for q in result.questions:
            print(f"  [{q.question_id}] ({q.category.value}, required={q.required})")
            print(f"    Q: {q.question_text}")
            print(f"    Purpose: {q.purpose}")
            print(f"    Source fields: {q.source_fields}")
        print()


if __name__ == "__main__":
    main()
