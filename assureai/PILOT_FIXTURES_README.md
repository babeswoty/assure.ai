# AssureAI Pilot Input Pack

Five synthetic RACM controls used to test the complete AssureAI workflow
end-to-end once the walkthrough-question, transcript-extraction, design-
assessment, and gap-assessment agents exist. **No agent, LLM call, or
extraction logic is built in this task** - this is test data only.

**Everything in this pack is synthetic.** The client ("Solstice Financial
Services"), every interviewee, every transcript, and every fact in it is
fictitious, created specifically for AssureAI pilot testing. Nothing here is
derived from, or represents, real client data - the repository had no
RACM-domain sample data to derive from (see the inspection findings in the
task response for what existed and why it wasn't relevant: unrelated
telecom-billing reconciliation fixtures for a different project).

## Layout

```
assureai/pilot/
  manifest.json                        Ties all 5 cases together (see app.pilot.models.PilotManifest)
  well_documented/
    racm_input.json                    Valid RACMControlRecord - pre-walkthrough fields only
    racm_source_extract.json           Sidecar: synthetic "RACM tracker" source material
    walkthrough_transcript.txt         Synthetic, line-tagged interview transcript
    expected_reference.json            Ground truth (see app.pilot.models.ExpectedReference)
  incomplete/            ...same 4 files...
  design_issue/          ...same 4 files...
  potential_gap/         ...same 4 files...
  insufficient_information/  ...same 4 files...

assureai/backend/app/pilot/             Pydantic models + validation for this pack
  models.py, validation.py
assureai/backend/tests/test_pilot_fixtures.py   38 tests validating the pack itself
```

## Why `racm_input.json` and `racm_source_extract.json` are separate files

`racm_input.json` is a valid, minimal `RACMControlRecord` - only what a RACM
tracker + risk register would supply *before* any walkthrough happens:
`engagement`, `control.control_id/control_title/risk/control_objective`.
Everything else (`walkthrough`, `documentation`, `design_assessment`,
`gap_assessment`, `review`) is left at its schema default, because none of
that exists yet at this stage of the pipeline.

`racm_source_extract.json` holds the client's own pre-existing RACM tracker
fields (e.g. the control description exactly as originally typed into the
tracker). This is **not** put into `documentation.control_description`,
because that field is meant to hold AssureAI's own synthesized description -
pre-loading it would defeat the point of later testing whether the
extraction stage does its job, and would blur the "source data vs.
AI-generated" line the canonical schema exists to protect. Instead it's
treated as source material (`SourceType.RACM_INPUT`), citable via
`SourceReference` exactly like a transcript is.

## The five scenarios

| Scenario | Control | What it tests | Deliberately missing/notable |
|---|---|---|---|
| `well_documented` | `PILOT-A-UAM-001` - New User Access Provisioning Approval | Clean baseline: all 6 attributes answerable from one consistent account, independent reviewer, clear rationale | Nothing - this is the "good" case |
| `incomplete` | `PILOT-B-UAM-002` - Terminated Employee Access Revocation | Missing-information detection on specific attributes, while others still resolve | `when` (no SLA/timeframe) and `why` (no stated rationale) are explicitly unknown to the interviewee - not merely unasked |
| `design_issue` | `PILOT-C-UAM-003` - Quarterly Privileged Access Review | Reading for substance, not just "are all 6 boxes filled in" | Fully documented, but the reviewer of privileged access is the same person who provisions it - a self-review/independence failure buried in a follow-up answer (L06-L08) |
| `potential_gap` | `PILOT-D-CM-004` - Emergency Change Post-Implementation Approval | Distinguishing a sound *design* from poor *operating effectiveness* | Fully documented and well-designed, but only 2 of the last 6 emergency changes have completed approval, with no escalation (L11-L14) - ground truth for the future gap-assessment agent, not a documentation problem |
| `insufficient_information` | `PILOT-E-CM-005` - Standard Change Testing and Approval | Refusing to manufacture a conclusion | Interviewee is not the control owner and explicitly declines to guess on every attribute - nothing is reliably determinable |

**Comparable pairs for the consistency dimension:** `well_documented` /
`incomplete` share the User Access Management subprocess family;
`potential_gap` / `insufficient_information` share Change Management. This
gives a later consistency check two genuinely comparable pairs where
different outcomes are justified by different evidence, not a contradiction.

## Why 5 cases, not fewer or more

Each scenario exercises a behaviour the other four cannot: clean extraction
(A), specific-attribute missing-information detection (B), reading past
surface completeness for a substantive alignment failure (C), separating
design from operating effectiveness (D), and refusing to conclude at all
(E). Collapsing any two would blur which behaviour a given pass/fail
actually tests. Five is the smallest set that isolates all five behaviours
called for in this task without redundant copies of the same
straightforward case.

## How these fixtures should eventually be used

1. Load `manifest.json` via `app.pilot.validation.validate_manifest`.
2. For each case, feed `racm_input.json` (+ `racm_source_extract.json` as a
   citable source, + `walkthrough_transcript.txt` as the raw transcript
   input) through the real pipeline once it exists (question generation ->
   transcript extraction -> design assessment -> gap assessment).
3. Compare the resulting `RACMControlRecord` against `expected_reference.json`
   using the pilot evaluation schema already defined
   (`app.evaluation.models.FieldComparison`, `TraceabilityAssessment`,
   `MissingInformationComparison`, etc. - see
   [PILOT_EVALUATION_FRAMEWORK.md](PILOT_EVALUATION_FRAMEWORK.md)), producing
   one `ControlEvaluation` per case.
4. Roll up all 5 `ControlEvaluation`s with `build_pilot_summary()`.

None of that comparison/aggregation logic needs to change to consume this
pack - it was designed against the schema these fixtures already conform to.

## What's explicitly NOT here

No walkthrough-question agent, no LLM call, no transcript-extraction logic,
no design- or gap-assessment logic, no UI, no database, no live client data.
Fixtures are inert JSON/text files plus their own validation tests - nothing
in this pack tunes the (non-existent) system to reproduce the expected
answers.

## Open items

- **Exact locator/versioning scheme for real transcripts.** These fixtures
  use simple `[L01]`, `[L02]` line tags for stable, unambiguous citation.
  Whether a real pipeline uses line numbers, timestamps, or another scheme
  is a decision for when transcript ingestion is actually built.
- **Whether `racm_source_extract.json`'s ad hoc shape should become part of
  a formal "RACM source extract" model.** Right now it's a plain JSON
  sidecar, not validated by a dedicated schema, since its exact shape will
  depend on how real client RACM trackers are ingested (out of scope here).

## Known limitation: domain/format narrowness (accepted for this pilot wave)

An audit against this pack's mechanical guarantees (schema validity,
traceability resolution, no secrets - all covered by
`test_pilot_fixtures.py`) versus its *representativeness of a real RACM
population* found this pack is narrower than a full client engagement would
be, on five axes:

| Dimension | What this pack has | What's missing |
|---|---|---|
| Process/domain | 100% IT General Controls (access management, change management) | No financial-process control (financial close, procure-to-pay, revenue, etc.) - notably, the canonical schema's own worked example (`sample_control_record.json`, a journal-entry-review control) is from a domain this pilot pack never exercises |
| Source type | Only 2 of 9 `SourceType` values used (`walkthrough_transcript`, `racm_input`) | `evidence_document`, `system_screenshot`, `policy_document`, `interview_note`, `email_correspondence`, `prior_assessment` are all untested |
| Control nature | 100% "Manual" | No automated / IT-dependent-manual control, which would surface as a config review rather than an interview |
| Transcript format | 5/5 uniform single-interviewer/single-interviewee Q&A, 10-16 tagged lines each | No prose-style meeting notes, multi-participant call, or email-based walkthrough |
| Frequency | 4/5 "per event," 1/5 "quarterly" | No daily/monthly/annual control |

**Decision (2026-09-29): accepted as a known limitation, not blocking.** This
pack is representative enough for what it was scoped to do - exercise the 5
named system behaviors (well-documented / incomplete / design-issue /
operating-gap / insufficient-evidence) with valid, well-tested, non-fabricated
fixtures - and is marked complete on that basis. The gaps above are logged
here so a future pilot wave (e.g. adding a financial-process case, or a
second source type on an existing case) is a deliberate, scoped addition
rather than a silently-assumed "this already covers everything."
