import { useState } from "react";
import {
  ApiError,
  assessDesign,
  convertExcelToRacm,
  draftGaps,
  exportExcel,
  extractDocumentText,
  extractTranscript,
  generateQuestions,
  validateRecord,
  validateReview,
} from "@/services/api";
import type {
  ControlDocumentation,
  ControlReview,
  DesignAssessment,
  ExtractionResult,
  Gap,
  GapAssessment,
  RacmRecord,
  StepReviewState,
  WalkthroughQuestionSet,
} from "@/types";
import {
  CategoryBadge,
  DraftBadge,
  ErrorBanner,
  PhaseHeading,
  RacmField,
  RatingBadge,
  SectionCard,
  SourceRefDisclosure,
  StepText,
} from "@/components/Shared";
import { StepReview } from "@/components/StepReview";

type ReviewDecision = "approved" | "approved_with_edits" | "needs_revision" | "rejected";

// Every step, starting with the loaded RACM input, needs a human approval before the next one unlocks. Order
// matters: invalidating a step clears its approval and every later one.
const STEP_ORDER = ["racm", "questions", "transcript", "documentation", "description", "design", "gaps"] as const;
type StepKey = (typeof STEP_ORDER)[number];

function readFileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsText(file);
  });
}

export default function App() {
  // ---------- Screen 1: RACM input ----------
  const [rawJsonInput, setRawJsonInput] = useState("");
  const [record, setRecord] = useState<RacmRecord | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingRecord, setLoadingRecord] = useState(false);

  // ---------- Screen 2: walkthrough questions ----------
  const [questions, setQuestions] = useState<WalkthroughQuestionSet | null>(null);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  const [generatingQuestions, setGeneratingQuestions] = useState(false);
  // Reviewer edits to the generated question wording, keyed by question_id.
  const [editedQuestions, setEditedQuestions] = useState<Record<string, string>>({});
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);

  // ---------- Per-step human review (every step, RACM input through gaps) ----------
  const [stepReviews, setStepReviews] = useState<Partial<Record<StepKey, StepReviewState>>>({});
  const [stepBusy, setStepBusy] = useState<StepKey | null>(null);
  const [stepErrors, setStepErrors] = useState<Partial<Record<StepKey, string>>>({});

  // ---------- Screen 3-6: transcript -> documentation ----------
  const [transcriptText, setTranscriptText] = useState("");
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  // Reviewer edits layered over the extracted documentation (never written
  // back to the AI output - extraction.documentation stays untouched).
  const [editedAttributes, setEditedAttributes] = useState<Record<string, string>>({});
  const [editingAttribute, setEditingAttribute] = useState<string | null>(null);
  const [reviewedDescription, setReviewedDescription] = useState<string | null>(null);
  const [editingDescription, setEditingDescription] = useState(false);

  // ---------- Screen 7: design assessment ----------
  const [design, setDesign] = useState<DesignAssessment | null>(null);
  const [designRatingLabel, setDesignRatingLabel] = useState<string | null>(null);
  const [designError, setDesignError] = useState<string | null>(null);
  const [assessingDesign, setAssessingDesign] = useState(false);

  // ---------- Screen 8: gap drafting ----------
  const [gapAssessment, setGapAssessment] = useState<GapAssessment | null>(null);
  const [gapsError, setGapsError] = useState<string | null>(null);
  const [draftingGaps, setDraftingGaps] = useState(false);
  // Keyed by gap_id - the reviewer fills these in directly on the gap card;
  // they are not produced by the Gap Drafting Agent, only mapped into the
  // Action Owner/Action Date columns at export time.
  const [gapActionOwners, setGapActionOwners] = useState<Record<string, string>>({});
  const [gapActionDates, setGapActionDates] = useState<Record<string, string>>({});
  // Reviewer edits to the AI-drafted gap text itself, keyed by gap_id - a
  // toggleable "Edit" state per gap card, same idea as Section 9's edit of
  // the control description but scoped to one gap at a time.
  const [editingGapIds, setEditingGapIds] = useState<Record<string, boolean>>({});
  const [editedGapFields, setEditedGapFields] = useState<
    Record<string, { gap_title: string; gap_description: string; root_cause_category: string; recommendation: string }>
  >({});

  // ---------- Screen 9: human review ----------
  const [decision, setDecision] = useState<ReviewDecision | null>(null);
  const [reviewerId, setReviewerId] = useState("");
  const [reviewerComments, setReviewerComments] = useState("");
  const [editedDescription, setEditedDescription] = useState("");
  const [submittedReview, setSubmittedReview] = useState<ControlReview | null>(null);
  const [finalDescription, setFinalDescription] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [submittingReview, setSubmittingReview] = useState(false);

  // ---------- Screen 10: RACM Excel export ----------
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportSucceeded, setExportSucceeded] = useState(false);

  // Files the reviewer uploaded from their own computer: just the name for
  // display, plus any read error.
  const [uploadedRacmName, setUploadedRacmName] = useState<string | null>(null);
  const [uploadedTranscriptName, setUploadedTranscriptName] = useState<string | null>(null);
  const [transcriptUploadError, setTranscriptUploadError] = useState<string | null>(null);

  function resetDownstream() {
    setQuestions(null);
    setQuestionsError(null);
    setTranscriptText("");
    setUploadedTranscriptName(null);
    setTranscriptUploadError(null);
    setExtraction(null);
    setExtractError(null);
    setDesign(null);
    setDesignRatingLabel(null);
    setDesignError(null);
    setGapAssessment(null);
    setGapsError(null);
    setGapActionOwners({});
    setGapActionDates({});
    setEditingGapIds({});
    setEditedGapFields({});
    setDecision(null);
    setReviewerComments("");
    setEditedDescription("");
    setSubmittedReview(null);
    setFinalDescription(null);
    setReviewError(null);
    setExportError(null);
    setExportSucceeded(false);
    setEditedQuestions({});
    setEditingQuestionId(null);
    setEditedAttributes({});
    setEditingAttribute(null);
    setReviewedDescription(null);
    setEditingDescription(false);
    setStepReviews({});
    setStepErrors({});
  }

  const stepApproved = (step: StepKey) => stepReviews[step]?.status === "approved";

  // Clears this step's approval and every later one (plus the final review,
  // which was granted on top of them), so nothing stays signed off after
  // something it depended on has changed.
  function invalidateFrom(step: StepKey) {
    const from = STEP_ORDER.indexOf(step);
    setStepReviews((prev) => {
      const next = { ...prev };
      STEP_ORDER.slice(from).forEach((k) => delete next[k]);
      return next;
    });
    setDecision(null);
    setSubmittedReview(null);
    setFinalDescription(null);
    setExportSucceeded(false);
  }

  // Reuses the backend's own ControlReview rules (reviewer id required,
  // comment required when requesting changes) rather than re-implementing
  // them here.
  async function reviewStep(step: StepKey, kind: "approve" | "changes", comment = "") {
    setStepBusy(step);
    setStepErrors((prev) => ({ ...prev, [step]: undefined }));
    try {
      const result = await validateReview(kind === "approve" ? "approved" : "needs_revision", reviewerId, comment);
      if (kind === "changes") invalidateFrom(step);
      setStepReviews((prev) => ({
        ...prev,
        [step]: {
          status: kind === "approve" ? "approved" : "changes_requested",
          reviewer: result.reviewer_id ?? reviewerId,
          comment: comment || undefined,
          reviewed_at: result.reviewed_at,
        },
      }));
    } catch (e) {
      setStepErrors((prev) => ({ ...prev, [step]: (e as ApiError).message }));
    } finally {
      setStepBusy(null);
    }
  }

  // Shared by the paste box and the file uploads: whichever way a RACM arrives, the
  // backend validates it the same way. uploadName is only set for uploads, which also
  // show the converted record in the JSON box for review.
  async function loadRecordWith(load: () => Promise<RacmRecord>, uploadName?: string) {
    setLoadingRecord(true);
    setLoadError(null);
    try {
      const validated = await load();
      setRecord(validated);
      if (uploadName) setRawJsonInput(JSON.stringify(validated, null, 2));
      setUploadedRacmName(uploadName ?? null);
      resetDownstream();
    } catch (e) {
      if (e instanceof SyntaxError) {
        setLoadError(`Invalid JSON: ${e.message}`);
      } else {
        setLoadError((e as ApiError).message);
      }
      setRecord(null);
      setUploadedRacmName(null);
    } finally {
      setLoadingRecord(false);
    }
  }

  async function handleValidatePastedJson() {
    await loadRecordWith(async () => validateRecord(JSON.parse(rawJsonInput)));
  }

  async function handleRacmFile(file: File) {
    if (file.name.toLowerCase().endsWith(".json")) {
      try {
        const text = await readFileText(file);
        setRawJsonInput(text);
        await loadRecordWith(async () => validateRecord(JSON.parse(text)), file.name);
      } catch (e) {
        setLoadError((e as Error).message);
      }
      return;
    }
    // Excel (and anything else) is read by the backend, which also gives the
    // clear message for formats it cannot read.
    await loadRecordWith(() => convertExcelToRacm(file), file.name);
  }

  async function handleTranscriptFile(file: File) {
    setTranscriptUploadError(null);
    const name = file.name.toLowerCase();
    try {
      let text: string;
      if (name.endsWith(".txt")) {
        text = await readFileText(file);
      } else if (name.endsWith(".docx") || name.endsWith(".doc")) {
        text = await extractDocumentText(file);
      } else {
        setTranscriptUploadError(`${file.name} is not supported - upload a .docx or .txt transcript.`);
        return;
      }
      if (!text.trim()) {
        setTranscriptUploadError(`${file.name} is empty.`);
        return;
      }
      setTranscriptText(text);
      setUploadedTranscriptName(file.name);
      invalidateFrom("transcript");
    } catch (e) {
      setTranscriptUploadError((e as Error).message);
    }
  }

  async function handleGenerateQuestions() {
    if (!record) return;
    setGeneratingQuestions(true);
    setQuestionsError(null);
    try {
      const result = await generateQuestions(record);
      setQuestions(result);
      setEditedQuestions({});
      setEditingQuestionId(null);
      invalidateFrom("questions");
    } catch (e) {
      setQuestionsError((e as ApiError).message);
    } finally {
      setGeneratingQuestions(false);
    }
  }

  async function handleProcessTranscript() {
    if (!record || !effectiveQuestions) return;
    setExtracting(true);
    setExtractError(null);
    try {
      const result = await extractTranscript(record, effectiveQuestions, transcriptText);
      setExtraction(result);
      setEditedAttributes({});
      setEditingAttribute(null);
      setReviewedDescription(null);
      setEditingDescription(false);
      invalidateFrom("documentation");
      // Re-processing invalidates any design assessment/gaps drafted from a
      // previous extraction - those stages must be re-run against the new
      // documentation, not silently left showing stale results.
      setDesign(null);
      setDesignRatingLabel(null);
      setGapAssessment(null);
      setGapActionOwners({});
      setGapActionDates({});
      setEditingGapIds({});
      setEditedGapFields({});
    } catch (e) {
      setExtractError((e as ApiError).message);
    } finally {
      setExtracting(false);
    }
  }

  async function handleAssessDesign() {
    if (!record || !doc) return;
    setAssessingDesign(true);
    setDesignError(null);
    try {
      const control = { ...record.control, documentation: doc };
      const result = await assessDesign(control);
      setDesign(result.design_assessment);
      setDesignRatingLabel(result.rating_label);
      invalidateFrom("design");
      setGapAssessment(null); // stale relative to the freshly (re-)assessed design
      setGapActionOwners({});
      setGapActionDates({});
      setEditingGapIds({});
      setEditedGapFields({});
    } catch (e) {
      setDesignError((e as ApiError).message);
    } finally {
      setAssessingDesign(false);
    }
  }

  async function handleDraftGaps() {
    if (!record || !doc || !design) return;
    setDraftingGaps(true);
    setGapsError(null);
    try {
      const control = { ...record.control, documentation: doc };
      const result = await draftGaps(control, design);
      setGapAssessment(result);
      invalidateFrom("gaps");
    } catch (e) {
      setGapsError((e as ApiError).message);
    } finally {
      setDraftingGaps(false);
    }
  }

  function effectiveGap(g: Gap): Gap {
    const edits = editedGapFields[g.gap_id];
    return edits ? { ...g, ...edits } : g;
  }

  function toggleGapEdit(g: Gap) {
    invalidateFrom("gaps"); // reopening a drafted gap for editing withdraws its approval
    setEditingGapIds((prev) => ({ ...prev, [g.gap_id]: !prev[g.gap_id] }));
    setEditedGapFields((prev) =>
      prev[g.gap_id]
        ? prev
        : {
            ...prev,
            [g.gap_id]: {
              gap_title: g.gap_title,
              gap_description: g.gap_description,
              root_cause_category: g.root_cause_category ?? "",
              recommendation: g.recommendation ?? "",
            },
          }
    );
  }

  async function handleSubmitReview() {
    if (!decision) return;
    setSubmittingReview(true);
    setReviewError(null);
    try {
      const result = await validateReview(decision, reviewerId, reviewerComments);
      setSubmittedReview(result);
      if (decision === "approved_with_edits") {
        setFinalDescription(editedDescription);
      } else if (decision === "approved") {
        setFinalDescription(doc?.control_description ?? null);
      } else {
        setFinalDescription(null);
      }
    } catch (e) {
      setReviewError((e as ApiError).message);
    } finally {
      setSubmittingReview(false);
    }
  }

  async function handleExportExcel() {
    if (!record || !doc || !submittedReview) return;
    setExporting(true);
    setExportError(null);
    setExportSucceeded(false);
    try {
      await exportExcel({
        ...record,
        control: {
          ...record.control,
          documentation: {
            ...doc,
            control_description: finalDescription ?? doc.control_description,
          },
          design_assessment: design ?? record.control.design_assessment,
          gap_assessment: {
            ...(gapAssessment ?? record.control.gap_assessment),
            gaps: (gapAssessment ?? record.control.gap_assessment).gaps.map((g) => ({
              ...effectiveGap(g),
              action_owner: gapActionOwners[g.gap_id] || null,
              action_date: gapActionDates[g.gap_id] || null,
            })),
          },
          review: submittedReview,
        },
      });
      setExportSucceeded(true);
    } catch (e) {
      setExportError((e as ApiError).message);
    } finally {
      setExporting(false);
    }
  }

  const effectiveQuestions: WalkthroughQuestionSet | null = questions && {
    ...questions,
    questions: questions.questions.map((q) =>
      editedQuestions[q.question_id] !== undefined ? { ...q, question_text: editedQuestions[q.question_id] } : q
    ),
  };

  // The reviewer's edits layered over the untouched AI extraction.
  const doc: ControlDocumentation | undefined = extraction ? (() => {
    const base = extraction.documentation;
    const merged: ControlDocumentation = {
      ...base,
      control_description: reviewedDescription ?? base.control_description,
    };
    (["what", "who", "when", "why", "where", "how"] as const).forEach((k) => {
      if (editedAttributes[k] !== undefined) merged[k] = { ...base[k], value: editedAttributes[k] };
    });
    return merged;
  })() : undefined;
  const attributes: Array<{ key: keyof NonNullable<typeof doc>; label: string }> = [
    { key: "what", label: "What" },
    { key: "who", label: "Who" },
    { key: "when", label: "When" },
    { key: "why", label: "Why" },
    { key: "where", label: "Where" },
    { key: "how", label: "How" },
  ];

  return (
    <div className="min-h-screen bg-ink-50">
      <header className="bg-ink-950 text-white px-6 py-4 flex items-center gap-3">
        <div className="w-2 h-6 bg-brand-500 rounded-sm" />
        <h1 className="text-lg font-bold">AssureAI Test Harness</h1>
        <span className="text-ink-400 text-sm">
          RACM &rarr; questions &rarr; transcript &rarr; documentation &rarr; design assessment &rarr; gaps &rarr; review
        </span>
        {record && (
          <span className="ml-auto badge bg-brand-500 text-white font-mono">
            Active control: {record.control.control_id}
          </span>
        )}
      </header>

      <main className="max-w-4xl mx-auto px-6 py-6 space-y-5">
        <div className="card flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Reviewer ID</span>
            <input
              className="input"
              value={reviewerId}
              onChange={(e) => setReviewerId(e.target.value)}
              placeholder="e.g. j.smith"
            />
          </label>
          <p className="text-xs text-ink-500 flex-1 min-w-[14rem]">
            Every step, starting with the loaded RACM, needs your approval before the next one unlocks. Changing a step
            clears its approval and every later one.
          </p>
        </div>

        {/* Screen 1 */}
        <SectionCard number={1} title="RACM Input">
          <div className="space-y-3">
            <details open>
              <summary className="cursor-pointer text-sm text-brand-700 hover:underline select-none">
                Upload RACM file from your computer
              </summary>
              <div className="mt-2 space-y-2">
                <input
                  type="file"
                  accept=".xlsx,.json,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  className="input"
                  aria-label="Upload RACM file"
                  disabled={loadingRecord}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) void handleRacmFile(file);
                  }}
                />
                <p className="text-xs text-ink-500">
                  An Excel RACM (.xlsx) using the standard headers, or a RACM control record in JSON. Either way it is
                  validated exactly like a pasted record.
                </p>
                {loadingRecord && <p className="text-xs text-ink-600">Reading the file...</p>}
                {uploadedRacmName && <p className="text-xs text-ink-600">Loaded from {uploadedRacmName}</p>}
              </div>
            </details>

            <details>
              <summary className="cursor-pointer text-sm text-brand-700 hover:underline select-none">
                Advanced: paste RACM JSON directly
              </summary>
              <div className="mt-2 space-y-2">
                <textarea
                  className="input font-mono text-xs h-32"
                  value={rawJsonInput}
                  onChange={(e) => setRawJsonInput(e.target.value)}
                  placeholder="Paste a RACMControlRecord JSON object"
                />
                <button className="btn-secondary" onClick={handleValidatePastedJson} disabled={loadingRecord}>
                  {loadingRecord ? "Validating..." : record ? "Validated & Loaded" : "Validate & Load"}
                </button>
              </div>
            </details>

            <ErrorBanner message={loadError} />

            {record && (
              <div data-testid="control-context" className="rounded-lg border border-ink-200 bg-ink-50 p-4 text-sm">
                <div className="mb-2">
                  <span className="font-semibold">Control:</span> {record.control.control_id} -{" "}
                  {record.control.control_title}
                </div>
                {/* Field order mirrors the client RACM tracker: OpCo through
                    Test Procedures TOE. Columns between "Suggested Control"
                    and "Control evidence" in that tracker aren't modeled yet
                    (not yet supplied) - Frequency/Type/Nature exist on the
                    schema but sit outside this specific header set for now. */}
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                  <RacmField label="OpCo" value={record.engagement.opco} />
                  <RacmField label="Area" value={record.engagement.area} />
                  <RacmField label="Mega Process" value={record.engagement.mega_process} />
                  <RacmField label="Process Name" value={record.engagement.process} />
                  <RacmField label="Sub-process" value={record.engagement.subprocess} />
                  <RacmField label="Risk Ref" value={record.control.risk.risk_id} />
                  <RacmField label="Risk Description" value={record.control.risk.risk_description} wide />
                  <RacmField label="Control Objective" value={record.control.control_objective} wide />
                  <RacmField label="Control Ref" value={record.control.control_reference} />
                  <RacmField label="Suggested Control" value={record.control.suggested_control_description} wide />
                  <RacmField label="Control Evidence" value={record.control.expected_evidence} wide />
                  <RacmField label="Test Procedures TOD" value={record.control.suggested_test_procedures_tod} wide />
                  <RacmField label="Test Procedures TOE" value={record.control.suggested_test_procedures_toe} wide />
                </dl>
              </div>
            )}
            <StepReview
              label="RACM Input"
              review={stepReviews.racm}
              canReview={!!record}
              busy={stepBusy === "racm"}
              error={stepErrors.racm}
              onApprove={() => reviewStep("racm", "approve")}
              onRequestChanges={(c) => reviewStep("racm", "changes", c)}
            />
          </div>
        </SectionCard>

        {/* Screen 2 */}
        <SectionCard number={2} title="Walkthrough Questions" disabled={!stepApproved("racm")}>
          <div className="space-y-3">
            <button
              className="btn-primary"
              onClick={handleGenerateQuestions}
              disabled={!record || generatingQuestions || !stepApproved("racm")}
            >
              {generatingQuestions ? "Generating..." : questions ? "Questions Generated" : "Generate Walkthrough Questions"}
            </button>
            <ErrorBanner message={questionsError} />
            {effectiveQuestions && (
              <ul className="space-y-2">
                {effectiveQuestions.questions.map((q) => (
                  <li key={q.question_id} className="rounded-lg border border-ink-200 p-3 text-sm">
                    <div className="flex items-center gap-2 mb-1">
                      <CategoryBadge category={q.category} />
                      {!q.required && <span className="badge bg-ink-100 text-ink-500">optional</span>}
                      <button
                        className="btn-secondary ml-auto"
                        aria-label={
                          editingQuestionId === q.question_id
                            ? `Finish editing question ${q.question_id}`
                            : `Edit question ${q.question_id}`
                        }
                        onClick={() => setEditingQuestionId(editingQuestionId === q.question_id ? null : q.question_id)}
                      >
                        {editingQuestionId === q.question_id ? "Done" : "Edit"}
                      </button>
                    </div>
                    {editingQuestionId === q.question_id ? (
                      <textarea
                        className="input h-16"
                        aria-label={`Question text ${q.question_id}`}
                        value={q.question_text}
                        onChange={(e) => {
                          setEditedQuestions((prev) => ({ ...prev, [q.question_id]: e.target.value }));
                          invalidateFrom("questions");
                        }}
                      />
                    ) : (
                      <p className="font-medium">{q.question_text}</p>
                    )}
                    <details className="mt-1 text-xs text-ink-500">
                      <summary className="cursor-pointer select-none">Details</summary>
                      <div className="mt-1 space-y-0.5">
                        <div>ID: <span className="font-mono">{q.question_id}</span></div>
                        <div>Purpose: {q.purpose}</div>
                        <div>Source fields: {q.source_fields.join(", ") || "-"}</div>
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            )}
            <StepReview
              label="Questions"
              review={stepReviews.questions}
              canReview={!!questions}
              busy={stepBusy === "questions"}
              error={stepErrors.questions}
              onApprove={() => reviewStep("questions", "approve")}
              onRequestChanges={(c) => reviewStep("questions", "changes", c)}
            />
          </div>
        </SectionCard>

        {/* Screen 3 */}
        <SectionCard number={3} title="Walkthrough Transcript" disabled={!stepApproved("questions")}>
          <div className="space-y-3">
            <div className="flex gap-2">
              <label
                className={`btn-secondary cursor-pointer focus-within:ring-2 focus-within:ring-brand-500 ${
                  !stepApproved("questions") ? "opacity-50 pointer-events-none" : ""
                }`}
              >
                {uploadedTranscriptName ? "Transcript Uploaded" : "Upload transcript"}
                <input
                  type="file"
                  accept=".docx,.txt,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  className="sr-only"
                  aria-label="Upload transcript file"
                  disabled={!stepApproved("questions")}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) void handleTranscriptFile(file);
                  }}
                />
              </label>
              {uploadedTranscriptName && (
                <span className="self-center text-xs text-ink-600">Uploaded: {uploadedTranscriptName}</span>
              )}
            </div>
            <ErrorBanner message={transcriptUploadError} />
            <textarea
              className="input font-mono text-xs h-48"
              value={transcriptText}
              onChange={(e) => {
                setTranscriptText(e.target.value);
                setUploadedTranscriptName(null);
                invalidateFrom("transcript");
              }}
              disabled={!stepApproved("questions")}
              placeholder="Paste the walkthrough transcript text here"
              aria-label="Transcript text"
            />
            <StepReview
              label="Transcript"
              review={stepReviews.transcript}
              canReview={stepApproved("questions") && transcriptText.trim() !== ""}
              busy={stepBusy === "transcript"}
              error={stepErrors.transcript}
              onApprove={() => reviewStep("transcript", "approve")}
              onRequestChanges={(c) => reviewStep("transcript", "changes", c)}
            />
            <button
              className="btn-primary"
              onClick={handleProcessTranscript}
              disabled={!questions || extracting || !stepApproved("transcript")}
            >
              {extracting ? "Processing..." : extraction ? "Transcript Processed" : "Process Transcript"}
            </button>
            <ErrorBanner message={extractError} />
          </div>
        </SectionCard>

        {/* Documentation Extraction phase - the 5 Ws + How, drawn from the transcript */}
        <PhaseHeading>Documentation Extraction</PhaseHeading>

        {/* Screen 4 */}
        <SectionCard number={4} title="Structured Control Documentation" disabled={!doc}>
          {doc && (
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {attributes.map(({ key, label }) => {
                  const attr = doc[key] as { value?: string | null; source_references: any[] };
                  const isEditing = editingAttribute === String(key);
                  return (
                    <div key={String(key)} data-testid={`doc-${String(key)}`} className="rounded-lg border border-ink-200 p-3 text-sm">
                      <div className="flex items-center mb-1">
                        <div className="font-semibold uppercase text-xs text-ink-500">{label}</div>
                        <button
                          className="btn-secondary ml-auto"
                          aria-label={isEditing ? `Finish editing ${label}` : `Edit ${label}`}
                          onClick={() => setEditingAttribute(isEditing ? null : String(key))}
                        >
                          {isEditing ? "Done" : "Edit"}
                        </button>
                      </div>
                      {isEditing ? (
                        <textarea
                          className="input h-20"
                          aria-label={`${label} value`}
                          value={attr.value ?? ""}
                          onChange={(e) => {
                            setEditedAttributes((prev) => ({ ...prev, [String(key)]: e.target.value }));
                            invalidateFrom("documentation");
                          }}
                        />
                      ) : attr.value ? (
                        <>
                          {key === "how" ? <StepText text={attr.value} /> : <p>{attr.value}</p>}
                          <SourceRefDisclosure refs={attr.source_references} />
                        </>
                      ) : (
                        <p className="text-ink-400 italic">Not established</p>
                      )}
                    </div>
                  );
                })}
              </div>
              <StepReview
                label="Documentation"
                review={stepReviews.documentation}
                canReview={!!doc}
                busy={stepBusy === "documentation"}
                error={stepErrors.documentation}
                onApprove={() => reviewStep("documentation", "approve")}
                onRequestChanges={(c) => reviewStep("documentation", "changes", c)}
              />
            </div>
          )}
        </SectionCard>

        {/* Screen 5 */}
        <SectionCard number={5} title="Draft Control Description" disabled={!stepApproved("documentation")}>
          {doc && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <DraftBadge />
                <button
                  className="btn-secondary ml-auto"
                  aria-label={editingDescription ? "Finish editing draft description" : "Edit draft description"}
                  onClick={() => setEditingDescription((v) => !v)}
                >
                  {editingDescription ? "Done" : "Edit"}
                </button>
              </div>
              {editingDescription ? (
                <textarea
                  className="input h-40"
                  aria-label="Draft control description"
                  value={doc.control_description ?? ""}
                  onChange={(e) => {
                    setReviewedDescription(e.target.value);
                    invalidateFrom("description");
                  }}
                />
              ) : (
                <p className="rounded-lg border border-ink-200 bg-ink-50 p-3 text-sm whitespace-pre-wrap">
                  {doc.control_description ?? "(Insufficient information to draft a description.)"}
                </p>
              )}
              <StepReview
                label="Draft Description"
                review={stepReviews.description}
                canReview={stepApproved("documentation")}
                busy={stepBusy === "description"}
                error={stepErrors.description}
                onApprove={() => reviewStep("description", "approve")}
                onRequestChanges={(c) => reviewStep("description", "changes", c)}
              />
            </div>
          )}
        </SectionCard>

        {/* Design Assessment phase - judges the documentation above, never re-reads the transcript */}
        <PhaseHeading>Design Assessment</PhaseHeading>

        {/* Screen 6 */}
        <SectionCard number={6} title="Design Assessment" disabled={!stepApproved("description")}>
          <div className="space-y-3">
            <button
              className="btn-primary"
              onClick={handleAssessDesign}
              disabled={!doc || assessingDesign || !stepApproved("description")}
            >
              {assessingDesign ? "Assessing..." : design ? "Control Design Assessed" : "Assess Control Design"}
            </button>
            <ErrorBanner message={designError} />
            {design && designRatingLabel && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">Rating:</span>
                  <RatingBadge label={designRatingLabel} />
                </div>
                <p className="text-sm">{design.conclusion_rationale}</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {(
                    [
                      ["Completeness", design.completeness],
                      ["Relevance", design.relevance],
                      ["Risk/Objective/Control Alignment", design.risk_objective_control_alignment],
                    ] as const
                  ).map(([label, dim]) => (
                    <div key={label} className="rounded-lg border border-ink-200 p-3 text-sm">
                      <div className="font-semibold text-xs uppercase text-ink-500 mb-1">{label}</div>
                      <RatingBadge label={
                        dim.result === "pass" ? "Adequate" : dim.result === "fail" ? "Inadequate" : "Requires Human Review"
                      } />
                      <p className="mt-1 text-xs text-ink-600">{dim.rationale}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <StepReview
              label="Design Assessment"
              review={stepReviews.design}
              canReview={!!design}
              busy={stepBusy === "design"}
              error={stepErrors.design}
              onApprove={() => reviewStep("design", "approve")}
              onRequestChanges={(c) => reviewStep("design", "changes", c)}
            />
          </div>
        </SectionCard>

        {/* Gap Assessment phase - only drafts a gap when design assessment found a specific, evidence-backed flaw */}
        <PhaseHeading>Gap Assessment</PhaseHeading>

        {/* Screen 7 */}
        <SectionCard number={7} title="Gap Drafting" disabled={!stepApproved("design")}>
          <div className="space-y-3">
            <button
              className="btn-primary"
              onClick={handleDraftGaps}
              disabled={!design || draftingGaps || !stepApproved("design")}
            >
              {draftingGaps ? "Drafting..." : gapAssessment ? "Gaps Drafted" : "Draft Gaps"}
            </button>
            <ErrorBanner message={gapsError} />
            {gapAssessment && gapAssessment.gaps.length === 0 && (
              <p className="text-sm text-ink-500">
                No gap drafted - design assessment did not conclude Inadequate for this control.
              </p>
            )}
            {gapAssessment && gapAssessment.gaps.length > 0 && (
              <ul className="space-y-2">
                {gapAssessment.gaps.map((g) => {
                  const isEditing = !!editingGapIds[g.gap_id];
                  const edited = editedGapFields[g.gap_id];
                  const effective = effectiveGap(g);
                  return (
                    <li key={g.gap_id} className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm space-y-2">
                      {isEditing ? (
                        <div className="space-y-2">
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="font-medium">Gap title</span>
                            <input
                              className="input"
                              value={edited?.gap_title ?? g.gap_title}
                              onChange={(e) =>
                                setEditedGapFields((prev) => ({
                                  ...prev,
                                  [g.gap_id]: { ...(prev[g.gap_id] ?? effective), gap_title: e.target.value },
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="font-medium">Observation</span>
                            <textarea
                              className="input h-20"
                              value={edited?.gap_description ?? g.gap_description}
                              onChange={(e) =>
                                setEditedGapFields((prev) => ({
                                  ...prev,
                                  [g.gap_id]: { ...(prev[g.gap_id] ?? effective), gap_description: e.target.value },
                                }))
                              }
                            />
                          </label>
                          <div>
                            <span className="font-semibold">Risk:</span> {record?.control.risk.risk_description}
                          </div>
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="font-medium">Root Cause</span>
                            <input
                              className="input"
                              value={edited?.root_cause_category ?? g.root_cause_category ?? ""}
                              onChange={(e) =>
                                setEditedGapFields((prev) => ({
                                  ...prev,
                                  [g.gap_id]: { ...(prev[g.gap_id] ?? effective), root_cause_category: e.target.value },
                                }))
                              }
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-sm">
                            <span className="font-medium">Recommendation</span>
                            <textarea
                              className="input h-20"
                              value={edited?.recommendation ?? g.recommendation ?? ""}
                              onChange={(e) =>
                                setEditedGapFields((prev) => ({
                                  ...prev,
                                  [g.gap_id]: { ...(prev[g.gap_id] ?? effective), recommendation: e.target.value },
                                }))
                              }
                            />
                          </label>
                        </div>
                      ) : (
                        <>
                          <div className="font-semibold text-red-800">{effective.gap_title}</div>
                          <div>
                            <span className="font-semibold">Observation:</span> {effective.gap_description}
                          </div>
                          <div>
                            <span className="font-semibold">Risk:</span> {record?.control.risk.risk_description}
                          </div>
                          {effective.root_cause_category && (
                            <div>
                              <span className="font-semibold">Root Cause:</span> {effective.root_cause_category}
                            </div>
                          )}
                          {effective.recommendation && (
                            <div>
                              <span className="font-semibold">Recommendation:</span> {effective.recommendation}
                            </div>
                          )}
                        </>
                      )}
                      <div className="flex gap-3 pt-1 items-end">
                        <label className="flex flex-col gap-1 text-sm flex-1">
                          <span className="font-medium">Action Owner</span>
                          <input
                            className="input"
                            value={gapActionOwners[g.gap_id] ?? ""}
                            onChange={(e) => setGapActionOwners((prev) => ({ ...prev, [g.gap_id]: e.target.value }))}
                            placeholder="e.g. J. Smith"
                          />
                        </label>
                        <label className="flex flex-col gap-1 text-sm">
                          <span className="font-medium">Action Date</span>
                          <input
                            type="date"
                            className="input"
                            value={gapActionDates[g.gap_id] ?? ""}
                            onChange={(e) => setGapActionDates((prev) => ({ ...prev, [g.gap_id]: e.target.value }))}
                          />
                        </label>
                        <button className="btn-secondary" onClick={() => toggleGapEdit(g)}>
                          {isEditing ? "Done" : "Edit"}
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <StepReview
              label="Gaps"
              review={stepReviews.gaps}
              canReview={!!gapAssessment}
              busy={stepBusy === "gaps"}
              error={stepErrors.gaps}
              onApprove={() => reviewStep("gaps", "approve")}
              onRequestChanges={(c) => reviewStep("gaps", "changes", c)}
            />
          </div>
        </SectionCard>

        {/* Screen 8 */}
        <SectionCard number={8} title="Human Review" disabled={!stepApproved("gaps")}>
          <div className="space-y-3">
            <div className="flex gap-2 flex-wrap">
              <button
                className="btn-primary"
                onClick={() => setDecision("approved")}
                disabled={!stepApproved("gaps")}
                aria-pressed={decision === "approved"}
              >
                {decision === "approved" ? "Approved" : "Approve"}
              </button>
              <button
                className="btn-secondary"
                onClick={() => {
                  setDecision("approved_with_edits");
                  setEditedDescription(doc?.control_description ?? "");
                }}
                disabled={!stepApproved("gaps")}
                aria-pressed={decision === "approved_with_edits"}
              >
                {decision === "approved_with_edits" ? "Editing" : "Edit"}
              </button>
              <button
                className="btn-danger"
                onClick={() => setDecision("rejected")}
                disabled={!stepApproved("gaps")}
                aria-pressed={decision === "rejected"}
              >
                {decision === "rejected" ? "Rejected" : "Reject"}
              </button>
            </div>

            {decision === "approved_with_edits" && (
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Edited control description (final)</span>
                <textarea
                  className="input h-24"
                  value={editedDescription}
                  onChange={(e) => setEditedDescription(e.target.value)}
                />
              </label>
            )}

            {decision === "rejected" && (
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Reason for rejection (required)</span>
                <textarea
                  className="input h-20"
                  value={reviewerComments}
                  onChange={(e) => setReviewerComments(e.target.value)}
                  placeholder="Explain why this draft is being rejected"
                />
              </label>
            )}

            {decision && (
              <button
                className="btn-primary"
                onClick={handleSubmitReview}
                disabled={submittingReview || (!!submittedReview && submittedReview.decision === decision)}
              >
                {submittingReview
                  ? "Submitting..."
                  : submittedReview && submittedReview.decision === decision
                  ? "Review Decision Submitted"
                  : "Submit Review Decision"}
              </button>
            )}

            <ErrorBanner message={reviewError} />

            {submittedReview && (
              <div className="rounded-lg border border-brand-300 bg-brand-50 p-3 text-sm space-y-2">
                <div className="font-semibold text-brand-800">
                  Review recorded: {submittedReview.decision.replace(/_/g, " ")}
                </div>
                <details open className="text-xs text-ink-600">
                  <summary className="cursor-pointer font-semibold select-none">Review history / Audit details</summary>
                  <div className="mt-2 space-y-2">
                    <div>
                      <span className="font-semibold">AI-generated draft (unchanged):</span>
                      <p className="whitespace-pre-wrap italic">{extraction?.documentation.control_description}</p>
                    </div>
                    <div>
                      <span className="font-semibold">Reviewer decision:</span> {submittedReview.decision}
                    </div>
                    <div>
                      <span className="font-semibold">Reviewer:</span> {submittedReview.reviewer_id}
                    </div>
                    {submittedReview.reviewer_comments && (
                      <div>
                        <span className="font-semibold">Reviewer comments:</span> {submittedReview.reviewer_comments}
                      </div>
                    )}
                    {finalDescription !== null && (
                      <div>
                        <span className="font-semibold">Reviewer-final value:</span>
                        <p className="whitespace-pre-wrap">{finalDescription}</p>
                      </div>
                    )}
                  </div>
                </details>
                {(submittedReview.decision === "approved" || submittedReview.decision === "approved_with_edits") && (
                  <div className="pt-1">
                    <button className="btn-primary" onClick={handleExportExcel} disabled={exporting}>
                      {exporting ? "Exporting..." : exportSucceeded ? "RACM Excel Downloaded" : "Download RACM Excel"}
                    </button>
                    <ErrorBanner message={exportError} />
                  </div>
                )}
              </div>
            )}
          </div>
        </SectionCard>
      </main>
    </div>
  );
}
