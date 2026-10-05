import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import App from "./App";
import { ApiError } from "@/services/api";
import type { ExtractionResult, RacmRecord, WalkthroughQuestionSet } from "@/types";

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ApiError: actual.ApiError,
    validateRecord: vi.fn(),
    generateQuestions: vi.fn(),
    extractTranscript: vi.fn(),
    assessDesign: vi.fn(),
    draftGaps: vi.fn(),
    validateReview: vi.fn(),
    exportExcel: vi.fn(),
    convertExcelToRacm: vi.fn(),
    extractDocumentText: vi.fn(),
  };
});

import * as api from "@/services/api";

const RECORD: RacmRecord = {
  schema_version: "1.0",
  engagement: {
    engagement_id: "ENG-1",
    client: "Solstice (SYNTHETIC)",
    opco: "Solstice (South Africa) (SYNTHETIC)",
    area: "Information Technology",
    mega_process: "IT General Controls",
    process: "User Access Management",
    subprocess: "Provisioning",
  },
  control: {
    control_id: "PILOT-A-UAM-001",
    control_title: "New User Access Provisioning Approval",
    control_reference: "ITGC-UAM-01",
    risk: { risk_id: "R-1", risk_description: "Inappropriate access could be provisioned." },
    control_objective: "Access requests are approved before provisioning.",
    suggested_control_description: "Manager approves; IT Security provisions per role profile.",
    control_frequency: null,
    control_nature: null,
    control_type: null,
    expected_evidence: "ServiceNow ticket evidencing the approval and provisioning.",
    suggested_test_procedures_tod: "Inspect documentation to confirm independent review is required before provisioning.",
    suggested_test_procedures_toe: "For a sample of new hires, inspect the ServiceNow record to confirm review occurred.",
    documentation: {
      what: { value: null, source_references: [] },
      who: { value: null, source_references: [] },
      when: { value: null, source_references: [] },
      why: { value: null, source_references: [] },
      where: { value: null, source_references: [] },
      how: { value: null, source_references: [] },
      control_description: null,
      missing_information: [],
      source_references: [],
      metadata: { generated_by: "ai" },
    },
    design_assessment: {
      completeness: { result: "not_assessed", source_references: [] },
      relevance: { result: "not_assessed", source_references: [] },
      risk_objective_control_alignment: { result: "not_assessed", source_references: [] },
      first_pass_design_conclusion: "not_assessed",
      rfi_items: [],
      testing_procedures: [],
    },
    gap_assessment: { gaps: [], missing_information: [] },
    review: { decision: "not_reviewed", human_approval_required: true },
  },
};

const QUESTIONS: WalkthroughQuestionSet = {
  control_id: "PILOT-A-UAM-001",
  questions: [
    {
      question_id: "PILOT-A-UAM-001-Q01",
      question_text: 'Please walk me through how "New User Access Provisioning Approval" is carried out.',
      category: "what",
      purpose: "Establish what happens.",
      source_fields: ["control.control_title"],
      required: true,
      answer: null,
      source_references: [],
    },
    {
      question_id: "PILOT-A-UAM-001-Q02",
      question_text: "Who is responsible for performing the control?",
      category: "who",
      purpose: "Identify the performer.",
      source_fields: ["control.control_title"],
      required: true,
      answer: null,
      source_references: [],
    },
  ],
};

function extractionWith(overrides: Partial<ExtractionResult["documentation"]> = {}): ExtractionResult {
  return {
    control_id: "PILOT-A-UAM-001",
    transcript_id: "WT-TEST-UI-01",
    documentation: {
      what: { value: "Manager submits a request.", source_references: [{ source_id: "WT-1", source_type: "walkthrough_transcript", source_name: "t", locator: "L02", excerpt: "Manager submits a request." }] },
      who: { value: "IT Security reviews it.", source_references: [{ source_id: "WT-1", source_type: "walkthrough_transcript", source_name: "t", locator: "L05", excerpt: "IT Security reviews it." }] },
      when: { value: null, source_references: [] },
      why: { value: null, source_references: [] },
      where: { value: null, source_references: [] },
      how: { value: null, source_references: [] },
      control_description: "What: Manager submits a request. Who: IT Security reviews it.",
      missing_information: [
        { field: "documentation.when", reason: "Not discussed in the transcript.", follow_up_question: "How frequently is this performed?", status: "open" },
      ],
      source_references: [],
      metadata: { generated_by: "ai", generated_at: "2026-01-01T00:00:00Z", model_or_author: "deterministic-transcript-extractor-v1" },
      ...overrides,
    },
    questions: QUESTIONS,
  };
}

beforeEach(() => {
  vi.mocked(api.validateRecord).mockResolvedValue(RECORD);
  vi.mocked(api.generateQuestions).mockResolvedValue(QUESTIONS);
  vi.mocked(api.extractTranscript).mockResolvedValue(extractionWith());
  vi.mocked(api.assessDesign).mockResolvedValue({
    design_assessment: {
      completeness: { result: "pass", rationale: "All six attributes documented.", source_references: [] },
      relevance: { result: "pass", rationale: "Clearly relevant.", source_references: [] },
      risk_objective_control_alignment: { result: "pass", rationale: "Aligned.", source_references: [] },
      first_pass_design_conclusion: "pass",
      conclusion_rationale: "Documentation is complete and no issues were detected.",
      rfi_items: [],
      testing_procedures: [],
    },
    rating_label: "Adequate",
  });
  vi.mocked(api.draftGaps).mockResolvedValue({ gaps: [], missing_information: [] });
  vi.mocked(api.validateReview).mockResolvedValue({ decision: "approved", reviewer_id: "jsmith", human_approval_required: true });
  vi.mocked(api.exportExcel).mockResolvedValue(undefined);
});

const TRANSCRIPT_TEXT = "[L01] Interviewer: Who?\n[L02] Interviewee: IT Security.";

const racmFile = () => new File([JSON.stringify(RECORD)], "my-racm.json", { type: "application/json" });

async function loadControl(user: ReturnType<typeof userEvent.setup>) {
  render(<App />);
  await waitFor(() => expect(screen.getByLabelText("Upload RACM file")).toBeInTheDocument());
  await user.type(screen.getByLabelText("Reviewer ID"), "jsmith");
  await user.upload(screen.getByLabelText("Upload RACM file"), racmFile());
  await waitFor(() => expect(screen.getByText(/Active control: PILOT-A-UAM-001/)).toBeInTheDocument());
}

async function uploadTranscript(user: ReturnType<typeof userEvent.setup>, text = TRANSCRIPT_TEXT) {
  await user.upload(
    screen.getByLabelText("Upload transcript file"),
    new File([text], "walkthrough.txt", { type: "text/plain" })
  );
  await screen.findByText("Uploaded: walkthrough.txt");
}

describe("Screen 1: RACM input", () => {
  it("renders control information after loading a control", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    const context = within(screen.getByTestId("control-context"));
    expect(context.getByText(/Inappropriate access could be provisioned/)).toBeInTheDocument();
    expect(context.getByText(/Access requests are approved before provisioning/)).toBeInTheDocument();
    // Full RACM header set, in order: OpCo -> ... -> Test Procedures TOE.
    expect(context.getByText("Solstice (South Africa) (SYNTHETIC)")).toBeInTheDocument();
    expect(context.getByText("Information Technology")).toBeInTheDocument();
    expect(context.getByText("IT General Controls")).toBeInTheDocument();
    expect(context.getByText("User Access Management")).toBeInTheDocument();
    expect(context.getByText("Provisioning")).toBeInTheDocument();
    expect(context.getByText("ITGC-UAM-01")).toBeInTheDocument();
    expect(context.getByText(/Manager approves; IT Security provisions/)).toBeInTheDocument();
    expect(context.getByText(/ServiceNow ticket evidencing/)).toBeInTheDocument();
    expect(context.getByText(/Inspect documentation to confirm independent review/)).toBeInTheDocument();
    expect(context.getByText(/For a sample of new hires/)).toBeInTheDocument();
  });

  it("shows the backend's message when the RACM cannot be validated", async () => {
    vi.mocked(api.validateRecord).mockRejectedValueOnce(new ApiError("control.risk: Field required"));
    const user = userEvent.setup();
    render(<App />);
    await user.upload(screen.getByLabelText("Upload RACM file"), racmFile());
    expect(await screen.findByRole("alert")).toHaveTextContent("control.risk: Field required");
    expect(screen.queryByText(/Active control:/)).not.toBeInTheDocument();
  });

  it("has no pilot or fixture controls", async () => {
    render(<App />);
    expect(screen.queryByLabelText("Pilot control")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load Control" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /fixture/i })).not.toBeInTheDocument();
  });

  it("reports invalid JSON when Validate & Load is pressed with nothing pasted", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Validate & Load" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid JSON");
  });
});

describe("Screen 2: walkthrough questions", () => {
  it("invokes generateQuestions and renders returned questions", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    expect(api.generateQuestions).toHaveBeenCalledWith(RECORD);
    expect(await screen.findByText(/Please walk me through how/)).toBeInTheDocument();
    expect(screen.getByText("Who is responsible for performing the control?")).toBeInTheDocument();
  });
});

async function approveStep(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(await screen.findByRole("button", { name: `Approve ${label}` }));
  await screen.findByRole("button", { name: `${label} Approved` });
}

async function progressToExtraction(user: ReturnType<typeof userEvent.setup>) {
  await loadControl(user);
  await approveStep(user, "RACM Input");
  await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
  await screen.findByText(/Please walk me through how/);
  await approveStep(user, "Questions");
  await uploadTranscript(user);
  await approveStep(user, "Transcript");
  await user.click(screen.getByRole("button", { name: "Process Transcript" }));
  await waitFor(() => expect(api.extractTranscript).toHaveBeenCalled());
}

async function approveDocumentation(user: ReturnType<typeof userEvent.setup>) {
  await approveStep(user, "Documentation");
  await approveStep(user, "Draft Description");
}

async function assessAndApproveDesign(user: ReturnType<typeof userEvent.setup>) {
  await approveDocumentation(user);
  await user.click(screen.getByRole("button", { name: "Assess Control Design" }));
  await screen.findByRole("button", { name: "Control Design Assessed" });
  await approveStep(user, "Design Assessment");
}

async function progressToHumanReview(user: ReturnType<typeof userEvent.setup>) {
  await progressToExtraction(user);
  await assessAndApproveDesign(user);
  await user.click(screen.getByRole("button", { name: "Draft Gaps" }));
  await screen.findByRole("button", { name: "Gaps Drafted" });
  await approveStep(user, "Gaps");
}

describe("Screen 3-4: transcript processing and structured documentation", () => {
  it("submits the transcript and renders extracted documentation with source references", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    expect(await screen.findByText("Manager submits a request.")).toBeInTheDocument();
    expect(screen.getByText("IT Security reviews it.")).toBeInTheDocument();
    const whatCard = within(screen.getByTestId("doc-what"));
    await user.click(whatCard.getByText(/View source/));
    expect(whatCard.getByText(/L02/)).toBeInTheDocument();
  });

  it("renders a multi-sentence HOW value as a numbered list, not one paragraph", async () => {
    vi.mocked(api.extractTranscript).mockResolvedValue(
      extractionWith({
        how: {
          value: "First the engineer logs the change. Then the CAB reviews it. Finally the approval is recorded.",
          source_references: [],
        },
      })
    );
    const user = userEvent.setup();
    await progressToExtraction(user);
    const howCard = within(await screen.findByTestId("doc-how"));
    const items = howCard.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("First the engineer logs the change.");
    expect(items[2]).toHaveTextContent("Finally the approval is recorded.");
  });

  it("shows a HOW value that arrives already numbered as one clean list, without doubled numbers", async () => {
    vi.mocked(api.extractTranscript).mockResolvedValue(
      extractionWith({
        how: {
          value: "1. Compare the report to the invoices\n2. Sign off in the system\n3. Save the signed report",
          source_references: [],
        },
      })
    );
    const user = userEvent.setup();
    await progressToExtraction(user);
    const howCard = within(await screen.findByTestId("doc-how"));
    const items = howCard.getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "Compare the report to the invoices",
      "Sign off in the system",
      "Save the signed report",
    ]);
  });

  it("keeps a single numbered HOW step as plain text without its number", async () => {
    vi.mocked(api.extractTranscript).mockResolvedValue(
      extractionWith({ how: { value: "1. Save the signed report in the record", source_references: [] } })
    );
    const user = userEvent.setup();
    await progressToExtraction(user);
    const howCard = within(await screen.findByTestId("doc-how"));
    expect(howCard.queryAllByRole("listitem")).toHaveLength(0);
    expect(howCard.getByText("Save the signed report in the record")).toBeInTheDocument();
  });

  it("keeps a single-sentence HOW value as plain text, not a one-item list", async () => {
    vi.mocked(api.extractTranscript).mockResolvedValue(
      extractionWith({ how: { value: "The engineer deploys the fix.", source_references: [] } })
    );
    const user = userEvent.setup();
    await progressToExtraction(user);
    const howCard = within(await screen.findByTestId("doc-how"));
    expect(howCard.queryByRole("list")).not.toBeInTheDocument();
    expect(howCard.getByText("The engineer deploys the fix.")).toBeInTheDocument();
  });
});

describe("Phase headings", () => {
  it("renders 'Documentation Extraction' above Structured Control Documentation, not 'Design Assessment'", async () => {
    // Regression test: this heading previously (incorrectly) said "Design
    // Assessment" above what is actually documentation extraction output -
    // now that a real design-assessment agent exists with its own section,
    // reusing that label here would recreate that exact confusion.
    const user = userEvent.setup();
    await progressToExtraction(user);
    const heading = await screen.findByRole("heading", { name: "Documentation Extraction" });
    const docSection = screen.getByText("Structured Control Documentation").closest("section");
    expect(heading.compareDocumentPosition(docSection!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Any heading named "Design Assessment" (the real agent's section/phase
    // heading, further down the page) must come AFTER the documentation
    // section, never before/above it.
    const designAssessmentHeadings = screen.getAllByRole("heading", { name: /design assessment/i });
    for (const designHeading of designAssessmentHeadings) {
      expect(docSection!.compareDocumentPosition(designHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("renders a 'Design Assessment' heading above the real Design Assessment section", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    await approveDocumentation(user);
    await user.click(screen.getByRole("button", { name: "Assess Control Design" }));
    const heading = await screen.findByRole("heading", { name: "Design Assessment" });
    const section = (await screen.findByText("Rating:")).closest("section");
    expect(heading.compareDocumentPosition(section!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("Screen 6: draft control description", () => {
  it("labels the draft as requiring human review", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    expect(await screen.findByText(/Draft - requires human review/i)).toBeInTheDocument();
  });

  it("preserves blank lines between attributes so each renders as its own paragraph", async () => {
    const user = userEvent.setup();
    vi.mocked(api.extractTranscript).mockResolvedValue(
      extractionWith({ control_description: "What: Manager submits a request.\n\nWho: IT Security reviews it." }),
    );
    await progressToExtraction(user);
    const description = await screen.findByText((_, element) => element?.tagName === "P" && element.textContent === "What: Manager submits a request.\n\nWho: IT Security reviews it.");
    expect(description).toHaveClass("whitespace-pre-wrap");
  });
});

describe("Screen 7: human review", () => {
  it("captures an Approve decision", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));
    expect(api.validateReview).toHaveBeenCalledWith("approved", "jsmith", "");
    expect(await screen.findByText(/Review recorded: approved/)).toBeInTheDocument();
  });

  it("relabels the submit button to 'Review Decision Submitted' and disables it after a successful submit", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));

    const submittedButton = await screen.findByRole("button", { name: "Review Decision Submitted" });
    expect(submittedButton).toBeDisabled();

    // Picking a different decision affordance should bring back a fresh submit button.
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("button", { name: "Submit Review Decision" })).toBeEnabled();
  });

  it("surfaces the backend's reject-requires-a-reason rule instead of reimplementing it", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);
    vi.mocked(api.validateReview).mockRejectedValueOnce(
      new ApiError("reviewer_comments: Value error, reviewer_comments is required when decision is 'rejected'")
    );
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reviewer_comments is required");
  });

  it("keeps reviewer-edited content distinguishable from the AI-generated draft", async () => {
    vi.mocked(api.validateReview).mockResolvedValue({
      decision: "approved_with_edits",
      reviewer_id: "jsmith",
      human_approval_required: true,
    });
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const editBox = screen.getByLabelText("Edited control description (final)");
    expect(editBox).toHaveValue("What: Manager submits a request. Who: IT Security reviews it.");
    await user.clear(editBox);
    await user.type(editBox, "Reviewer-rewritten final description.");
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));

    const history = await screen.findByText("Review history / Audit details");
    const panel = history.closest("details") as HTMLElement;
    expect(within(panel).getByText("What: Manager submits a request. Who: IT Security reviews it.")).toBeInTheDocument();
    expect(within(panel).getByText("Reviewer-rewritten final description.")).toBeInTheDocument();
  });
});

describe("Screen 10: excel export", () => {
  it("does not offer an export until a review decision has been submitted", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    expect(screen.queryByRole("button", { name: "Download RACM Excel" })).not.toBeInTheDocument();
  });

  it("offers an export after an Approve decision and sends the final documentation and review", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));

    const exportButton = await screen.findByRole("button", { name: "Download RACM Excel" });
    await user.click(exportButton);

    expect(api.exportExcel).toHaveBeenCalledWith(
      expect.objectContaining({
        control: expect.objectContaining({
          control_id: "PILOT-A-UAM-001",
          documentation: expect.objectContaining({ control_description: extractionWith().documentation.control_description }),
          review: { decision: "approved", reviewer_id: "jsmith", human_approval_required: true },
        }),
      })
    );
  });

  it("carries the computed design assessment into the export payload when it was run", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));

    await user.click(await screen.findByRole("button", { name: "Download RACM Excel" }));

    expect(api.exportExcel).toHaveBeenCalledWith(
      expect.objectContaining({
        control: expect.objectContaining({
          design_assessment: expect.objectContaining({ first_pass_design_conclusion: "pass" }),
        }),
      })
    );
  });

  it("carries the computed gap assessment into the export payload when gaps were drafted", async () => {
    vi.mocked(api.draftGaps).mockResolvedValue({
      gaps: [
        {
          gap_id: "PILOT-A-UAM-001-GAP-01",
          gap_type: "design_gap",
          gap_title: "Lack of independence between control roles",
          gap_description: "Same individual performs both roles.",
          root_cause_category: "Segregation of duties",
          impact: "unknown",
          recommendation: "Assign review to someone outside the provisioning process.",
          proposed_action: null,
          action_addresses_gap: "not_assessed",
          source_references: [],
        },
      ],
      missing_information: [],
    });
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await screen.findByText("Lack of independence between control roles");
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));

    await user.click(await screen.findByRole("button", { name: "Download RACM Excel" }));

    expect(api.exportExcel).toHaveBeenCalledWith(
      expect.objectContaining({
        control: expect.objectContaining({
          gap_assessment: expect.objectContaining({
            gaps: expect.arrayContaining([expect.objectContaining({ gap_title: "Lack of independence between control roles" })]),
          }),
        }),
      })
    );
  });

  it("sends the reviewer-edited description, not the AI draft, after Approve with Edits", async () => {
    vi.mocked(api.validateReview).mockResolvedValue({
      decision: "approved_with_edits",
      reviewer_id: "jsmith",
      human_approval_required: true,
    });
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const editBox = screen.getByLabelText("Edited control description (final)");
    await user.clear(editBox);
    await user.type(editBox, "Reviewer-rewritten final description.");
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));

    const exportButton = await screen.findByRole("button", { name: "Download RACM Excel" });
    await user.click(exportButton);

    expect(api.exportExcel).toHaveBeenCalledWith(
      expect.objectContaining({
        control: expect.objectContaining({
          documentation: expect.objectContaining({ control_description: "Reviewer-rewritten final description." }),
        }),
      })
    );
  });

  it("does not offer an export after a Reject decision", async () => {
    vi.mocked(api.validateReview).mockResolvedValue({
      decision: "rejected",
      reviewer_id: "jsmith",
      reviewer_comments: "Needs more evidence.",
      human_approval_required: true,
    });
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await user.type(screen.getByLabelText("Reason for rejection (required)"), "Needs more evidence.");
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));

    await screen.findByText(/Review recorded: rejected/);
    expect(screen.queryByRole("button", { name: "Download RACM Excel" })).not.toBeInTheDocument();
  });

  it("shows an error banner when export fails", async () => {
    vi.mocked(api.exportExcel).mockRejectedValueOnce(
      new ApiError("control.review.decision: Excel export requires an approved human review decision.")
    );
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));
    await user.click(await screen.findByRole("button", { name: "Download RACM Excel" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Excel export requires an approved human review decision.");
  });
});

describe("Screen 7: design assessment", () => {
  it("invokes assessDesign with the documentation folded into the control, and renders the rating", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    await approveDocumentation(user);
    await user.click(screen.getByRole("button", { name: "Assess Control Design" }));

    expect(api.assessDesign).toHaveBeenCalledWith(
      expect.objectContaining({ control_id: "PILOT-A-UAM-001", documentation: extractionWith().documentation })
    );
    expect(await screen.findByText("Documentation is complete and no issues were detected.")).toBeInTheDocument();
    // Overall rating + 3 dimension badges all legitimately say "Adequate" here.
    expect(screen.getAllByText("Adequate").length).toBeGreaterThan(0);
  });

  it("shows an error state when design assessment fails", async () => {
    vi.mocked(api.assessDesign).mockRejectedValueOnce(new ApiError("control: Field required"));
    const user = userEvent.setup();
    await progressToExtraction(user);
    await approveDocumentation(user);
    await user.click(screen.getByRole("button", { name: "Assess Control Design" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Field required");
  });
});

describe("Screen 8: gap drafting", () => {
  it("drafts a gap only after an Inadequate rating and renders Title/Observation/Risk/Root Cause/Recommendation", async () => {
    vi.mocked(api.assessDesign).mockResolvedValue({
      design_assessment: {
        completeness: { result: "pass", rationale: "x", source_references: [] },
        relevance: { result: "pass", rationale: "x", source_references: [] },
        risk_objective_control_alignment: {
          result: "fail",
          rationale: "Same individual performs both roles.",
          source_references: [],
        },
        first_pass_design_conclusion: "fail",
        conclusion_rationale: "Independence issue detected.",
        rfi_items: [],
        testing_procedures: [],
      },
      rating_label: "Inadequate",
    });
    vi.mocked(api.draftGaps).mockResolvedValue({
      gaps: [
        {
          gap_id: "PILOT-A-UAM-001-GAP-01",
          gap_type: "design_gap",
          gap_title: "Lack of independence between control roles",
          gap_description: "Same individual performs both roles.",
          root_cause_category: "Segregation of duties",
          impact: "unknown",
          recommendation: "Assign an independent reviewer.",
          proposed_action: null,
          action_addresses_gap: "not_assessed",
          source_references: [],
        },
      ],
      missing_information: [],
    });

    const user = userEvent.setup();
    await progressToExtraction(user);
    await assessAndApproveDesign(user);
    await screen.findByText("Independence issue detected.");
    await user.click(screen.getByRole("button", { name: "Draft Gaps" }));

    expect(await screen.findByText("Lack of independence between control roles")).toBeInTheDocument();
    // The gap's Observation reuses the same rationale text already shown in
    // the Design Assessment section's alignment card above - appears twice
    // by design (gap_description IS that dimension's rationale).
    expect(screen.getAllByText(/Same individual performs both roles\./).length).toBe(2);
    expect(screen.getByText("Segregation of duties")).toBeInTheDocument();
    expect(screen.getByText("Assign an independent reviewer.")).toBeInTheDocument();
  });

  it("lets the reviewer fill in Action Owner and Action Date on the gap card, and exports them", async () => {
    vi.mocked(api.assessDesign).mockResolvedValue({
      design_assessment: {
        completeness: { result: "pass", rationale: "x", source_references: [] },
        relevance: { result: "pass", rationale: "x", source_references: [] },
        risk_objective_control_alignment: {
          result: "fail",
          rationale: "Same individual performs both roles.",
          source_references: [],
        },
        first_pass_design_conclusion: "fail",
        conclusion_rationale: "Independence issue detected.",
        rfi_items: [],
        testing_procedures: [],
      },
      rating_label: "Inadequate",
    });
    vi.mocked(api.draftGaps).mockResolvedValue({
      gaps: [
        {
          gap_id: "PILOT-A-UAM-001-GAP-01",
          gap_type: "design_gap",
          gap_title: "Lack of independence between control roles",
          gap_description: "Same individual performs both roles.",
          root_cause_category: "Segregation of duties",
          impact: "unknown",
          recommendation: "Assign an independent reviewer.",
          proposed_action: null,
          action_addresses_gap: "not_assessed",
          source_references: [],
        },
      ],
      missing_information: [],
    });

    const user = userEvent.setup();
    await progressToExtraction(user);
    await assessAndApproveDesign(user);
    await screen.findByText("Independence issue detected.");
    await user.click(screen.getByRole("button", { name: "Draft Gaps" }));
    await screen.findByText("Lack of independence between control roles");

    await user.type(screen.getByLabelText("Action Owner"), "J. Smith");
    await user.type(screen.getByLabelText("Action Date"), "2026-03-15");
    await approveStep(user, "Gaps");

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));
    await user.click(await screen.findByRole("button", { name: "Download RACM Excel" }));

    expect(api.exportExcel).toHaveBeenCalledWith(
      expect.objectContaining({
        control: expect.objectContaining({
          gap_assessment: expect.objectContaining({
            gaps: [expect.objectContaining({ action_owner: "J. Smith", action_date: "2026-03-15" })],
          }),
        }),
      })
    );
  });

  it("lets the reviewer edit the gap draft via the Edit button next to Action Owner/Date, and exports the edits", async () => {
    vi.mocked(api.assessDesign).mockResolvedValue({
      design_assessment: {
        completeness: { result: "pass", rationale: "x", source_references: [] },
        relevance: { result: "pass", rationale: "x", source_references: [] },
        risk_objective_control_alignment: {
          result: "fail",
          rationale: "Same individual performs both roles.",
          source_references: [],
        },
        first_pass_design_conclusion: "fail",
        conclusion_rationale: "Independence issue detected.",
        rfi_items: [],
        testing_procedures: [],
      },
      rating_label: "Inadequate",
    });
    vi.mocked(api.draftGaps).mockResolvedValue({
      gaps: [
        {
          gap_id: "PILOT-A-UAM-001-GAP-01",
          gap_type: "design_gap",
          gap_title: "Lack of independence between control roles",
          gap_description: "Same individual performs both roles.",
          root_cause_category: "Segregation of duties",
          impact: "unknown",
          recommendation: "Assign an independent reviewer.",
          proposed_action: null,
          action_addresses_gap: "not_assessed",
          source_references: [],
        },
      ],
      missing_information: [],
    });

    const user = userEvent.setup();
    await progressToExtraction(user);
    await assessAndApproveDesign(user);
    await screen.findByText("Independence issue detected.");
    await user.click(screen.getByRole("button", { name: "Draft Gaps" }));
    await screen.findByText("Lack of independence between control roles");

    // "Edit" also labels Section 9's Approve/Edit/Reject button - the gap
    // card's own Edit button is the first one in document order.
    await user.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    const titleBox = screen.getByLabelText("Gap title");
    await user.clear(titleBox);
    await user.type(titleBox, "Reviewer-revised gap title");
    const recommendationBox = screen.getByLabelText("Recommendation");
    await user.clear(recommendationBox);
    await user.type(recommendationBox, "Reviewer-revised recommendation.");
    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(screen.getByText("Reviewer-revised gap title")).toBeInTheDocument();
    expect(screen.getByText("Reviewer-revised recommendation.")).toBeInTheDocument();
    await approveStep(user, "Gaps");

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));
    await user.click(await screen.findByRole("button", { name: "Download RACM Excel" }));

    expect(api.exportExcel).toHaveBeenCalledWith(
      expect.objectContaining({
        control: expect.objectContaining({
          gap_assessment: expect.objectContaining({
            gaps: [
              expect.objectContaining({
                gap_title: "Reviewer-revised gap title",
                recommendation: "Reviewer-revised recommendation.",
              }),
            ],
          }),
        }),
      })
    );
  });

  it("reports no gap drafted when design assessment did not conclude Inadequate", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    await assessAndApproveDesign(user);
    await user.click(screen.getByRole("button", { name: "Draft Gaps" }));
    expect(await screen.findByText(/No gap drafted/)).toBeInTheDocument();
  });
});

describe("Control-level guardrail", () => {
  it("keeps the active control_id visible and consistent through the whole flow", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    expect(screen.getByText(/Active control: PILOT-A-UAM-001/)).toBeInTheDocument();
    // extractTranscript must have been called with the SAME record that was loaded.
    expect(api.extractTranscript).toHaveBeenCalledWith(RECORD, QUESTIONS, expect.any(String));
  });
});

describe("Button labels reflect a completed action", () => {
  it("relabels Validate & Load, Generate Walkthrough Questions, Upload transcript, and Process Transcript once each succeeds", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Reviewer ID"), "jsmith");
    await user.upload(screen.getByLabelText("Upload RACM file"), racmFile());
    expect(await screen.findByRole("button", { name: "Validated & Loaded" })).toBeInTheDocument();
    await approveStep(user, "RACM Input");

    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    expect(await screen.findByRole("button", { name: "Questions Generated" })).toBeInTheDocument();
    await approveStep(user, "Questions");

    await uploadTranscript(user);
    expect(screen.getByText("Transcript Uploaded")).toBeInTheDocument();
    await approveStep(user, "Transcript");

    await user.click(screen.getByRole("button", { name: "Process Transcript" }));
    expect(await screen.findByRole("button", { name: "Transcript Processed" })).toBeInTheDocument();

    // Typing over the uploaded transcript undoes the "uploaded" label.
    await user.type(screen.getByLabelText("Transcript text"), "x");
    expect(screen.getByText("Upload transcript")).toBeInTheDocument();
  });

  it("relabels Assess Control Design and Draft Gaps once each succeeds", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    await approveDocumentation(user);
    await user.click(screen.getByRole("button", { name: "Assess Control Design" }));
    expect(await screen.findByRole("button", { name: "Control Design Assessed" })).toBeInTheDocument();
    await approveStep(user, "Design Assessment");

    await user.click(screen.getByRole("button", { name: "Draft Gaps" }));
    expect(await screen.findByRole("button", { name: "Gaps Drafted" })).toBeInTheDocument();
  });

  it("relabels Approve/Edit/Reject to their past-tense form once selected", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);

    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(screen.getByRole("button", { name: "Approved" })).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Edit" })[0]); // Section 9's Edit (no gap card when no gap is drafted)
    expect(screen.getByRole("button", { name: "Editing" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("button", { name: "Rejected" })).toBeInTheDocument();
  });

  it("relabels Download RACM Excel once the export succeeds, without disabling it", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Submit Review Decision" }));
    await user.click(await screen.findByRole("button", { name: "Download RACM Excel" }));

    const downloadedButton = await screen.findByRole("button", { name: "RACM Excel Downloaded" });
    expect(downloadedButton).toBeEnabled();
  });
});

describe("Human review at every step from step 2", () => {
  it("keeps question generation locked until the loaded RACM is approved", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    expect(screen.getByRole("button", { name: "Generate Walkthrough Questions" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Approve RACM Input" })).toBeEnabled();

    await approveStep(user, "RACM Input");
    expect(screen.getByRole("button", { name: "Generate Walkthrough Questions" })).toBeEnabled();
  });

  it("asks for a fresh RACM approval when a different control is loaded", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");

    await user.upload(screen.getByLabelText("Upload RACM file"), racmFile());
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve RACM Input" })).toBeEnabled());
    expect(screen.getByRole("button", { name: "Generate Walkthrough Questions" })).toBeDisabled();
  });

  it("keeps each step locked until the previous one is approved", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);

    // Step 3 stays locked until the questions are approved.
    expect(screen.getByLabelText("Upload transcript file")).toBeDisabled();
    expect(screen.getByLabelText("Transcript text")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Process Transcript" })).toBeDisabled();
    await approveStep(user, "Questions");
    expect(screen.getByLabelText("Upload transcript file")).toBeEnabled();
    expect(screen.getByLabelText("Transcript text")).toBeEnabled();

    // The transcript has to be approved before it can be processed.
    await uploadTranscript(user);
    expect(screen.getByRole("button", { name: "Process Transcript" })).toBeDisabled();
    await approveStep(user, "Transcript");
    expect(screen.getByRole("button", { name: "Process Transcript" })).toBeEnabled();
  });

  it("walks the documentation steps in order and unlocks Assess Control Design only after the last one", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    expect(screen.getByRole("button", { name: "Approve Draft Description" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Assess Control Design" })).toBeDisabled();

    await approveStep(user, "Documentation");
    expect(screen.getByRole("button", { name: "Approve Draft Description" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Assess Control Design" })).toBeDisabled();
    await approveStep(user, "Draft Description");
    expect(screen.getByRole("button", { name: "Assess Control Design" })).toBeEnabled();
  });

  it("keeps the final review locked until the gaps step is approved", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    await assessAndApproveDesign(user);
    await user.click(screen.getByRole("button", { name: "Draft Gaps" }));
    await screen.findByRole("button", { name: "Gaps Drafted" });
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();

    await approveStep(user, "Gaps");
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  });

  it("requests changes with a comment, withdrawing the approval and relocking later steps", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    await approveStep(user, "Documentation");
    await approveStep(user, "Draft Description");
    expect(screen.getByRole("button", { name: "Assess Control Design" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Request changes to Documentation" }));
    await user.type(screen.getByLabelText("Comment for Documentation"), "WHO looks wrong.");
    await user.click(screen.getByRole("button", { name: "Send change request for Documentation" }));

    expect(api.validateReview).toHaveBeenCalledWith("needs_revision", "jsmith", "WHO looks wrong.");
    expect(await screen.findByText(/Changes requested by jsmith: WHO looks wrong\./)).toBeInTheDocument();
    // Documentation is no longer approved, so everything after it locks again.
    expect(screen.getByRole("button", { name: "Approve Documentation" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Approve Draft Description" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Assess Control Design" })).toBeDisabled();
  });

  it("surfaces the backend's review rules for a step instead of reimplementing them", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    vi.mocked(api.validateReview).mockRejectedValueOnce(
      new ApiError("reviewer_comments: Value error, reviewer_comments is required when decision is 'needs_revision'")
    );
    await user.click(screen.getByRole("button", { name: "Request changes to Documentation" }));
    await user.click(screen.getByRole("button", { name: "Send change request for Documentation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reviewer_comments is required");
  });

  it("lets the reviewer edit an extracted attribute, which is what later steps and the export use", async () => {
    const user = userEvent.setup();
    await progressToExtraction(user);
    await approveStep(user, "Documentation");

    await user.click(screen.getByRole("button", { name: "Edit Who" }));
    const whoBox = screen.getByLabelText("Who value");
    await user.clear(whoBox);
    await user.type(whoBox, "The Finance Manager reviews it.");
    await user.click(screen.getByRole("button", { name: "Finish editing Who" }));

    // Editing withdraws the approval until it is re-approved.
    expect(screen.getByRole("button", { name: "Approve Documentation" })).toBeEnabled();
    expect(screen.getByText("The Finance Manager reviews it.")).toBeInTheDocument();

    await approveDocumentation(user);
    await user.click(screen.getByRole("button", { name: "Assess Control Design" }));
    await waitFor(() => expect(api.assessDesign).toHaveBeenCalled());
    expect(api.assessDesign).toHaveBeenCalledWith(
      expect.objectContaining({
        documentation: expect.objectContaining({ who: expect.objectContaining({ value: "The Finance Manager reviews it." }) }),
      })
    );
  });

  it("lets the reviewer edit a generated question, which is what transcript extraction receives", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);

    await user.click(screen.getByRole("button", { name: "Edit question PILOT-A-UAM-001-Q02" }));
    const box = screen.getByLabelText("Question text PILOT-A-UAM-001-Q02");
    await user.clear(box);
    await user.type(box, "Who carries out this control each time?");
    await user.click(screen.getByRole("button", { name: "Finish editing question PILOT-A-UAM-001-Q02" }));

    await approveStep(user, "Questions");
    await uploadTranscript(user);
    await approveStep(user, "Transcript");
    await user.click(screen.getByRole("button", { name: "Process Transcript" }));
    await waitFor(() => expect(api.extractTranscript).toHaveBeenCalled());

    const calls = vi.mocked(api.extractTranscript).mock.calls;
    const sent = calls[calls.length - 1][1];
    expect(sent.questions.find((q) => q.question_id === "PILOT-A-UAM-001-Q02")?.question_text).toBe(
      "Who carries out this control each time?"
    );
  });

  it("re-running an earlier step clears the approvals that depended on it", async () => {
    const user = userEvent.setup();
    await progressToHumanReview(user);
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Control Design Assessed" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve Design Assessment" })).toBeEnabled());
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
  });
});

describe("Uploading your own files", () => {
  async function renderReady(user: ReturnType<typeof userEvent.setup>) {
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Upload RACM file")).toBeInTheDocument());
    await user.type(screen.getByLabelText("Reviewer ID"), "jsmith");
  }

  it("loads a RACM uploaded from the browser through the same validation as a pasted one", async () => {
    vi.mocked(api.validateRecord).mockResolvedValue(RECORD);
    const user = userEvent.setup();
    await renderReady(user);

    await user.upload(screen.getByLabelText("Upload RACM file"), racmFile());

    await waitFor(() => expect(screen.getByText(/Active control: PILOT-A-UAM-001/)).toBeInTheDocument());
    expect(api.validateRecord).toHaveBeenCalledWith(RECORD);
    expect(screen.getByText("Loaded from my-racm.json")).toBeInTheDocument();
    // It still needs the human approval before the next step unlocks.
    expect(screen.getByRole("button", { name: "Generate Walkthrough Questions" })).toBeDisabled();
    await approveStep(user, "RACM Input");
    expect(screen.getByRole("button", { name: "Generate Walkthrough Questions" })).toBeEnabled();
  });

  it("reports a RACM file that is not valid JSON", async () => {
    vi.mocked(api.validateRecord).mockClear();
    const user = userEvent.setup();
    await renderReady(user);

    await user.upload(
      screen.getByLabelText("Upload RACM file"),
      new File(["{ not json"], "broken.json", { type: "application/json" })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid JSON");
    expect(api.validateRecord).not.toHaveBeenCalled();
  });

  it("surfaces the backend's validation errors for an uploaded RACM", async () => {
    vi.mocked(api.validateRecord).mockRejectedValueOnce(new ApiError("control.risk: Field required"));
    const user = userEvent.setup();
    await renderReady(user);

    await user.upload(screen.getByLabelText("Upload RACM file"), racmFile());

    expect(await screen.findByRole("alert")).toHaveTextContent("control.risk: Field required");
  });

  it("keeps transcript upload locked until the questions are approved", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    expect(screen.getByLabelText("Upload transcript file")).toBeDisabled();
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);
    expect(screen.getByLabelText("Upload transcript file")).toBeDisabled();
    await approveStep(user, "Questions");
    expect(screen.getByLabelText("Upload transcript file")).toBeEnabled();
  });

  it("fills the transcript from an uploaded text file, which then needs approval before processing", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);
    await approveStep(user, "Questions");

    const text = "[L01] Interviewer: Who performs it?\n[L02] Interviewee: The Finance Manager.";
    await user.upload(
      screen.getByLabelText("Upload transcript file"),
      new File([text], "walkthrough.txt", { type: "text/plain" })
    );

    expect(await screen.findByText("Transcript Uploaded")).toBeInTheDocument();
    expect(screen.getByText("Uploaded: walkthrough.txt")).toBeInTheDocument();
    expect(screen.getByLabelText("Transcript text")).toHaveValue(text);
    expect(screen.getByRole("button", { name: "Process Transcript" })).toBeDisabled();
    await approveStep(user, "Transcript");
    await user.click(screen.getByRole("button", { name: "Process Transcript" }));
    await waitFor(() => expect(api.extractTranscript).toHaveBeenCalled());
    const calls = vi.mocked(api.extractTranscript).mock.calls;
    expect(calls[calls.length - 1][2]).toBe(text);

    // Typing over the uploaded text drops the "uploaded" label.
    await user.type(screen.getByLabelText("Transcript text"), "x");
    expect(screen.queryByText("Uploaded: walkthrough.txt")).not.toBeInTheDocument();
  });

  it("rejects an empty transcript file", async () => {
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);
    await approveStep(user, "Questions");

    await user.upload(
      screen.getByLabelText("Upload transcript file"),
      new File(["   \n"], "empty.txt", { type: "text/plain" })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("empty.txt is empty.");
    expect(screen.getByLabelText("Transcript text")).toHaveValue("");
  });
});

describe("Excel RACM and Word transcript uploads", () => {
  const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

  async function renderReady(user: ReturnType<typeof userEvent.setup>) {
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Upload RACM file")).toBeInTheDocument());
    await user.type(screen.getByLabelText("Reviewer ID"), "jsmith");
  }

  it("sends an uploaded Excel RACM to the backend converter and loads the control it returns", async () => {
    vi.mocked(api.convertExcelToRacm).mockResolvedValue(RECORD);
    const user = userEvent.setup();
    await renderReady(user);

    const file = new File(["xlsx-bytes"], "my-racm.xlsx", { type: XLSX });
    await user.upload(screen.getByLabelText("Upload RACM file"), file);

    await waitFor(() => expect(screen.getByText(/Active control: PILOT-A-UAM-001/)).toBeInTheDocument());
    expect(api.convertExcelToRacm).toHaveBeenCalledWith(file);
    expect(screen.getByText("Loaded from my-racm.xlsx")).toBeInTheDocument();
    // The converted record is shown in the JSON box for review, and still needs approval.
    expect(screen.getByPlaceholderText("Paste a RACMControlRecord JSON object")).toHaveValue(JSON.stringify(RECORD, null, 2));
    expect(screen.getByRole("button", { name: "Generate Walkthrough Questions" })).toBeDisabled();
    await approveStep(user, "RACM Input");
    expect(screen.getByRole("button", { name: "Generate Walkthrough Questions" })).toBeEnabled();
  });

  it("shows the backend's message when the Excel file cannot be used", async () => {
    vi.mocked(api.convertExcelToRacm).mockRejectedValueOnce(new ApiError("Cannot detect header row - no row names both a risk column"));
    const user = userEvent.setup();
    await renderReady(user);

    await user.upload(screen.getByLabelText("Upload RACM file"), new File(["x"], "bad.xlsx", { type: XLSX }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot detect header row");
    expect(screen.queryByText(/Active control:/)).not.toBeInTheDocument();
  });

  it("reads a Word transcript through the backend and puts its text in the transcript box", async () => {
    vi.mocked(api.extractDocumentText).mockResolvedValue("[L01] Interviewer: Who?\n[L02] Interviewee: IT Security.");
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);
    await approveStep(user, "Questions");

    const file = new File(["docx-bytes"], "walkthrough.docx", { type: DOCX });
    await user.upload(screen.getByLabelText("Upload transcript file"), file);

    expect(await screen.findByText("Uploaded: walkthrough.docx")).toBeInTheDocument();
    expect(api.extractDocumentText).toHaveBeenCalledWith(file);
    expect(screen.getByLabelText("Transcript text")).toHaveValue("[L01] Interviewer: Who?\n[L02] Interviewee: IT Security.");
    await approveStep(user, "Transcript");
    expect(screen.getByRole("button", { name: "Process Transcript" })).toBeEnabled();
  });

  it("shows the backend's message when the Word file cannot be read", async () => {
    vi.mocked(api.extractDocumentText).mockRejectedValueOnce(new ApiError("Could not read the .docx file - is it a valid Word document?"));
    const user = userEvent.setup();
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);
    await approveStep(user, "Questions");

    await user.upload(screen.getByLabelText("Upload transcript file"), new File(["x"], "broken.docx", { type: DOCX }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not read the .docx file");
    expect(screen.getByLabelText("Transcript text")).toHaveValue("");
  });

  it("does not send a plain .txt transcript to the backend, and rejects other file types", async () => {
    vi.mocked(api.extractDocumentText).mockClear();
    const user = userEvent.setup({ applyAccept: false });
    await loadControl(user);
    await approveStep(user, "RACM Input");
    await user.click(screen.getByRole("button", { name: "Generate Walkthrough Questions" }));
    await screen.findByText(/Please walk me through how/);
    await approveStep(user, "Questions");

    await user.upload(screen.getByLabelText("Upload transcript file"), new File(["[L01] Interviewer: Hi."], "t.txt", { type: "text/plain" }));
    await screen.findByText("Uploaded: t.txt");
    expect(api.extractDocumentText).not.toHaveBeenCalled();

    await user.upload(screen.getByLabelText("Upload transcript file"), new File(["%PDF"], "t.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("t.pdf is not supported");
  });
});
