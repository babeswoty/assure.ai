# AssureAI — RACM Master Schema (Phase: Domain Contract)

This is the first slice of AssureAI: the canonical data contract that every
future agent (walkthrough extraction, design assessment, gap assessment,
recommendation drafting, human review) reads and writes. It intentionally
contains **no UI, database, auth, LLM calls, agent orchestration, transcript
parsing, Excel integration, or dashboards** - just the domain model and its
runtime validation.

## Where things live

```
assureai/backend/app/schemas/common.py   Reusable primitives: SourceReference,
                                          MissingInformation, GenerationMetadata,
                                          and their enums.
assureai/backend/app/schemas/racm.py     The master domain model: Engagement, Risk,
                                          Walkthrough, DocumentedAttribute,
                                          ControlDocumentation, DesignAssessment,
                                          GapAssessment, ControlReview, Control,
                                          RACMControlRecord.
assureai/backend/app/validation.py       validate_record() / try_validate_record() /
                                          merge_control_section() runtime validation
                                          and safe-write entry points.
assureai/backend/examples/
  sample_control_record.json             One realistic, mid-workflow control record.
assureai/backend/tests/test_racm_schema.py

assureai/backend/app/evaluation/         Pilot evaluation schema: compares an AssureAI
                                          draft against an experienced reviewer's
                                          reference conclusions. See
                                          PILOT_EVALUATION_FRAMEWORK.md and
                                          SUCCESS_CRITERIA_MATRIX.md for the methodology.

assureai/pilot/                          5 synthetic pilot RACM controls + walkthrough
                                          transcripts + expected reviewer references, for
                                          testing the full pipeline once it's built. See
                                          PILOT_FIXTURES_README.md.
assureai/backend/app/pilot/              Pydantic models for the fixture pack itself
                                          (PilotManifest, ExpectedReference).
```

## The core idea: one record per control, progressively enriched

`RACMControlRecord` is the single shared object for a control. Each stage of
the pipeline only touches its own section and leaves the rest alone:

| Stage | Reads | Writes |
|---|---|---|
| RACM input load | - | `engagement`, `control.control_id/control_title/risk/control_objective` |
| Walkthrough question generation | `control.documentation` (what exists so far) | `control.walkthrough.questions[].question_text` |
| Transcript extraction | `control.walkthrough` | `control.walkthrough.questions[].answer` + `source_references`, then `control.documentation.*` (+ `missing_information` for anything the transcript didn't cover, + `metadata`) |
| Design assessment | `control.documentation` | `control.design_assessment.*` (+ `metadata`) |
| RFI / testing procedure drafting | `control.design_assessment` | `control.design_assessment.rfi_items`, `.testing_procedures` |
| Gap assessment | `control.documentation`, `control.design_assessment` | `control.gap_assessment.gaps` (+ `metadata` per gap) |
| Human review | everything above | `control.review` only |

A given agent should:

1. Load the current record: `record = validate_record(current_dict)` (raises
   `pydantic.ValidationError` on malformed input - don't catch that and
   guess a fallback, surface it).
2. Read whatever upstream sections it needs as context.
3. Write its output back with `merge_control_section(record, "<section>",
   data)`, **not** by constructing a fresh `Control(...)`/`RACMControlRecord(...)`.
   A bare `Control` with only your section filled in is itself a *valid*
   partial record (that's what makes partial records work at all) - which
   means building one from scratch and persisting it will silently erase
   every earlier stage's work. `merge_control_section` always starts from
   the current full record and swaps out exactly one section, so the rest
   is guaranteed to survive. Stamp `metadata.generated_by = "ai"`,
   `metadata.generated_at`, and `metadata.model_or_author` on any section
   you write.
4. Never touch `control.review` and never derive a "final" conclusion by
   copying an AI result into a place that implies human approval - `review`
   is the only field a human can set, and recording a real `decision` there
   requires `reviewer_id` and `reviewed_at`, plus `reviewer_comments` for a
   rejection or revision request (all enforced by the schema, not by
   convention).
5. When something can't be determined, don't invent a value: leave the
   field `None`/empty and add an entry to the relevant `missing_information`
   list explaining why, with a `follow_up_question` if one applies.
   `documentation` and `gap_assessment` each have their own
   `missing_information` list.
6. Serialize back out with `record.model_dump(mode="json")` and hand the
   dict to the next stage / persist it.

## Traceability

`SourceReference` is the one reusable citation type used everywhere an
AI-generated statement needs to point at evidence. It never embeds the full
source document - only an id/name/locator and an optional excerpt capped at
1000 characters - so the master record stays small and the evidence stays in
its original system of record.

Each of `documentation.what/who/when/why/where/how` is a `DocumentedAttribute`
(`{value, source_references}`) with its **own** citations, not a shared
document-level list - a transcript-extraction agent should cite the specific
part of the transcript that supports "who" separately from what supports
"when". `documentation.control_description` is the one synthesized exception:
it summarizes the six attributes above and inherits their traceability
transitively, so it stays a plain string. Each design-assessment dimension
and each gap also carries its own `source_references` for the same reason.
`documentation.source_references` (section-level) is for general/overall
citations, e.g. "the whole walkthrough transcript."

## Assessment safety

Finite-state fields are real enums, not free strings, so an agent (or a bug)
can't write `"probably fine"` into `design_assessment.first_pass_design_conclusion`.
`AssessmentResult` keeps three non-conclusive states distinct from
`PASS`/`PARTIAL`/`FAIL`:
- `NOT_ASSESSED` - nothing attempted yet (the default).
- `UNKNOWN` - attempted, but the evidence was insufficient or unavailable.
- `NOT_APPLICABLE` - the dimension legitimately does not apply to this
  control; never modeled as a `PASS` or a `FAIL`.

`gap_id`, `question_id`, `rfi_id`, and `procedure_id` must each be unique
within their list - two agent passes both emitting `GAP-1` is rejected at
validation time rather than silently colliding downstream.

## Validating a record

```python
from app.validation import validate_record, try_validate_record, merge_control_section

record = validate_record(some_dict)                  # raises on invalid input
record, error = try_validate_record(some_dict)        # returns (None, error) instead
record = merge_control_section(record, "gap_assessment", gap_data)  # safe section write
```

## Running the tests

```bash
cd assureai/backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
pytest
```

## Out of scope for this phase (intentionally)

UI, persistence/database, authentication, LLM/agent calls, transcript
parsing, Excel ingestion, dashboards, and per-stage (as opposed to
whole-control) review gates. The schema is designed so none of those would
require breaking changes to add later - e.g. persistence is just storing
`record.model_dump(mode="json")` and reloading it through `validate_record`.
