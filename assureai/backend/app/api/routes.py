"""Thin HTTP wrapper around the existing AssureAI backend functions.

No business logic lives here - every endpoint validates/serializes with
the existing pydantic models and calls an existing function
(generate_walkthrough_questions, extract_control_documentation,
ControlReview's own validators, ...). There is no database: this test
harness is stateless server-side, matching the fact that no persistence
layer exists anywhere in AssureAI yet.
"""
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

try:
    from docx import Document
except ImportError:
    Document = None

from app.design_assessment.assessor import assess_control_design, rating_label
from app.excel_import import extract_racm_from_excel, ExcelValidationError, ExcelParsingError
from app.gap_drafting.drafter import draft_gaps
from app.pilot.validation import validate_manifest
from app.question_generation.generator import generate_walkthrough_questions
from app.question_generation.models import WalkthroughQuestionSet
from app.racm_export.exporter import build_racm_excel_bytes, is_approved_for_export
from app.schemas.racm import Control, ControlReview, DesignAssessment, RACMControlRecord
from app.transcript_extraction.extractor import extract_control_documentation
from app.transcript_extraction.models import ExtractionResult
from app.transcript_extraction.parser import parse_transcript_text
from app.validation import validate_record

router = APIRouter(prefix="/api")

PILOT_DIR = Path(__file__).resolve().parents[3] / "pilot"


def _validation_error_detail(exc: ValidationError) -> list[dict]:
    """Turns a pydantic ValidationError into a small, safe-to-display list -
    never a raw stack trace."""
    return [
        {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "AssureAI test API"}


@router.post("/convert-excel-to-racm")
async def convert_excel_to_racm(file: UploadFile = File(...)):
    """Convert Excel RACM format to JSON RACMControlRecord.

    Accepts .xlsx or .xls files and returns the equivalent JSON structure.

    Returns:
    - 200: Successfully parsed and validated
    - 400: File format error (unsupported type, empty, missing worksheet/headers)
    - 422: Validation error (missing required fields in data rows)
    - 500: Unexpected infrastructure error
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        # Check file extension
        if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            raise HTTPException(status_code=400, detail="File must be .xlsx or .xls format")

        # Read file bytes
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="File is empty")

        print(f"[DEBUG] Processing Excel file: {file.filename}, Size: {len(file_bytes)} bytes")

        # Convert Excel to RACM dict
        try:
            racm_dict = extract_racm_from_excel(file_bytes)
        except ExcelValidationError as e:
            # Structured validation errors - return 422 with error details
            print(f"[DEBUG] Validation errors: {e.errors}")
            raise HTTPException(status_code=422, detail={"errors": e.errors})
        except ExcelParsingError as e:
            # File format/parsing errors - return 400
            print(f"[DEBUG] Parsing error: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

        print(f"[DEBUG] Extracted RACM dict with control_id: {racm_dict.get('control', {}).get('control_id')}")

        # Validate the converted record using schema validation
        try:
            record = validate_record(racm_dict)
            print(f"[DEBUG] Validation passed")
        except ValidationError as e:
            # Schema validation errors - return 422 with structured error details
            error_details = _validation_error_detail(e)
            print(f"[DEBUG] Schema validation errors: {error_details}")
            raise HTTPException(status_code=422, detail=error_details)

        # Return as JSON
        return record.model_dump(mode="json")

    except HTTPException:
        raise
    except Exception as e:
        # Unexpected errors - return 500 only for infrastructure issues
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg) from e


@router.post("/extract-text-from-document")
async def extract_text_from_document(file: UploadFile = File(...)):
    """Extract text from .docx, .doc, or .txt files.

    Returns:
    - 200: Successfully extracted text
    - 400: Unsupported file type or empty file
    - 500: Unexpected error
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        # Read file bytes
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="File is empty")

        # Handle different file types
        if file.filename.endswith('.docx'):
            if not Document:
                raise HTTPException(status_code=500, detail="python-docx not installed")

            try:
                doc = Document(BytesIO(file_bytes))
                text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
                return {"text": text, "filename": file.filename}
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse .docx file: {str(e)}")

        elif file.filename.endswith('.doc'):
            # For .doc files, try to use python-docx (it supports some .doc files)
            if not Document:
                raise HTTPException(status_code=500, detail="python-docx not installed")
            try:
                doc = Document(BytesIO(file_bytes))
                text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
                return {"text": text, "filename": file.filename}
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse .doc file: {str(e)}")

        elif file.filename.endswith('.txt'):
            try:
                text = file_bytes.decode('utf-8')
                return {"text": text, "filename": file.filename}
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to decode .txt file: {str(e)}")

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.filename}")

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg) from e


# ---------- Screen 1: RACM input / pilot fixtures ----------


@router.get("/pilot/cases")
def list_pilot_cases():
    try:
        manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))
    except (FileNotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not load pilot manifest: {exc}") from exc
    return {
        "pilot_id": manifest.pilot_id,
        "cases": [
            {
                "case_id": c.case_id,
                "control_id": c.control_id,
                "scenario": c.scenario.value,
                "expected_behavior": c.expected_behavior,
            }
            for c in manifest.cases
        ],
    }


@router.get("/pilot/cases/{case_id}")
def get_pilot_case(case_id: str):
    manifest = validate_manifest(json.loads((PILOT_DIR / "manifest.json").read_text(encoding="utf-8")))
    case = next((c for c in manifest.cases if c.case_id == case_id), None)
    if case is None:
        raise HTTPException(status_code=404, detail=f"No pilot case {case_id!r}")

    racm_path = PILOT_DIR / case.racm_input_path
    transcript_path = PILOT_DIR / case.walkthrough_input_path
    try:
        record = validate_record(json.loads(racm_path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail=_validation_error_detail(exc)) from exc

    return {
        "case_id": case.case_id,
        "record": record.model_dump(mode="json"),
        "transcript_text": transcript_path.read_text(encoding="utf-8"),
    }


class ValidateRecordRequest(BaseModel):
    record: dict[str, Any]


@router.post("/records/validate")
def validate_record_endpoint(payload: ValidateRecordRequest):
    """Screen 1's "paste your own RACM JSON" path - reuses the exact same
    validate_record() the rest of the pipeline (and the pilot fixtures)
    are validated with. No second RACM schema."""
    try:
        record = validate_record(payload.record)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc
    return record.model_dump(mode="json")


# ---------- Screen 2: walkthrough questions ----------


class GenerateQuestionsRequest(BaseModel):
    record: dict[str, Any]


@router.post("/questions/generate")
def generate_questions_endpoint(payload: GenerateQuestionsRequest):
    try:
        record = validate_record(payload.record)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc

    result = generate_walkthrough_questions(record.control, engagement=record.engagement)
    return result.model_dump(mode="json")


# ---------- Screen 3/4/5/6: transcript -> structured documentation ----------


class ExtractRequest(BaseModel):
    record: dict[str, Any]
    questions: dict[str, Any]
    transcript_text: str
    transcript_id: str = "WT-TEST-UI-01"
    source_name: str = "Test UI transcript"


@router.post("/transcripts/extract")
def extract_transcript_endpoint(payload: ExtractRequest):
    if not payload.transcript_text.strip():
        raise HTTPException(status_code=422, detail=[{"field": "transcript_text", "message": "Transcript text is empty."}])

    try:
        record = validate_record(payload.record)
        questions = WalkthroughQuestionSet.model_validate(payload.questions)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc

    # Control-level guardrail: the transcript must belong to the SAME
    # control this session is scoped to, and the question set must be the
    # one generated for it - extract_control_documentation() itself raises
    # if control_ids disagree (see its own control_id equality check), so
    # this is enforced by existing logic, not re-implemented here.
    transcript = parse_transcript_text(
        payload.transcript_text,
        transcript_id=payload.transcript_id,
        control_id=record.control.control_id,
        source_name=payload.source_name,
    )

    try:
        result: ExtractionResult = extract_control_documentation(record.control, questions, transcript)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=[{"field": "control_id", "message": str(exc)}]) from exc

    return result.model_dump(mode="json")


# ---------- Design Assessment Agent (Prompt 3) ----------


class AssessDesignRequest(BaseModel):
    control: dict[str, Any]


@router.post("/design-assessment/assess")
def assess_design_endpoint(payload: AssessDesignRequest):
    """Thin wrapper over assess_control_design() - reads the control's
    ALREADY-EXTRACTED documentation (via Control.model_validate) and
    returns a DesignAssessment. No business logic here."""
    try:
        control = Control.model_validate(payload.control)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc

    design = assess_control_design(control)
    return {
        "design_assessment": design.model_dump(mode="json"),
        "rating_label": rating_label(design.first_pass_design_conclusion),
    }


# ---------- Gap Drafting Agent (Prompt 4) ----------


class DraftGapsRequest(BaseModel):
    control: dict[str, Any]
    design_assessment: dict[str, Any]


@router.post("/gaps/draft")
def draft_gaps_endpoint(payload: DraftGapsRequest):
    """Thin wrapper over draft_gaps() - only drafts a gap when the supplied
    design assessment already concluded Inadequate (FAIL); otherwise
    returns an empty gap list. No business logic here."""
    try:
        control = Control.model_validate(payload.control)
        design = DesignAssessment.model_validate(payload.design_assessment)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc

    gap_assessment = draft_gaps(control, design)
    return gap_assessment.model_dump(mode="json")


# ---------- Screen 7: human review ----------


class ReviewRequest(BaseModel):
    decision: str
    reviewer_id: Optional[str] = None
    reviewer_comments: Optional[str] = None


@router.post("/review/validate")
def validate_review_endpoint(payload: ReviewRequest):
    """Validates a reviewer's decision using ControlReview's OWN rules
    (reviewer_id/reviewed_at required for any real decision, comments
    required for a rejection/revision request) - these rules are not
    re-implemented in the frontend."""
    try:
        review = ControlReview(
            decision=payload.decision,
            reviewer_id=payload.reviewer_id,
            reviewer_comments=payload.reviewer_comments,
            reviewed_at=datetime.now(timezone.utc) if payload.decision != "not_reviewed" else None,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc
    return review.model_dump(mode="json")


# ---------- Screen 10: RACM Excel export ----------


class ExportExcelRequest(BaseModel):
    record: dict[str, Any]


@router.post("/export/excel")
def export_excel_endpoint(payload: ExportExcelRequest):
    """Exports the RACM input and structured control documentation to a
    two-column-group Excel workbook. Gated on the record's own review
    decision (via is_approved_for_export) - a control still in draft is
    not exportable, matching the human-review-is-the-only-gate rule."""
    try:
        record = validate_record(payload.record)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc

    if not is_approved_for_export(record):
        raise HTTPException(
            status_code=409,
            detail=[{
                "field": "control.review.decision",
                "message": "Excel export requires an approved (or approved-with-edits) human review decision.",
            }],
        )

    content = build_racm_excel_bytes(record)
    filename = f"{record.control.control_id}-RACM.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
