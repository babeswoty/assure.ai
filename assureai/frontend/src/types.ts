// TypeScript shapes mirroring the backend's existing pydantic models
// (assureai/backend/app/schemas, question_generation, transcript_extraction).
// These are types for rendering only - no validation logic is duplicated
// here; every payload is validated server-side before this UI ever
// displays it.

export interface SourceReference {
  source_id: string;
  source_type: string;
  source_name: string;
  locator?: string | null;
  excerpt?: string | null;
}

export interface Risk {
  risk_id: string;
  risk_description: string;
}

export interface Control {
  control_id: string;
  control_title: string;
  control_reference?: string | null;
  risk: Risk;
  control_objective?: string | null;
  suggested_control_description?: string | null;
  control_frequency?: string | null;
  control_nature?: string | null;
  control_type?: string | null;
  expected_evidence?: string | null;
  suggested_test_procedures_tod?: string | null;
  suggested_test_procedures_toe?: string | null;
  documentation: ControlDocumentation;
  design_assessment: DesignAssessment;
  gap_assessment: GapAssessment;
  review: ControlReview;
}

export interface Engagement {
  engagement_id: string;
  client: string;
  opco?: string | null;
  area?: string | null;
  mega_process?: string | null;
  process: string;
  subprocess?: string | null;
}

export interface RacmRecord {
  schema_version: string;
  engagement: Engagement;
  control: Control;
}

export interface WalkthroughQuestion {
  question_id: string;
  question_text: string;
  category?: string | null;
  purpose?: string | null;
  source_fields: string[];
  required: boolean;
  answer?: string | null;
  source_references: SourceReference[];
}

export interface WalkthroughQuestionSet {
  control_id: string;
  questions: WalkthroughQuestion[];
}

export interface DocumentedAttribute {
  value?: string | null;
  source_references: SourceReference[];
}

export interface MissingInformation {
  field: string;
  reason: string;
  follow_up_question?: string | null;
  status: string;
}

export interface ControlDocumentation {
  what: DocumentedAttribute;
  who: DocumentedAttribute;
  when: DocumentedAttribute;
  why: DocumentedAttribute;
  where: DocumentedAttribute;
  how: DocumentedAttribute;
  control_description?: string | null;
  missing_information: MissingInformation[];
  source_references: SourceReference[];
  metadata: { generated_by: string; generated_at?: string | null; model_or_author?: string | null };
}

export interface ExtractionResult {
  control_id: string;
  transcript_id: string;
  documentation: ControlDocumentation;
  questions: WalkthroughQuestionSet;
}

export interface AssessmentDimension {
  result: string;
  rationale?: string | null;
  source_references: SourceReference[];
}

export interface DesignAssessment {
  completeness: AssessmentDimension;
  relevance: AssessmentDimension;
  risk_objective_control_alignment: AssessmentDimension;
  first_pass_design_conclusion: string;
  conclusion_rationale?: string | null;
  rfi_items: unknown[];
  testing_procedures: unknown[];
}

export interface Gap {
  gap_id: string;
  gap_type: string;
  gap_title: string;
  gap_description: string;
  root_cause_category?: string | null;
  impact: string;
  recommendation?: string | null;
  proposed_action?: string | null;
  action_addresses_gap: string;
  action_owner?: string | null;
  action_date?: string | null;
  source_references: SourceReference[];
}

export interface GapAssessment {
  gaps: Gap[];
  missing_information: MissingInformation[];
}

export interface ControlReview {
  decision: string;
  reviewer_comments?: string | null;
  reviewer_id?: string | null;
  reviewed_at?: string | null;
  human_approval_required: boolean;
}

export interface StepReviewState {
  status: "approved" | "changes_requested";
  reviewer: string;
  comment?: string;
  reviewed_at?: string | null;
}

export interface ApiErrorDetail {
  field: string;
  message: string;
}
