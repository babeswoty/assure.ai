"""Excel export of the RACM master record.

Three column-group blocks: the original RACM input (orange - Engagement
Details / Risk Details / Control Details), the structured control
documentation drafted from the walkthrough (light green, opening with
Applicable/Reason if Not Applicable), and the gap block (olive - Gap/Gap
title/Reason/RCA/Action Plan drawn from the Gap Drafting Agent's output,
plus Action Owner/Action Date left as blank placeholders for a human
reviewer to fill in). The review audit trail is left out until asked for.

Applicable/Reason if Not Applicable are derived from the Design Assessment
Agent's own rating (Control.design_assessment), not a separate RACM-input
field: Adequate -> Applicable "Yes" (reason column echoes "Yes"), Inadequate
-> Applicable "No" (reason column carries the design assessment's own
conclusion_rationale, falling back to "N/A" if that's somehow blank, plus
the relevance dimension's own rationale appended when it has one - giving
the fuller picture rather than citing only the alignment failure). Any
other rating (not yet assessed, or "Requires Human Review") is not a
confirmed yes/no, so both columns stay blank rather than guessing.

Gap/Gap title/RCA/Action Plan read off Control.gap_assessment.gaps -
gap_description/gap_title/root_cause_category/recommendation respectively,
with "N/A" when no gap was drafted. A control stays on one row regardless
of how many gaps it has: with exactly one gap the cell holds that value
as-is; with several, each column becomes a numbered list ("1. ...", "2.
...") within the same cell rather than splitting into one row per gap.
Reason joins the control's own objective with that same (possibly
numbered) gap_description text - already-existing, verbatim fields, never
invented text. Action Owner/Action Date come from Gap.action_owner/
action_date - fields only a human reviewer fills in (on the Gap Drafting
card in the UI), never produced by any agent. With exactly one gap the
real value passes straight through (Action Date keeps its true Excel date
type, so the native calendar picker still works); blank means "not filled
in yet", not "N/A". With several gaps, both become a numbered list in the
one cell, same as the other gap columns - Action Date necessarily as text
at that point, since one cell can't hold more than one real date.

Row layout: row 1 is a group-label row (merged across each contiguous run
of columns sharing a group), row 2 is the field-name header, row 3 is the
single control's data.

Export is gated on the control's own human-review decision
(Control.review.decision) rather than re-implemented here - a control
without an approved/approved_with_edits decision is not exportable, since
everything above that gate is still a draft (see ControlReview docstring).
"""
from io import BytesIO
from typing import Callable, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.workbook import Workbook as WorkbookType
from openpyxl.worksheet.datavalidation import DataValidation

from app.design_assessment.assessor import rating_label
from app.schemas.racm import Gap, RACMControlRecord, ReviewDecision

RACM_INPUT_FILL = PatternFill(start_color="FFA500", end_color="FFA500", fill_type="solid")
DOCUMENTATION_FILL = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
GAP_FILL = PatternFill(start_color="C6E0B4", end_color="C6E0B4", fill_type="solid")

_ACTION_DATE_NUMBER_FORMAT = "yyyy-mm-dd"
_ACTION_DATE_VALIDATION_ROWS = 200

_GROUP_FONT = Font(color="1F4E78")
_HEADER_FONT = Font(bold=True)
_WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical="top")

_GROUP_ROW, _HEADER_ROW, _DATA_ROW = 1, 2, 3

_APPROVED_DECISIONS = (ReviewDecision.APPROVED, ReviewDecision.APPROVED_WITH_EDITS)

_ColumnSpec = Tuple[str, Callable[[RACMControlRecord], object], str]


def _applicable_value(record: RACMControlRecord) -> Optional[str]:
    label = rating_label(record.control.design_assessment.first_pass_design_conclusion)
    if label == "Adequate":
        return "Yes"
    if label == "Inadequate":
        return "No"
    return None


def _not_applicable_reason_value(record: RACMControlRecord) -> Optional[str]:
    design = record.control.design_assessment
    label = rating_label(design.first_pass_design_conclusion)
    if label == "Adequate":
        return "Yes"
    if label == "Inadequate":
        parts = [design.conclusion_rationale or "N/A"]
        if design.relevance.rationale:
            parts.append(f"Relevance: {design.relevance.rationale}")
        return "\n\n".join(parts)
    return None


RACM_INPUT_FIELDS: List[_ColumnSpec] = [
    ("Engagement ID", lambda r: r.engagement.engagement_id, "Engagement Details"),
    ("Client", lambda r: r.engagement.client, "Engagement Details"),
    ("OpCo", lambda r: r.engagement.opco, "Engagement Details"),
    ("Area", lambda r: r.engagement.area, "Engagement Details"),
    ("Mega Process", lambda r: r.engagement.mega_process, "Engagement Details"),
    ("Process", lambda r: r.engagement.process, "Engagement Details"),
    ("Sub-process", lambda r: r.engagement.subprocess, "Engagement Details"),
    ("Control ID", lambda r: r.control.control_id, "Control Details"),
    ("Control Reference", lambda r: r.control.control_reference, "Control Details"),
    ("Control Title", lambda r: r.control.control_title, "Control Details"),
    ("Risk ID", lambda r: r.control.risk.risk_id, "Risk Details"),
    ("Risk Description", lambda r: r.control.risk.risk_description, "Risk Details"),
    ("Control Objective", lambda r: r.control.control_objective, "Control Details"),
    ("Suggested Control Description", lambda r: r.control.suggested_control_description, "Control Details"),
    ("Control Frequency", lambda r: r.control.control_frequency, "Control Details"),
    ("Control Nature", lambda r: r.control.control_nature, "Control Details"),
    ("Control Type", lambda r: r.control.control_type, "Control Details"),
    ("Expected Evidence", lambda r: r.control.expected_evidence, "Control Details"),
    ("Suggested Test Procedures (ToD)", lambda r: r.control.suggested_test_procedures_tod, "Control Details"),
    ("Suggested Test Procedures (ToE)", lambda r: r.control.suggested_test_procedures_toe, "Control Details"),
]

DOCUMENTATION_FIELDS: List[_ColumnSpec] = [
    ("Applicable", _applicable_value, "Structured Control Documentation"),
    ("Reason if Not Applicable", _not_applicable_reason_value, "Structured Control Documentation"),
    ("What", lambda r: r.control.documentation.what.value, "Structured Control Documentation"),
    ("Who", lambda r: r.control.documentation.who.value, "Structured Control Documentation"),
    ("When", lambda r: r.control.documentation.when.value, "Structured Control Documentation"),
    ("Why", lambda r: r.control.documentation.why.value, "Structured Control Documentation"),
    ("Where", lambda r: r.control.documentation.where.value, "Structured Control Documentation"),
    ("How", lambda r: r.control.documentation.how.value, "Structured Control Documentation"),
]


def _numbered(gaps: List[Gap], getter: Callable[[Gap], Optional[str]]) -> str:
    """Renders one gap's field as-is; renders several gaps as a numbered
    list in the same cell (1. ..., 2. ..., blank line between), rather than
    splitting into one row per gap - keeps the export at one row per
    control regardless of how many gaps it has."""
    if not gaps:
        return "N/A"
    if len(gaps) == 1:
        return getter(gaps[0]) or "N/A"
    return "\n\n".join(f"{i}. {getter(gap) or 'N/A'}" for i, gap in enumerate(gaps, start=1))


def _gap_value(record: RACMControlRecord) -> str:
    return _numbered(record.control.gap_assessment.gaps, lambda g: g.gap_description)


def _gap_title_value(record: RACMControlRecord) -> str:
    return _numbered(record.control.gap_assessment.gaps, lambda g: g.gap_title)


def _gap_reason_value(record: RACMControlRecord) -> str:
    gaps = record.control.gap_assessment.gaps
    if not gaps:
        return "N/A"
    objective = record.control.control_objective
    descriptions = _numbered(gaps, lambda g: g.gap_description)
    return f"{objective}\n\n{descriptions}" if objective else descriptions


def _gap_rca_value(record: RACMControlRecord) -> str:
    return _numbered(record.control.gap_assessment.gaps, lambda g: g.root_cause_category)


def _gap_action_plan_value(record: RACMControlRecord) -> str:
    return _numbered(record.control.gap_assessment.gaps, lambda g: g.recommendation)


def _gap_action_owner_value(record: RACMControlRecord) -> Optional[str]:
    """Unlike the other gap columns, a blank result here means 'not filled
    in yet', not 'N/A' - these are reviewer-entered, so a blank cell is an
    invitation to fill it in directly in Excel, never a conclusion."""
    gaps = record.control.gap_assessment.gaps
    if not gaps:
        return None
    if len(gaps) == 1:
        return gaps[0].action_owner
    return "\n\n".join(f"{i}. {gap.action_owner or ''}" for i, gap in enumerate(gaps, start=1))


def _gap_action_date_value(record: RACMControlRecord):
    """Single gap: the real date object (or None), so the cell keeps a true
    Excel date type and the calendar picker/validation works. Several gaps
    can't share one date-typed cell, so that case falls back to a numbered
    text list of ISO dates instead."""
    gaps = record.control.gap_assessment.gaps
    if not gaps:
        return None
    if len(gaps) == 1:
        return gaps[0].action_date
    return "\n\n".join(
        f"{i}. {gap.action_date.isoformat() if gap.action_date else ''}" for i, gap in enumerate(gaps, start=1)
    )


GAP_FIELDS: List[_ColumnSpec] = [
    ("Gap", _gap_value, "Gap"),
    ("Gap title", _gap_title_value, "Gap"),
    ("Reason", _gap_reason_value, "Gap"),
    ("RCA", _gap_rca_value, "Gap"),
    ("Action Plan", _gap_action_plan_value, "Gap"),
    ("Action Owner", _gap_action_owner_value, "Gap"),
    ("Action Date", _gap_action_date_value, "Gap"),
]


def is_approved_for_export(record: RACMControlRecord) -> bool:
    return record.control.review.decision in _APPROVED_DECISIONS


def build_racm_workbook(record: RACMControlRecord) -> WorkbookType:
    columns: List[Tuple[str, Callable[[RACMControlRecord], object], str, PatternFill]] = (
        [(label, getter, group, RACM_INPUT_FILL) for label, getter, group in RACM_INPUT_FIELDS]
        + [(label, getter, group, DOCUMENTATION_FILL) for label, getter, group in DOCUMENTATION_FIELDS]
        + [(label, getter, group, GAP_FILL) for label, getter, group in GAP_FIELDS]
    )
    total_columns = len(columns)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "RACM"

    # Row 1: group label, merged across each contiguous run sharing a group.
    i = 0
    while i < total_columns:
        group = columns[i][2]
        j = i
        while j + 1 < total_columns and columns[j + 1][2] == group:
            j += 1
        start_col, end_col = i + 1, j + 1
        cell = sheet.cell(row=_GROUP_ROW, column=start_col, value=group)
        cell.font = _GROUP_FONT
        cell.alignment = _WRAP_ALIGNMENT
        if end_col > start_col:
            sheet.merge_cells(start_row=_GROUP_ROW, start_column=start_col, end_row=_GROUP_ROW, end_column=end_col)
        i = j + 1

    for col_index, (label, _getter, _group, fill) in enumerate(columns, start=1):
        sheet.cell(row=_GROUP_ROW, column=col_index).fill = fill
        header_cell = sheet.cell(row=_HEADER_ROW, column=col_index, value=label)
        header_cell.font = _HEADER_FONT
        header_cell.fill = fill
        header_cell.alignment = _WRAP_ALIGNMENT

    for col_index, (_label, getter, _group, fill) in enumerate(columns, start=1):
        data_cell = sheet.cell(row=_DATA_ROW, column=col_index, value=getter(record))
        data_cell.fill = fill
        data_cell.alignment = _WRAP_ALIGNMENT

    for col_index in range(1, total_columns + 1):
        sheet.column_dimensions[sheet.cell(row=_HEADER_ROW, column=col_index).column_letter].width = 30

    _apply_action_date_formatting(sheet, columns)

    sheet.freeze_panes = f"A{_DATA_ROW}"
    return workbook


def _apply_action_date_formatting(sheet, columns) -> None:
    """Gives Action Date an Excel date number format plus a date data
    validation, so Excel shows its native calendar date-picker when a
    reviewer clicks the cell - applied a little past the current single
    data row too, so it still works if rows are added by hand later."""
    action_date_col = next(i for i, (label, *_rest) in enumerate(columns, start=1) if label == "Action Date")
    last_row = _DATA_ROW + _ACTION_DATE_VALIDATION_ROWS
    col_letter = sheet.cell(row=_HEADER_ROW, column=action_date_col).column_letter

    for row in range(_DATA_ROW, last_row + 1):
        sheet.cell(row=row, column=action_date_col).number_format = _ACTION_DATE_NUMBER_FORMAT

    validation = DataValidation(type="date", operator="greaterThanOrEqual", formula1="1", allow_blank=True)
    validation.error = "Enter a valid date."
    validation.errorTitle = "Invalid date"
    sheet.add_data_validation(validation)
    validation.add(f"{col_letter}{_DATA_ROW}:{col_letter}{last_row}")


def build_racm_excel_bytes(record: RACMControlRecord) -> bytes:
    buffer = BytesIO()
    build_racm_workbook(record).save(buffer)
    return buffer.getvalue()
