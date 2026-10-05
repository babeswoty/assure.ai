import axios, { AxiosError } from "axios";
import type {
  ApiErrorDetail,
  Control,
  ControlReview,
  DesignAssessment,
  ExtractionResult,
  GapAssessment,
  RacmRecord,
  WalkthroughQuestionSet,
} from "@/types";

const client = axios.create({ baseURL: "/api" });

export class ApiError extends Error {
  details: ApiErrorDetail[];
  constructor(message: string, details: ApiErrorDetail[] = []) {
    super(message);
    this.details = details;
  }
}

function unwrap(err: unknown): never {
  const axiosErr = err as AxiosError<{ detail?: ApiErrorDetail[] | string }>;
  const detail = axiosErr.response?.data?.detail;
  if (Array.isArray(detail)) {
    throw new ApiError(detail.map((d) => `${d.field ? d.field + ": " : ""}${d.message}`).join("; "), detail);
  }
  if (typeof detail === "string") {
    throw new ApiError(detail);
  }
  throw new ApiError(axiosErr.message || "Request failed");
}

// A failed blob-response request still comes back as a Blob (not JSON), so
// its error detail has to be read out of the blob body instead of
// axiosErr.response.data directly.
async function unwrapBlobError(err: unknown): Promise<never> {
  const axiosErr = err as AxiosError<Blob>;
  const data = axiosErr.response?.data;
  let detail: ApiErrorDetail[] | string | undefined;
  if (data instanceof Blob) {
    try {
      detail = JSON.parse(await data.text())?.detail;
    } catch {
      detail = undefined;
    }
  }
  if (Array.isArray(detail)) {
    throw new ApiError(detail.map((d) => `${d.field ? d.field + ": " : ""}${d.message}`).join("; "), detail);
  }
  if (typeof detail === "string") {
    throw new ApiError(detail);
  }
  throw new ApiError(axiosErr.message || "Request failed");
}

export async function validateRecord(record: unknown): Promise<RacmRecord> {
  try {
    const { data } = await client.post("/records/validate", { record });
    return data;
  } catch (err) {
    unwrap(err);
  }
}

export async function convertExcelToRacm(file: File): Promise<RacmRecord> {
  const form = new FormData();
  form.append("file", file);
  try {
    const { data } = await client.post("/convert-excel-to-racm", form);
    return data;
  } catch (err) {
    unwrap(err);
  }
}

export async function extractDocumentText(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  try {
    const { data } = await client.post("/extract-text-from-document", form);
    return data.text;
  } catch (err) {
    unwrap(err);
  }
}

export async function generateQuestions(record: RacmRecord): Promise<WalkthroughQuestionSet> {
  try {
    const { data } = await client.post("/questions/generate", { record });
    return data;
  } catch (err) {
    unwrap(err);
  }
}

export async function extractTranscript(
  record: RacmRecord,
  questions: WalkthroughQuestionSet,
  transcriptText: string,
  transcriptId = "WT-TEST-UI-01",
  sourceName = "Test UI transcript"
): Promise<ExtractionResult> {
  try {
    const { data } = await client.post("/transcripts/extract", {
      record,
      questions,
      transcript_text: transcriptText,
      transcript_id: transcriptId,
      source_name: sourceName,
    });
    return data;
  } catch (err) {
    unwrap(err);
  }
}

export async function validateReview(
  decision: string,
  reviewerId?: string,
  reviewerComments?: string
): Promise<ControlReview> {
  try {
    const { data } = await client.post("/review/validate", {
      decision,
      reviewer_id: reviewerId,
      reviewer_comments: reviewerComments,
    });
    return data;
  } catch (err) {
    unwrap(err);
  }
}

export async function assessDesign(
  control: Control
): Promise<{ design_assessment: DesignAssessment; rating_label: string }> {
  try {
    const { data } = await client.post("/design-assessment/assess", { control });
    return data;
  } catch (err) {
    unwrap(err);
  }
}

export async function draftGaps(control: Control, designAssessment: DesignAssessment): Promise<GapAssessment> {
  try {
    const { data } = await client.post("/gaps/draft", { control, design_assessment: designAssessment });
    return data;
  } catch (err) {
    unwrap(err);
  }
}

export async function exportExcel(record: RacmRecord): Promise<void> {
  const response = await client
    .post("/export/excel", { record }, { responseType: "blob" })
    .catch((err) => unwrapBlobError(err));
  const disposition: string = response.headers["content-disposition"] || "";
  const filename = disposition.match(/filename="?([^"]+)"?/)?.[1] ?? "RACM-export.xlsx";
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
