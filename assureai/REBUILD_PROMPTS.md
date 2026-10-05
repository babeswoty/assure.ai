# AssureAI rebuild prompts

Paste the **Master prompt** once at the start. Then paste the phases one at a time, and don't move on until the acceptance checks pass.

---

## Master prompt (paste first)

```
You are building AssureAI: an agent-assisted RACM (Risk & Control Matrix) testing and
assessment MVP. A reviewer loads one control, runs a walkthrough transcript through a
pipeline of small agents, reviews the drafts, and exports an Excel row.

Stack: Python 3.12 + FastAPI + Pydantic v2 + pytest (backend, own venv);
React 18 + TypeScript + Vite + Tailwind + Vitest/React Testing Library (frontend).
Layout: assureai/backend, assureai/frontend, assureai/pilot (test fixtures, not shown in the UI), assureai/samples.
Frontend runs on :5174 and proxies /api to the backend on :8001.

Non-negotiable rules:
1. Deterministic and rules-based. No LLM calls, no credentials, no external providers.
2. Never invent facts. If evidence is missing, leave it null and record a MissingInformation
   entry. Prefer "Requires Human Review" over a guess.
3. Traceability: every extracted fact carries SourceReference(s) with a verbatim excerpt
   (<= 1000 chars). Never alter excerpts.
4. Human-in-the-loop at every step: all AI output is a draft. Every step, starting with the
   loaded RACM input, needs a named reviewer's approval before the next step unlocks, and the final
   ControlReview.decision is the only thing that can approve the control as a whole.
5. One canonical record per control (RACMControlRecord). Every stage reads and enriches it;
   no parallel schemas, no duplicated fields.
6. Each pipeline stage is its own package under app/ with a clean __init__.py API.
7. Routes are thin wrappers; no business logic in them. Do not re-implement backend
   validation in the frontend; surface the backend's error text.
8. Build only what each phase asks. Do not build later phases early.
9. Every phase ends with passing tests (pytest / vitest) and, for UI work, a live check.

Work phase by phase. At the end of each phase, report what changed and the test counts.
```

---

## Phase 1: Canonical schema

```
Build app/schemas with the canonical models (Pydantic v2, extra="forbid"):
- common: SourceReference(source_id, source_type, source_name, locator, excerpt<=1000),
  MissingInformation(field, reason, follow_up_question, status), GenerationMetadata,
  ensure_unique_ids helper.
- racm: Engagement(engagement_id, client, opco, area, mega_process, process, subprocess),
  Risk(risk_id, risk_description),
  Control(control_id, control_title, control_reference, risk, control_objective,
  suggested_control_description, control_frequency/nature/type, expected_evidence,
  suggested_test_procedures_tod/toe, walkthrough, documentation, design_assessment,
  gap_assessment, review),
  DocumentedAttribute(value|None, source_references) and ControlDocumentation
  (what/who/when/why/where/how, control_description, missing_information, metadata),
  AssessmentResult enum (not_assessed, unknown, not_applicable, pass, partial, fail),
  DesignAssessment (completeness, relevance, risk_objective_control_alignment,
  first_pass_design_conclusion, conclusion_rationale),
  Gap (gap_id, gap_type, gap_title, gap_description, root_cause_category, impact,
  recommendation, action_owner, action_date) and GapAssessment,
  ControlReview with validators: reviewer_id and reviewed_at required for any decision;
  reviewer_comments required for rejected / needs_revision.
- RACMControlRecord(schema_version "1.0", engagement, control) and validate_record().

Do not build agents, API or UI yet.
Acceptance: schema tests for each validator, extra-field rejection, unique-id checks.
```

## Phase 2: Pilot fixtures and evaluation

```
Create assureai/pilot with manifest.json and 5 synthetic cases (clearly marked SYNTHETIC):
well_documented, incomplete, design_issue (the one person who performs the control also
reviews it, so independence fails), potential_gap, insufficient_information.
Each case folder has racm_input.json, walkthrough_transcript.txt (lines like
"[L01] Interviewer: ..."), and expected_reference.json.
control_objective values must read as objectives ("To ensure that ...").
Add an evaluation package that validates the manifest and reference files.

Acceptance: fixture-validation tests pass for all 5 cases.
```

## Phase 3: Walkthrough question generation

```
Build app/question_generation: generate_walkthrough_questions(control, engagement) ->
WalkthroughQuestionSet. Always emit What/Who/When/Why/Where/How questions (required).
Add narrow optional categories (evidence, review, approval, exception_handling, system)
only when the control's own text calls for them. Each question has category, purpose,
source_fields and required. Questions are templated from RACM fields; nothing is invented.

Acceptance: tests for the six core questions, conditional optional questions, and
per-question traceability to source fields.
```

## Phase 4: Transcript extraction

```
Build app/transcript_extraction:
- parser.parse_transcript_text(): parse "[L01] Speaker: text" lines. Use re.MULTILINE on
  the line pattern, because headers above the first line must not break detection. Add a
  regression test for this.
- extractor.extract_control_documentation(control, questions, transcript): map answers to
  the six attributes with source references and verbatim excerpts. Unresolved attributes
  stay null and get a MissingInformation entry whose follow_up_question reuses the stage-3
  question text.
- voice.to_documentation_voice(): deterministic passive-voice rewrite of the documented
  value ("An account was created in Active Directory", not "I created the account").
  Guard against phrasal verbs and WH-clauses. The excerpt stays verbatim.
- control_description: one paragraph per resolved attribute, joined with a blank line
  ("What: ...\n\nWho: ...").
Control-level guardrail: raise if the transcript's control_id differs from the control's.

Acceptance: all 5 pilot cases extract as expected; no fabricated values.
```

## Phase 5: Design Assessment Agent

```
Build app/design_assessment.assess_control_design(control) -> DesignAssessment. It reads
only the extracted documentation, never the raw transcript.
- completeness: 6 of 6 attributes = PASS, 4-5 = PARTIAL, fewer = FAIL.
- relevance: term-overlap heuristic (overlap coefficient, threshold 0.15) between
  what+how+description and risk+objective. Pass or Unknown only.
- alignment: same heuristic on WHY, plus an independence check: if the objective or risk
  requires independence (independent / segregation / separation of duties) and WHO
  contains a self-review signal, FAIL with a citing rationale.
- overall: completeness != PASS -> UNKNOWN; alignment FAIL -> FAIL; relevance and
  alignment PASS -> PASS; otherwise UNKNOWN.
- rating_label(): PASS = "Adequate", FAIL = "Inadequate", everything else = "Requires
  Human Review". Reuse AssessmentResult; do not add a second enum.

Acceptance: well_documented = Adequate, design_issue = Inadequate, the other three =
Requires Human Review.
```

## Phase 6: Gap Drafting Agent

```
Build app/gap_drafting.draft_gaps(control, design_assessment). Draft only when the
conclusion is FAIL. One Gap per failed dimension: title, description (the observation),
root_cause_category (e.g. "Segregation of duties"), recommendation. Risk is NOT a Gap
field; the UI reuses control.risk.risk_description. action_owner and action_date are
never set by the agent.

Acceptance: design_issue yields 1 gap; every other case yields none.
```

## Phase 7: API layer

```
Build FastAPI app (CORS for :5174). Endpoints: GET /api/health, /api/pilot/cases,
/api/pilot/cases/{id}; POST /api/records/validate, /api/questions/generate,
/api/transcripts/extract, /api/design-assessment/assess, /api/gaps/draft,
/api/review/validate, /api/export/excel (added in Phase 10). Return safe validation errors
as [{field, message}]; never stack traces.

Acceptance: TestClient tests for the full pipeline over each pilot case and for 422s.
```

## Phase 8: Frontend pipeline UI

```
Build the React UI with a green brand theme (#86BC25) and black/grey ink palette.
Numbered section cards, each disabled until its prerequisite exists:
1 RACM Input (no pilot or fixture controls in the UI: an open "Upload RACM file from your
  computer" dropdown that reads an Excel .xlsx or a .json record, a "paste JSON" advanced
  option, full RACM field display). Excel goes to POST /api/convert-excel-to-racm; JSON, paste
  and Excel all end in the same backend validation.
2 Walkthrough Questions
3 Walkthrough Transcript ("Upload transcript" for a .docx or .txt file + textarea + Process). .docx goes to POST /api/extract-text-from-document (python-docx); .txt is read in the browser. Upload is locked until the questions are approved, rejects an empty file,
  and any new or edited transcript needs approval again before it can be processed.
  Use a visually hidden but focusable file input, not display:none, so it stays keyboard
  accessible.
Phase heading "Documentation Extraction":
4 Structured Control Documentation (How shown as a numbered list; source disclosures)
5 Draft Control Description (blank line between points)
Phase heading "Design Assessment": 6 rating badge + three dimension cards
Phase heading "Gap Assessment": 7 gap cards (Title, Observation, Risk, Root Cause,
  Recommendation)
There is no separate Missing Information card in the UI (the backend still records it).
Show the active control_id in the header. Re-running an earlier step invalidates
everything downstream.

Per-step human review (every step). Add one shared Reviewer ID field at the top, and a
reusable StepReview strip at the bottom of each of these cards: Approve <Step> / Request
Changes (with a comment). Steps: RACM Input, Questions, Transcript, Documentation, Draft
Description, Design Assessment, Gaps. Rules:
- Each step is locked (real disabled attributes, not just styling) until the previous one is
  approved. Question generation stays locked until the loaded RACM is approved, and loading a
  different control clears that approval. The transcript must be approved before it can be processed, and the final
  Approve/Edit/Reject in step 8 stays locked until Gaps is approved.
- Reuse POST /api/review/validate for every step approval or change request, so the backend's
  own rules apply (reviewer id required, comment required for changes). Surface its errors.
- Request Changes withdraws that step's approval and every later one.
- Editing or re-running a step clears its approval and every later one, plus any submitted
  final review.
- Reviewer edits are layered over the untouched AI output: question wording (step 2),
  each extracted attribute (step 4), the draft description (step 6), and gap text (step 8).
  Later steps and the export use the edited values.
- Approved steps show "<Step> Approved" and "Approved by <reviewer>".

Acceptance: RTL tests per screen; tests that each step stays locked until the previous one is
approved, that Request Changes relocks later steps, that edits flow into the next step's
payload, and that backend errors are surfaced; live click-through of one pilot case.
```

## Phase 9: Human review and gap editing

```
8 Human Review: Approve / Edit / Reject, Reviewer ID, reject-reason box, edited-description
box for Edit, a Submit button, and an audit panel (AI draft unchanged vs reviewer-final).
Per gap card: Edit/Done toggle for title, observation, root cause and recommendation (Risk
stays read-only), plus Action Owner text box and Action Date native date picker, keyed by
gap_id.
Button labels reflect state: Validate & Load -> Validated & Loaded, Generate Walkthrough Questions
-> Questions Generated, Upload transcript -> Transcript Uploaded, Process
Transcript -> Transcript Processed, Assess Control Design -> Control Design Assessed, Draft
Gaps -> Gaps Drafted, Approve/Edit/Reject -> Approved/Editing/Rejected, Submit Review
Decision -> Review Decision Submitted (disabled; resets if a different decision is
chosen). Async buttons show "Loading...", "Assessing..." and similar while running.

Acceptance: tests for each label, edit-then-export payload, and backend error surfacing.
```

## Phase 10: Excel export

```
POST /api/export/excel (openpyxl). Returns 409 unless the review decision is approved or
approved_with_edits. The "Download RACM Excel" button appears only then, sends the final
documentation, design assessment, edited gaps with owner/date, and review, and relabels
to "RACM Excel Downloaded" while staying enabled.
Layout (one row per control): row 1 merged group labels, row 2 headers, row 3 data.
- Orange (RACM input): Engagement Details | Control Details (ID, Reference, Title) |
  Risk Details (ID, Description) | Control Details (Objective ... ToE procedures)
- Light green (Structured Control Documentation): Applicable, Reason if Not Applicable,
  What, Who, When, Why, Where, How. No "Draft Control Description" column.
  Applicable: Adequate -> "Yes"/"Yes"; Inadequate -> "No" + conclusion rationale, then
  "Relevance: ..." if present, "N/A" fallback; otherwise blank.
- Olive (Gap): Gap, Gap title, Reason (objective + gap description), RCA, Action Plan,
  Action Owner, Action Date. "N/A" when no gap. Several gaps stay on one row as a
  numbered list ("1. ... 2. ..."). A single Action Date is a real Excel date (yyyy-mm-dd
  format plus date validation); blank owner/date means "not filled in", never "N/A".

Acceptance: workbook tests for headers, merges, fills, applicable logic, multi-gap
numbering, and a live export of design_issue and well_documented.
```

## Phase 11: Hardening

```
Excel RACM import (app/excel_import.py): the standard headers are the app's own Excel export
headers (Engagement ID, Client, OpCo, Area, Mega Process, Process, Sub-process, Control ID,
Control Reference, Control Title, Risk ID, Risk Description, Control Objective, Suggested Control
Description, Control Frequency, Control Nature, Control Type, Expected Evidence, Suggested Test
Procedures (ToD)/(ToE)), so an exported RACM can be uploaded again. Accept common older names as
aliases (Risk Ref, Control Ref, Process Name, Suggested Control, ...). Require only Risk ID and a
control identifier. Detect the header row in the top 10 rows, prefer a sheet named 'RACM Upload',
read only the first control row, and assume nothing about the client (default 'Not specified').
Reject legacy .xls and .doc with a clear 'Save As .xlsx/.docx' message, since openpyxl and
python-docx cannot read them.

Optional extras, all off unless configured: ANTHROPIC_API_KEY (from the environment only, never a
file in the repo) lets Claude tidy the HOW answer, with a deterministic fallback; ANTHROPIC_MODEL
picks the model; ASSUREAI_CONDENSE=0 turns off the short-phrase wording of the structured documentation (on by
default). Because a short phrase can drop evidence (who performs AND reviews), the independence
check in the design assessment also reads the verbatim source excerpts, not only the documented value. Tests must
clear these variables so they never call an outside service.

Structured documentation wording (app/transcript_extraction/condenser.py): each of the six attributes
is a short documentation phrase, never a quote of the conversation. WHEN is a frequency keyword
(every Thursday -> Weekly, once a year -> Yearly, twice a year -> Twice a year, quarterly, monthly,
daily, fortnightly) or, for an event, 'Triggered every time/whenever/when ...'; if both are given,
both. WHO is the role or team names (AP Supervisor, Finance Manager, Helpdesk Team, CAB), not the
sentence; a first-person answer with no role named keeps its words. WHY is 'To <verb> ...' (this
prevents X -> To prevent X). WHERE is the system or location (ServiceNow, Finance System, Shared
Drive Folder “Access Reviews”). WHAT and HOW lose filler and the speaker ('I go through the list'
-> 'Go through the list'), contractions are expanded, and HOW stays a numbered list. Safety rules:
every word comes from the answer (or is a fixed label like Weekly), when a field can't be condensed
confidently the original wording is kept, nothing is ever cut mid-clause, and source excerpts stay
verbatim so the full conversation is one click away under View source. The UI must strip existing
'1.' numbering before it adds its own, or steps show as '1. 1.'.

Sample data: assureai/samples holds a synthetic Excel RACM using the standard headers plus a
matching transcript as .txt and .docx; a test runs them through the whole pipeline so they stay valid.

Pilot clean-up: the pilot dropdown, Load Control button and Load fixture transcript button are gone
from the UI. The assureai/pilot folder and /api/pilot/* endpoints remain only as test fixtures; delete
them (and the tests that use them) once the samples and your own data cover those scenarios.

Run full pytest and vitest and type-check with tsc. Verify live in the browser: upload a
RACM and a transcript, full pipeline, export opened and inspected. Document how to start both
servers.
```

---

## Lessons from the first build

- Check `re.MULTILINE` on any `^`-anchored line regex.
- Pydantic's `model_copy(update=...)` doesn't validate nested dicts. Build real model objects in test helpers.
- React Testing Library throws on duplicate text such as "Adequate" or "Edit". Scope queries or use `getAllBy`.
- Native date inputs are awkward to automate in browser tests.
- On Windows, start the backend as a detached process, or it dies with the session. Upload errors such as 'status code 500' mean the backend is down.
