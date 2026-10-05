"""Robust Excel RACM importer with intelligent header detection and column mapping."""

import hashlib
import html
import re
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None


class ExcelParsingError(Exception):
    """Base exception for Excel parsing issues."""
    pass


class ExcelValidationError(ExcelParsingError):
    """Exception for data validation issues with structured error details."""
    def __init__(self, errors: List[Dict[str, Any]]):
        self.errors = errors
        super().__init__(f"Excel validation failed with {len(errors)} error(s)")


# Header aliases - maps variations to canonical field names
HEADER_ALIASES = {
    "ref": "Ref",
    "#ref": "Ref",
    "mega process": "Mega Process",
    "major process": "Major Process Name",
    "major process name": "Major Process Name",
    "process name": "Process Name",
    "sub-process": "Sub-process",
    "subprocess": "Sub-process",
    "risk ref": "Risk Ref",
    "risk ref (#)": "Risk Ref",
    "risk refence": "Risk Ref",
    "risk description": "Risk Description",
    "control objective": "Control Objective",
    "control ref": "Control Ref",
    "control ref (#)": "Control Ref",
    "control reference": "Control Ref",
    "aml/ctf control": "AML/CTF Control",
    "suggested control": "Suggested Control",
    "control nature": "Control Nature",
    "control type": "Control Type",
    "control type (manual/automated/semi automated)": "Control Type",
    "frequency of control": "Frequency of Control",
    "frequency": "Frequency of Control",
    "control evidence": "Control Evidence",
    "expected evidence": "Control Evidence",
    "test procedures tod": "Test Procedures TOD",
    "test procedures toe": "Test Procedures TOE",
    "owner": "Owner",
    "group fintech/fintech opco": "Owner",
}

# Column to RACM field mapping
COLUMN_MAPPING = {
    "Ref": ("_ref", str),
    "Mega Process": ("engagement.mega_process", str),
    "Major Process Name": ("engagement.area", str),
    "Process Name": ("engagement.process", str),
    "Sub-process": ("engagement.subprocess", str),
    "Risk Ref": ("control.risk.risk_id", str),
    "Risk Description": ("control.risk.risk_description", str),
    "Control Objective": ("control.control_objective", str),
    "Control Ref": ("control.control_id", str),
    "Control Reference": ("control.control_reference", str),
    "AML/CTF Control": ("control.control_title", str),
    "Suggested Control": ("control.suggested_control_description", str),
    "Control Nature": ("control.control_nature", str),
    "Control Type": ("control.control_type", str),
    "Frequency of Control": ("control.control_frequency", str),
    "Control Evidence": ("control.expected_evidence", str),
    "Test Procedures TOD": ("control.suggested_test_procedures_tod", str),
    "Test Procedures TOE": ("control.suggested_test_procedures_toe", str),
}


def _normalize_header(text: str) -> str:
    """Normalize Excel header for matching:
    - Trim whitespace
    - Replace line breaks with spaces
    - Collapse repeated spaces
    - Decode HTML entities
    - Lowercase for comparison
    """
    if not text:
        return ""

    # Decode HTML entities (e.g., &amp; -> &)
    text = html.unescape(str(text))

    # Replace line breaks with spaces
    text = re.sub(r'[\r\n]+', ' ', text)

    # Collapse repeated spaces
    text = re.sub(r'\s+', ' ', text)

    # Trim and lowercase
    return text.strip().lower()


def _find_header_row(ws) -> Optional[int]:
    """Scan first 10 rows to find the true header row.

    The header row contains both a risk reference column and a control reference column.
    """
    # Canonical normalized names to look for
    risk_ref_normalized = _normalize_header("Risk Ref")
    control_ref_normalized = _normalize_header("Control Ref")

    for row_idx in range(1, min(11, ws.max_row + 1)):
        has_risk_ref = False
        has_control_ref = False
        is_blank = True

        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value is None:
                continue

            is_blank = False
            normalized = _normalize_header(str(cell.value))

            # Check if this is a risk ref or control ref column
            if "risk" in normalized and "ref" in normalized:
                has_risk_ref = True
            if "control" in normalized and ("ref" in normalized or "reference" in normalized):
                has_control_ref = True

        # Found the header row if it has both columns and is not blank
        if not is_blank and has_risk_ref and has_control_ref:
            return row_idx

    return None


def _build_header_map(ws, header_row: int) -> Dict[str, int]:
    """Build mapping from canonical header names to column indices."""
    header_map = {}

    for col_idx in range(1, ws.max_column + 1):
        cell = ws.cell(row=header_row, column=col_idx)
        if cell.value is None:
            continue

        normalized = _normalize_header(str(cell.value))

        # Try to find matching canonical header
        for canonical, aliases in HEADER_ALIASES.items():
            if normalized == canonical:
                header_map[aliases] = col_idx
                break

    return header_map


def _get_cell_value(ws, row: int, col_idx: Optional[int], preserve_newlines: bool = False) -> Optional[str]:
    """Extract cell value, handling None, NaN, and whitespace."""
    if col_idx is None:
        return None

    cell = ws.cell(row=row, column=col_idx)
    value = cell.value

    if value is None:
        return None

    # Convert to string
    value_str = str(value).strip()

    # Reject string literals for None values
    if value_str.lower() in ("nan", "none", "undefined", ""):
        return None

    # For multiline cells, optionally preserve line breaks
    if not preserve_newlines:
        value_str = re.sub(r'\s+', ' ', value_str)

    return value_str if value_str else None


def extract_racm_from_excel(file_bytes: bytes) -> Dict[str, Any]:
    """Extract RACM control data from Excel file.

    Returns dict matching RACMControlRecord schema.
    Raises ExcelParsingError or ExcelValidationError on issues.
    """
    if not openpyxl:
        raise ExcelParsingError("openpyxl not installed")

    try:
        # Load workbook
        file_obj = BytesIO(file_bytes)
        wb = openpyxl.load_workbook(file_obj, data_only=True)
    except Exception as e:
        raise ExcelParsingError(f"Failed to load workbook: {str(e)}")

    # Find RACM Upload worksheet or use first visible sheet
    ws = None
    worksheet_name = None

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        if not sheet.sheet_state == 'hidden':
            if sheet_name.lower() == "racm upload":
                ws = sheet
                worksheet_name = sheet_name
                break

    # Fall back to first visible worksheet
    if ws is None:
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            if not sheet.sheet_state == 'hidden':
                ws = sheet
                worksheet_name = sheet_name
                break

    if ws is None:
        raise ExcelParsingError("No usable worksheet found")

    if ws.max_row < 2:
        raise ExcelParsingError("Worksheet is empty")

    # Find header row
    header_row = _find_header_row(ws)
    if header_row is None:
        raise ExcelParsingError("Cannot detect header row - no row contains both Risk Ref and Control Ref")

    # Build header map
    header_map = _build_header_map(ws, header_row)

    # Validate required headers
    required_headers = ["Risk Ref", "Control Ref"]
    missing = [h for h in required_headers if h not in header_map]
    if missing:
        raise ExcelParsingError(f"Missing required columns: {', '.join(missing)}")

    # Process data rows (starting after header row)
    errors: List[Dict[str, Any]] = []
    extracted_controls = []

    for row_idx in range(header_row + 1, ws.max_row + 1):
        # Skip blank rows
        is_blank = True
        for col_idx in range(1, ws.max_column + 1):
            if ws.cell(row=row_idx, column=col_idx).value is not None:
                is_blank = False
                break

        if is_blank:
            continue

        row_errors = []

        # Extract values
        control_id = _get_cell_value(ws, row_idx, header_map.get("Control Ref"))
        risk_id = _get_cell_value(ws, row_idx, header_map.get("Risk Ref"))

        # Validate required fields
        if not control_id:
            row_errors.append({
                "field": "control.control_id",
                "message": "Control Ref is required"
            })

        if not risk_id:
            row_errors.append({
                "field": "control.risk.risk_id",
                "message": "Risk Ref is required"
            })

        if row_errors:
            for error in row_errors:
                errors.append({
                    "sheet": worksheet_name,
                    "row": row_idx,
                    **error
                })
            continue

        # Extract all fields
        mega_process = _get_cell_value(ws, row_idx, header_map.get("Mega Process"))
        area = _get_cell_value(ws, row_idx, header_map.get("Major Process Name"))
        process = _get_cell_value(ws, row_idx, header_map.get("Process Name"))
        subprocess = _get_cell_value(ws, row_idx, header_map.get("Sub-process"))
        risk_description = _get_cell_value(ws, row_idx, header_map.get("Risk Description"))
        control_objective = _get_cell_value(ws, row_idx, header_map.get("Control Objective"), preserve_newlines=True)
        control_ref = _get_cell_value(ws, row_idx, header_map.get("Control Reference"))
        control_title = _get_cell_value(ws, row_idx, header_map.get("AML/CTF Control"))
        suggested_control = _get_cell_value(ws, row_idx, header_map.get("Suggested Control"), preserve_newlines=True)
        control_nature = _get_cell_value(ws, row_idx, header_map.get("Control Nature"))
        control_type = _get_cell_value(ws, row_idx, header_map.get("Control Type"))
        frequency = _get_cell_value(ws, row_idx, header_map.get("Frequency of Control"))
        evidence = _get_cell_value(ws, row_idx, header_map.get("Control Evidence"), preserve_newlines=True)
        test_tod = _get_cell_value(ws, row_idx, header_map.get("Test Procedures TOD"), preserve_newlines=True)
        test_toe = _get_cell_value(ws, row_idx, header_map.get("Test Procedures TOE"), preserve_newlines=True)

        # Generate engagement_id deterministically
        engagement_id = f"{worksheet_name}_{row_idx}".replace(" ", "_")

        # Build RACM record
        racm_record = {
            "schema_version": "1.0",
            "engagement": {
                "engagement_id": engagement_id,
                "client": "MTN Fintech",
                "opco": "Group Fintech / Fintech OpCo",
                "area": area,
                "mega_process": mega_process,
                "process": process or "Unknown Process",
                "subprocess": subprocess,
            },
            "control": {
                "control_id": control_id,
                "control_title": control_title or control_id,
                "control_reference": control_ref,
                "risk": {
                    "risk_id": risk_id,
                    "risk_description": risk_description or risk_id,
                },
                "control_objective": control_objective,
                "suggested_control_description": suggested_control,
                "control_frequency": frequency,
                "control_nature": control_nature,
                "control_type": control_type,
                "expected_evidence": evidence,
                "suggested_test_procedures_tod": test_tod,
                "suggested_test_procedures_toe": test_toe,
            },
        }

        extracted_controls.append(racm_record)

    # Report errors if any
    if errors:
        raise ExcelValidationError(errors)

    if not extracted_controls:
        raise ExcelParsingError("No valid data rows found in worksheet")

    # Return first control (TODO: handle multiple rows per spec)
    return extracted_controls[0]
