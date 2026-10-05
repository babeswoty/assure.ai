"""Tests for the Excel RACM importer."""
from io import BytesIO

import openpyxl
import pytest

from app.excel_import import (
    STANDARD_HEADERS,
    ExcelParsingError,
    ExcelValidationError,
    extract_racm_from_excel,
)
from app.racm_export import build_racm_excel_bytes
from app.schemas.racm import Control, ControlReview, Engagement, RACMControlRecord, ReviewDecision, Risk
from app.validation import validate_record


def workbook_bytes(headers: list, rows: list, sheet_name: str = "RACM Upload", header_row: int = 1) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for col, name in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col, value=name)
    for offset, row in enumerate(rows, start=1):
        for col, value in enumerate(row, start=1):
            if value is not None:
                ws.cell(row=header_row + offset, column=col, value=value)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_standard_headers_are_the_ones_the_app_exports():
    assert STANDARD_HEADERS[0] == "Engagement ID"
    assert "Control ID" in STANDARD_HEADERS and "Risk ID" in STANDARD_HEADERS
    assert "Suggested Test Procedures (ToD)" in STANDARD_HEADERS


def test_imports_every_field_from_the_standard_headers():
    row = [
        "ENG-1", "Sample Client", "Sample OpCo", "Information Technology", "IT General Controls",
        "User Access Management", "Provisioning", "CTRL-001", "ITGC-UAM-01", "New User Access Approval",
        "RISK-001", "Unauthorized access could be provisioned.",
        "To ensure that new access is approved before provisioning.",
        "Manager approves; IT provisions.", "Per event", "Manual", "Preventive",
        "Approval ticket.", "Inspect the design.", "Inspect a sample of tickets.",
    ]
    result = extract_racm_from_excel(workbook_bytes(STANDARD_HEADERS, [row]))

    assert result["engagement"] == {
        "engagement_id": "ENG-1", "client": "Sample Client", "opco": "Sample OpCo",
        "area": "Information Technology", "mega_process": "IT General Controls",
        "process": "User Access Management", "subprocess": "Provisioning",
    }
    control = result["control"]
    assert control["control_id"] == "CTRL-001"
    assert control["control_reference"] == "ITGC-UAM-01"
    assert control["control_title"] == "New User Access Approval"
    assert control["risk"] == {"risk_id": "RISK-001", "risk_description": "Unauthorized access could be provisioned."}
    assert control["control_objective"].startswith("To ensure that")
    assert control["control_frequency"] == "Per event"
    assert control["suggested_test_procedures_tod"] == "Inspect the design."
    assert control["suggested_test_procedures_toe"] == "Inspect a sample of tickets."
    validate_record(result)  # and it is a valid RACM record


def test_older_header_names_are_still_accepted_as_aliases():
    headers = [
        "Risk Ref (#)", "Control Ref (#)", "Process Name", "Major Process Name", "Suggested Control",
        "Frequency of Control", "Control Evidence", "Test Procedures TOD", "Test Procedures TOE",
    ]
    row = ["R-1", "C-1", "Payments", "Finance", "Reviewed by manager", "Monthly", "Signed report", "TOD", "TOE"]
    result = extract_racm_from_excel(workbook_bytes(headers, [row]))

    assert result["control"]["risk"]["risk_id"] == "R-1"
    assert result["control"]["control_id"] == "C-1"
    assert result["engagement"]["process"] == "Payments"
    assert result["engagement"]["area"] == "Finance"
    assert result["control"]["suggested_control_description"] == "Reviewed by manager"
    assert result["control"]["control_frequency"] == "Monthly"
    assert result["control"]["expected_evidence"] == "Signed report"
    assert result["control"]["suggested_test_procedures_tod"] == "TOD"


def test_header_matching_ignores_case_spacing_line_breaks_and_html_entities():
    headers = ["  RISK   id ", "control\nid", "Process"]
    result = extract_racm_from_excel(workbook_bytes(headers, [["R-1", "C-1", "P"]]))
    assert result["control"]["risk"]["risk_id"] == "R-1"
    assert result["control"]["control_id"] == "C-1"


def test_a_single_control_column_is_used_as_both_the_id_and_the_reference():
    result = extract_racm_from_excel(workbook_bytes(["Risk ID", "Control Reference"], [["R-1", "ITGC-01"]]))
    assert result["control"]["control_id"] == "ITGC-01"
    assert result["control"]["control_reference"] == "ITGC-01"


def test_control_id_and_control_reference_stay_separate_when_both_are_given():
    result = extract_racm_from_excel(
        workbook_bytes(["Risk ID", "Control ID", "Control Reference"], [["R-1", "CTRL-9", "ITGC-01"]])
    )
    assert result["control"]["control_id"] == "CTRL-9"
    assert result["control"]["control_reference"] == "ITGC-01"


def test_multiline_cells_keep_their_line_breaks_only_where_that_is_useful():
    headers = ["Risk ID", "Control ID", "Control Title", "Suggested Control Description", "Expected Evidence"]
    row = ["R-1", "C-1", "Line one\nline two", "Step 1\nStep 2", "Point 1\nPoint 2"]
    result = extract_racm_from_excel(workbook_bytes(headers, [row]))
    assert "\n" in result["control"]["suggested_control_description"]
    assert "\n" in result["control"]["expected_evidence"]
    assert result["control"]["control_title"] == "Line one line two"


def test_blank_optional_fields_become_none():
    headers = ["Risk ID", "Control ID", "Control Objective", "Control Nature"]
    result = extract_racm_from_excel(workbook_bytes(headers, [["R-1", "C-1", None, "nan"]]))
    assert result["control"]["control_objective"] is None
    assert result["control"]["control_nature"] is None


def test_no_client_or_company_is_assumed_when_the_file_does_not_name_one():
    result = extract_racm_from_excel(workbook_bytes(["Risk ID", "Control ID"], [["R-1", "C-1"]]))
    assert result["engagement"]["client"] == "Not specified"
    assert result["engagement"]["opco"] is None
    assert result["engagement"]["process"] == "Unknown Process"
    assert "MTN" not in str(result)


def test_missing_control_identifier_is_reported_per_row():
    with pytest.raises(ExcelValidationError) as exc:
        extract_racm_from_excel(workbook_bytes(["Risk ID", "Control ID"], [["R-1", None]]))
    assert any(e["field"] == "control.control_id" and e["row"] == 2 for e in exc.value.errors)


def test_missing_risk_identifier_is_reported_per_row():
    with pytest.raises(ExcelValidationError) as exc:
        extract_racm_from_excel(workbook_bytes(["Risk ID", "Control ID"], [[None, "C-1"]]))
    assert any(e["field"] == "control.risk.risk_id" for e in exc.value.errors)


def test_file_without_the_identifier_headers_is_rejected_with_a_clear_message():
    with pytest.raises(ExcelParsingError, match="Cannot detect header row"):
        extract_racm_from_excel(workbook_bytes(["Foo", "Bar"], [["a", "b"]]))


def test_empty_workbook_fails():
    out = BytesIO()
    openpyxl.Workbook().save(out)
    with pytest.raises(ExcelParsingError):
        extract_racm_from_excel(out.getvalue())


def test_a_file_that_is_not_a_workbook_fails_cleanly():
    with pytest.raises(ExcelParsingError, match="Failed to load workbook"):
        extract_racm_from_excel(b"this is not an excel file")


def test_racm_upload_worksheet_is_preferred_over_other_sheets():
    wb = openpyxl.Workbook()
    wb.active.title = "Read Me"
    wb.active.cell(row=1, column=1, value="Risk ID")
    wb.active.cell(row=1, column=2, value="Control ID")
    wb.active.cell(row=2, column=1, value="WRONG-R")
    wb.active.cell(row=2, column=2, value="WRONG-C")
    sheet = wb.create_sheet("RACM Upload")
    for col, v in enumerate(["Risk ID", "Control ID"], start=1):
        sheet.cell(row=1, column=col, value=v)
    for col, v in enumerate(["R-1", "C-1"], start=1):
        sheet.cell(row=2, column=col, value=v)
    out = BytesIO()
    wb.save(out)
    assert extract_racm_from_excel(out.getvalue())["control"]["control_id"] == "C-1"


def test_header_row_is_found_below_title_rows():
    headers = ["Risk ID", "Control ID", "Process"]
    result = extract_racm_from_excel(workbook_bytes(headers, [["R-1", "C-1", "P"]], header_row=3))
    assert result["control"]["control_id"] == "C-1"


def test_a_workbook_exported_by_the_app_can_be_uploaded_again():
    control = Control(
        control_id="CTRL-RT-01",
        control_title="Quarterly access review",
        control_reference="ITGC-RT-01",
        risk=Risk(risk_id="RISK-RT-01", risk_description="Stale access remains."),
        control_objective="To ensure that access is reviewed quarterly.",
        suggested_control_description="Manager reviews the report.",
        control_frequency="Quarterly",
        control_nature="Manual",
        control_type="Detective",
        expected_evidence="Signed report.",
        review=ControlReview(
            decision=ReviewDecision.APPROVED, reviewer_id="j.smith", reviewed_at="2026-01-01T00:00:00Z"
        ),
    )
    record = RACMControlRecord(
        engagement=Engagement(
            engagement_id="ENG-RT", client="Sample Client", opco="Sample OpCo", area="IT",
            mega_process="ITGC", process="Access", subprocess="Review",
        ),
        control=control,
    )

    result = extract_racm_from_excel(build_racm_excel_bytes(record))

    assert result["engagement"] == record.engagement.model_dump(mode="json")
    for field in (
        "control_id", "control_title", "control_reference", "control_objective",
        "suggested_control_description", "control_frequency", "control_nature", "control_type", "expected_evidence",
    ):
        assert result["control"][field] == getattr(control, field), field
    assert result["control"]["risk"] == {"risk_id": "RISK-RT-01", "risk_description": "Stale access remains."}
