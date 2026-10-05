# AssureAI Pilot Evaluation Framework

This defines how we compare AssureAI's draft RACM outputs against an
experienced reviewer's independent conclusions, for a pilot. It does **not**
try to show AI replaces the reviewer - it measures how useful and reliable
AssureAI is as a reviewer-support tool. Reviewers keep professional judgement
and final approval throughout; nothing here changes that.

The data model this framework uses lives in
`assureai/backend/app/evaluation/` (`enums.py`, `models.py`, `validation.py`)
and reuses the canonical RACM schema's own `SourceReference` and
`ReviewDecision` rather than duplicating them. See
[SUCCESS_CRITERIA_MATRIX.md](SUCCESS_CRITERIA_MATRIX.md) for the criterion-by-criterion matrix.

## Unit of evaluation

One RACM control, identified by its `control_id`, is the primary comparison
unit. For each pilot control we produce one `ControlEvaluation` record
comparing:

```
ASSUREAI DRAFT  (the RACMControlRecord AssureAI produced for this control)
      vs
REVIEWER REFERENCE  (the same control, independently assessed by an
                     experienced reviewer, without being anchored to
                     AssureAI's draft)
```

`ControlEvaluation` never embeds a full copy of either record - it cites
`control_id`, pins `control_schema_version` and an optional
`control_snapshot_ref` (see "Why snapshots matter" below), and holds short
textual snapshots of just the compared values.

### Why snapshots matter

`RACMControlRecord` is progressively enriched across the pipeline (walkthrough
-> documentation -> design assessment -> gap assessment -> review). A pilot
evaluation compares against **one point in time**. If the control is edited
after the evaluation runs, the evaluation can silently go stale. We record
`control_snapshot_ref` (a hash, revision id, or timestamp - the exact
mechanism is an infrastructure decision, see Open Decisions) so a stale
evaluation is at least detectable, not silently trusted.

## Comparison method (general)

Comparison is **substantive, not literal**. Different wording that reaches
the same conclusion is not a disagreement. This applies uniformly across all
five pilot areas: a reviewer (not a string-diff) sets every comparison
result. Nothing in the schema computes `ALIGNED`/`NOT_ALIGNED` etc.
automatically from text similarity - see Open Decisions for whether an
automatic pre-filter should assist (not replace) that judgement later.

## 1. Quality - field-level comparison

Model: `FieldComparison` (one per compared field/output, keyed by a dotted
path like `documentation.who` or `gap_assessment.gaps[GAP-1].recommendation`,
the same convention `MissingInformation.field` already uses).

Classification: `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE`.

**Are four categories sufficient?** Yes, for a pilot:
- `ALIGNED` / `NOT_ALIGNED` cover clear agreement/disagreement on substance.
- `PARTIALLY_ALIGNED` covers "same idea, but incomplete, imprecise, or partly
  wrong" - the common middle case for narrative fields.
- `NOT_ASSESSABLE` covers when comparison itself isn't meaningful (no
  reference value was produced, or the field is legitimately unpopulated on
  both sides).

We deliberately do **not** add a finer severity scale under `NOT_ALIGNED`.
Severity is tracked on an orthogonal axis: `FieldComparison.material_discrepancy`
(a boolean flag) and, for the worst cases, a linked `MaterialDiscrepancy`
record (see Material Discrepancy Framework below). Splitting the comparison
enum itself by severity would conflate "how different" with "how much it
matters" - two different questions.

Each `FieldComparison` also carries `reviewer_comment` (why) and
`supporting_source_references` (evidence backing the *reviewer's* judgement,
not necessarily what AssureAI cited - see Traceability below for that).

## 2. Consistency - across similar controls, not within one

STEP 4 asks whether AssureAI behaves consistently **across similar
controls** - that is inherently a cross-control question, and cannot be
answered by looking at one `ControlEvaluation` in isolation. We split it:

- **Per-control**: `ControlEvaluation.consistency_notes` (`ConsistencyObservation[]`)
  records *facts* about this control relevant to consistency - e.g. "used
  `PARTIAL` here, consistent with its use of `PARTIAL` (not `FAIL`) on
  control AP-VEN-002" - optionally pointing at other `control_id`s already
  compared. This is evidence, not a verdict.
- **Pilot-level**: `PilotSummary.consistency_findings` (`ConsistencyFinding[]`)
  holds the actual verdicts, each referencing 2+ `control_id`s and an
  explicit `is_contradiction: bool`.

We check:
- consistent completion of expected fields (did comparable controls get the
  same sections filled in, or does completeness vary unexpectedly);
- consistent use of assessment states (`PASS`/`PARTIAL`/`UNKNOWN`/etc. applied
  the same way given similar evidence quality);
- consistent treatment of missing information (same threshold for "flag it"
  vs. "infer it" across controls);
- consistent reasoning structure (rationales follow a similar structure/
  depth for similar controls);
- contradictions - same fact pattern, different conclusion, with no
  supporting difference in the underlying evidence.

**Differences are not automatically inconsistencies.** Two controls can
legitimately reach different conclusions because their facts differ.
`is_contradiction` must be set deliberately by the reviewer; it is never
inferred from controls simply having different results.

## 3. Traceability - does the evidence actually support the statement

Model: `TraceabilityAssessment`, one per significant AI-generated statement,
using the existing `SourceReference` model for `cited_source_references`
(exactly what AssureAI cited - possibly empty).

Classification (recommended improvement on the suggested scale - see
justification below): `NO_REFERENCE / SUPPORTED / PARTIALLY_SUPPORTED /
UNSUPPORTED / INCORRECT_REFERENCE / NOT_APPLICABLE`.

**Why `NO_REFERENCE` is added:** the suggested scale
(`SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED/INCORRECT_REFERENCE/NOT_APPLICABLE`)
conflates two different failures under `UNSUPPORTED`:
1. AssureAI cited a real, correctly-attributed source, but its content
   doesn't actually back the statement (a comprehension/reasoning failure).
2. AssureAI drew a conclusion and cited **nothing at all** (a citation-
   discipline failure - arguably more serious, and definitely different to
   fix).

The task's own STEP 5 question list treats these as separate questions ("is
the conclusion unsupported?" vs. "does the cited content support the
statement?"), which is exactly this distinction. `NO_REFERENCE` keeps them
visible as different failure modes instead of merging them.

Traceability questions this answers per statement:
- Is there a source reference at all? -> `NO_REFERENCE` if not.
- Does the referenced source exist / resolve to the intended location? ->
  `INCORRECT_REFERENCE` if it's fabricated or points somewhere else entirely.
- Does the cited content actually support the statement? ->
  `SUPPORTED`/`PARTIALLY_SUPPORTED`/`UNSUPPORTED`.
- Is a citation even expected for this kind of statement? -> `NOT_APPLICABLE`
  (e.g. a purely structural/boilerplate field).

**Having a citation is not sufficient** - `SUPPORTED` requires the reviewer
to confirm the cited excerpt substantively backs the claim, not merely that
a `SourceReference` object is present.

Two of these checks have different automation potential (see the Success
Criteria Matrix): reference existence/resolution is largely mechanical;
evidentiary support is a human judgement call.

## 4. Missing-information detection

Model: `MissingInformationComparison`, comparing what AssureAI's
`MissingInformation` entries flagged against what the reviewer independently
determines is actually missing, for the same field.

Classification: `TRUE_POSITIVE / FALSE_NEGATIVE / FALSE_POSITIVE /
NOT_DETERMINABLE`.

- `TRUE_POSITIVE`: AssureAI correctly flagged required information as
  missing.
- `FALSE_NEGATIVE`: the reviewer found missing information AssureAI didn't
  flag - this should usually also produce a `MaterialDiscrepancy` of type
  `missing_info_not_detected` if the omission is significant.
- `FALSE_POSITIVE`: AssureAI flagged something as missing that was in fact
  adequately covered by the evidence.
- `NOT_DETERMINABLE`: the evaluator cannot make a confident call either way
  from the available evidence.

**True negatives are not recorded as individual rows.** Recording "field X:
neither side flagged it as missing, and correctly so" for every untouched
field on every control would duplicate the RACM record with no evaluative
value. `PilotSummary` should track the total number of fields checked
per pilot separately (an Open Decision - see below) so recall/precision-style
questions remain answerable without materializing every non-event.

The result is **not auto-derived** from the two booleans
(`assureai_flagged_missing`, `reviewer_flagged_missing`) that are also
recorded for audit purposes - a simple truth table can't resolve
`NOT_DETERMINABLE`, and even the other three categories can require judgement
about whether AssureAI's flagged field and the reviewer's concern are really
the same thing.

## 5. Usefulness - is the draft a good starting point

Model: `UsefulnessAssessment`, applied per drafted output (control
description, design rationale, RFIs, testing procedures, gap descriptions,
impact, recommendation, proposed action - anything the reviewer had to read
and act on).

Classification: `ACCEPT_AS_IS / MINOR_AMENDMENT / SUBSTANTIAL_AMENDMENT /
REJECT_REPLACE / NOT_ASSESSABLE`.

**"Useful" does not mean "accepted unchanged."** `MINOR_AMENDMENT` and even
`SUBSTANTIAL_AMENDMENT` both mean the draft provided real value - the
reviewer built on it rather than starting from a blank page. Only
`REJECT_REPLACE` means the draft was not a useful starting point.

This is judged separately from `quality` (factual/substantive correctness):
a factually correct draft can still need heavy rewriting for tone, structure,
or audit-readiness, and a draft with a minor factual gap can still be a
useful skeleton.

## Material Discrepancy Framework

Model: `MaterialDiscrepancy` - a serious, individually-tracked failure.
Types (`MaterialDiscrepancyType`): `unsupported_conclusion`,
`incorrect_source_attribution`, `material_attribute_omitted`,
`missing_info_not_detected`, `conclusion_despite_insufficient_evidence`,
`materially_different_design_conclusion`, `fabricated_source_reference`,
`significant_gap_missed`, `recommendation_does_not_address_gap`, `other`.

**These are never folded into an average or a single score.**
`ControlEvaluation.material_discrepancies` is a list, always fully rendered;
`PilotSummary.material_discrepancies` (`MaterialDiscrepancyRef[]`) keeps each
one individually visible at the pilot level too, referencing back to its
`control_id` and `discrepancy_id` rather than just counting them. A pilot
with one severe fabricated citation and a pilot with zero should never look
the same because "the average was fine."

## Pilot Summary Model

Model: `PilotSummary`, built by `app.evaluation.validation.build_pilot_summary()`
from a set of `ControlEvaluation`s. It is a generated snapshot (re-run the
builder after new evaluations land), not a live-linked view - unlike
`ControlEvaluation`'s own `quality_summary`/`traceability_summary`/etc.,
which are `@computed_field` properties that can never drift from their
source lists.

It answers the STEP-11 questions directly:

| Question | Where the answer comes from |
|---|---|
| Where does AssureAI align well with reviewers? | `field_alignment_counts` (per-field breakdown) |
| Where does it disagree? | `field_alignment_counts`, plus `consistency_findings` for cross-control contradictions |
| Which RACM fields cause recurring problems? | `field_alignment_counts`, read per field across all controls |
| Which conclusions lack source support? | `traceability_counts` |
| Does it detect important missing information? | `missing_information_counts` |
| Which drafts frequently require substantial rewriting? | `usefulness_counts` |
| What material discrepancies occurred? | `material_discrepancies` (individually listed) |
| What should improve before another iteration? | `open_items_for_next_iteration` (reviewer-authored, deliberately free text - this is a judgement call, not a computed value) |

No dashboard is built here - this is the data those questions need, nothing
more.

## Framework self-check

Against the ten questions this framework must let us answer:

1. **Did AssureAI reach substantively similar conclusions?** Yes - `field_comparisons` + `quality_summary`, judged on substance not wording.
2. **If not, exactly where?** Yes - each `FieldComparison.field` pinpoints the exact dotted path, with `reviewer_comment` explaining why.
3. **Were conclusions supported by source material?** Yes - `traceability_assessments`, with the `NO_REFERENCE` vs `UNSUPPORTED` distinction preventing that question from being answered too coarsely.
4. **Did it identify important missing information?** Yes - `missing_information_comparisons`, TP/FN/FP/ND.
5. **Were drafted outputs useful?** Yes - `usefulness_assessments`, on the "useful starting point" scale, not "accepted unchanged."
6. **Are serious failures visible individually?** Yes - `material_discrepancies` is never averaged, at both control and pilot level.
7. **Can every result be traced to its control?** Yes - every record in this schema requires `control_id` (on `ControlEvaluation`) or is nested under one; `PilotSummary.material_discrepancies` keeps the `control_id` on each entry.
8. **Can we compare multiple pilot controls consistently?** Yes - `consistency_notes` (per-control) + `consistency_findings` (cross-control, pilot-level), explicitly not assuming similar controls must match.
9. **Have we preserved human professional judgement?** Yes - every classification (`comparison`, traceability `result`, missing-info `result`, usefulness `rating`, `is_contradiction`) is reviewer-set, not computed from the data; nothing here produces an automatic pass/fail verdict on AssureAI or overrides `ControlReview.decision`.
10. **Have we avoided arbitrary thresholds?** Yes - see Open Decisions; every place a threshold might go states `THRESHOLD_REQUIRES_PILOT_DECISION` instead.

## Open Decisions

Things that need professional or project judgement, not invented rules:

1. **Success thresholds.** Every threshold in the Success Criteria Matrix is
   marked `THRESHOLD_REQUIRES_PILOT_DECISION`. We should set them after
   seeing representative pilot results, not before.
2. **Control snapshot/versioning mechanism.** `control_snapshot_ref` exists
   as a field, but *how* we pin a specific version of a progressively-
   enriched `RACMControlRecord` (content hash? a stored revision history?
   a timestamp plus append-only log?) is an infrastructure decision for
   whenever persistence is built - out of scope for this task.
3. **Total-fields-checked denominator for missing-information rates.** We
   deliberately don't record true negatives as rows. To compute a
   recall/precision-style rate at the pilot level, we need to know how many
   fields were checked in total per control. Whether that's a fixed
   checklist, derived from the RACM schema's own field list, or something
   the reviewer states explicitly per control is undecided.
4. **How many controls, and how they're selected, constitutes a valid
   pilot.** This framework works for any number of controls, but whether 5
   controls or 50 are needed to trust the resulting `PilotSummary` is a
   project/statistical judgement, not something this schema can decide.
5. **Whether an automatic pre-filter should assist (never replace) the
   quality/traceability comparison.** E.g., a text-similarity check that
   pre-populates a *suggested* `FieldComparisonResult` for the reviewer to
   confirm or override. Feasible later, but would need its own accuracy
   evaluation before being trusted even as an aid - not built here.
6. **Who performs pilot evaluations, and whether the same person also
   performs the underlying RACM review.** `evaluator_id` and
   `reviewer_decision`/`reviewer_id` (on the RACM record) are separate
   fields precisely because they might be different people, but the pilot's
   operating model for this is a project decision.
7. **Materiality criteria for `material_discrepancy`/`is_contradiction`.**
   The schema requires these to be set deliberately, but doesn't (and
   shouldn't yet) define exactly what makes a discrepancy "material" versus
   an ordinary `NOT_ALIGNED` - that determination itself needs pilot
   experience to calibrate, consistent with not inventing thresholds.
