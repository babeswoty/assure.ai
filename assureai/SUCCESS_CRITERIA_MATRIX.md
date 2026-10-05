# AssureAI Pilot — Success Criteria Matrix

Every threshold below is `THRESHOLD_REQUIRES_PILOT_DECISION` - none are
invented here. See [PILOT_EVALUATION_FRAMEWORK.md](PILOT_EVALUATION_FRAMEWORK.md)
for the full methodology and the data model each row is backed by.

This is a measurement design, not a pass/fail gate: it defines how we will
know whether AssureAI is useful, not what score counts as "good enough."

| # | Dimension | Item evaluated | Definition | Comparison method | Possible outcomes | Evidence required | Evaluation | Threshold |
|---|---|---|---|---|---|---|---|---|
| 1 | Quality | Documentation attributes (What/Who/When/Why/Where/How) | Does AssureAI's extracted value match the reviewer's independent reading of the same evidence, in substance | Reviewer compares `documentation.<attr>.value` vs. reference; wording differences are not disagreement | `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE` (`FieldComparison`) | Walkthrough transcript/evidence; both drafted and reference values | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 2 | Quality | Control description | Does the synthesized narrative accurately represent the control | Same as above, applied to `documentation.control_description` | `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE` | Reviewer's own synthesis of the same evidence | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 3 | Quality | Risk / control objective / control alignment | Does AssureAI's alignment conclusion (`design_assessment.risk_objective_control_alignment`) match the reviewer's | Same, applied to the alignment dimension's `result` + `rationale` | `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE` | RACM input (risk, objective), documentation | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 4 | Quality | Design conclusion | Does `design_assessment.first_pass_design_conclusion` match the reviewer's own conclusion | Same, on the enum value itself | `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE` | Documentation, design-assessment dimensions | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 5 | Quality | Design rationale | Does the stated rationale (`design_assessment.conclusion_rationale`) hold up, independent of whether the conclusion itself matched | Same, on the rationale text | `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE` | Same evidence used for the conclusion | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 6 | Quality | RFIs and testing procedures | Are the drafted RFIs/testing steps relevant and correctly scoped to close the identified gaps | Same, per `rfi_items[]` / `testing_procedures[]` entry | `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE` | Design assessment, missing-information items | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 7 | Quality | Gap fields (title/description/root cause/impact/recommendation/proposed action) | Does each gap and its remediation match the reviewer's independent gap analysis | Same, per gap field | `ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / NOT_ASSESSABLE` | Documentation, design assessment, reviewer's gap analysis | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 8 | Consistency | Assessment-state usage across similar controls | Does AssureAI apply `PASS/PARTIAL/FAIL/UNKNOWN/NOT_APPLICABLE` the same way given similarly strong/weak evidence | Reviewer compares state usage across controls with comparable evidence quality; different facts may justify different states | `ConsistencyFinding.is_contradiction = true/false`, with `finding` text | Two or more `ControlEvaluation`s with `consistency_notes` | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 9 | Consistency | Expected-field completion | Are comparable controls completed to a comparable depth (no unexplained gaps in one vs. another) | Automatic check: which sections/fields are populated vs. left `None`/empty, compared across controls; human judges whether variance is explained by evidence availability | Same as above | Same as above | BOTH | THRESHOLD_REQUIRES_PILOT_DECISION |
| 10 | Traceability | Reference existence & structural validity | Does every significant AI statement cite a `SourceReference` that actually resolves (real `source_id`, plausible `locator`) | Automatable: check citation presence and that the cited source_id/locator resolves against the known evidence set | `NO_REFERENCE / INCORRECT_REFERENCE` vs. a resolvable reference | `TraceabilityAssessment.cited_source_references`; the underlying evidence index | AUTOMATIC | THRESHOLD_REQUIRES_PILOT_DECISION |
| 11 | Traceability | Evidentiary support | Does the cited content actually substantiate the statement (not just exist) | Reviewer reads the cited excerpt against the claim | `SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / NOT_APPLICABLE` | `TraceabilityAssessment`, cited excerpt, original evidence | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 12 | Missing-information detection | Coverage of information gaps | Does AssureAI flag information as missing exactly when the reviewer independently agrees it's missing | Reviewer compares `documentation.missing_information`/`gap_assessment.missing_information` entries against their own independent read of the evidence | `TRUE_POSITIVE / FALSE_NEGATIVE / FALSE_POSITIVE / NOT_DETERMINABLE` (`MissingInformationComparison`) | Evidence set, reviewer's independent completeness check | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 13 | Missing-information detection | Flag presence (structural) | Does AssureAI produce a `MissingInformation` entry at all wherever a documentation field is left `None` | Automatic: every `None`-valued required-for-conclusion field should have a corresponding `MissingInformation` entry | Boolean per field (present/absent) | `RACMControlRecord` structure alone | AUTOMATIC | THRESHOLD_REQUIRES_PILOT_DECISION |
| 14 | Usefulness | Drafted narrative/analytical outputs (control description, design rationale, RFIs, testing procedures, gap descriptions, impact, recommendation, proposed action) | Did the draft give the reviewer a useful starting point, regardless of how much editing it needed | Reviewer rates each drafted output after using it in their actual workpaper | `ACCEPT_AS_IS / MINOR_AMENDMENT / SUBSTANTIAL_AMENDMENT / REJECT_REPLACE / NOT_ASSESSABLE` (`UsefulnessAssessment`) | The draft and the reviewer's final, as-used version | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION |
| 15 | Material discrepancies | Individually-tracked serious failures (unsupported conclusion, incorrect/fabricated attribution, omitted material attribute, undetected required missing info, conclusion despite insufficient evidence, materially different design conclusion, significant gap missed, recommendation that doesn't address its gap) | Did any single-instance failure occur that matters regardless of overall averages | Reviewer records each occurrence individually; never averaged into a score | `MaterialDiscrepancy` list (per control) and `MaterialDiscrepancyRef` list (per pilot) - always enumerated, never just counted | Whatever evidence documents the specific failure (linked `source_references`) | HUMAN_REVIEW | THRESHOLD_REQUIRES_PILOT_DECISION (and arguably should never be a simple numeric threshold - see Open Decisions) |

## Reading this matrix

- **AUTOMATIC** rows are candidates for a lightweight script (e.g., "does
  this MissingInformation entry exist for every blank field," "does this
  source_id resolve") - none of that is built in this task, only identified
  as automatable.
- **HUMAN_REVIEW** rows require the pilot reviewer's professional judgement
  and cannot be mechanically scored - this is most of the matrix, by design,
  because most of what matters here is substantive meaning, not structural
  presence.
- **BOTH** rows have an automatable structural component feeding a human
  judgement call.
- No row states a pass/fail percentage. That decision is explicitly deferred
  until representative pilot results exist (see
  [PILOT_EVALUATION_FRAMEWORK.md § Open Decisions](PILOT_EVALUATION_FRAMEWORK.md#open-decisions)).
