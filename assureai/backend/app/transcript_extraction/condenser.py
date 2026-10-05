"""Condenses verbose extracted documentation into concise RACM-style keywords/phrases.

This module extracts business terminology from full sentences while preserving
source traceability. Source references and excerpts remain unchanged - only
the displayed value is condensed.

Examples:
  "The IT Security team reviews all access requests every month"
    → What: "User Access Review", Who: "IT Security", When: "Monthly"
  "We ensure that approved policies are maintained properly"
    → Why: "To ensure that approved policies are maintained"
"""

import re
from typing import Optional


# Common control verbs that signal the core activity
CONTROL_VERBS = {
    "review", "approve", "verify", "validate", "check", "reconcile",
    "audit", "monitor", "test", "document", "maintain", "update",
    "create", "provision", "grant", "assign", "disable", "revoke",
    "submit", "process", "authorize", "certify", "sign", "execute",
    "evaluate", "assess", "analyze", "confirm", "inspect", "perform",
    "prepare", "complete", "finalize", "archive", "retain", "secure",
}

# Common role/team keywords
ROLE_KEYWORDS = {
    "team", "manager", "director", "officer", "supervisor", "lead",
    "administrator", "analyst", "reviewer", "owner", "custodian",
    "department", "group", "committee", "board", "specialist",
}

# Frequency/timing keywords
TIMING_MAP = {
    r"\bdaily\b": "Daily",
    r"\bweekly\b": "Weekly",
    r"\bmonthly\b": "Monthly",
    r"\bquarterly\b": "Quarterly",
    r"\bsemi.?annual\b": "Semi-Annually",
    r"\bannually\b": "Annually",
    r"\byearly\b": "Annually",
    r"\bevery\s+month\b": "Monthly",
    r"\bevery\s+\d+\s+months?\b": "Periodically",
    r"\bevery\s+year\b": "Annually",
    r"\bevery\s+\d+\s+years?\b": "Periodically",
    r"\bupon\s+request\b": "Upon Request",
    r"\bon\s+demand\b": "On Demand",
    r"\bad\s+hoc\b": "Ad Hoc",
    r"\breal.?time\b": "Real-Time",
    r"\bcontinuous\b": "Continuous",
    r"\bmonth.?end\b": "Month-End",
    r"\byear.?end\b": "Year-End",
}


def _extract_noun_phrases(text: str, limit: int = 8) -> str:
    """Extract concise noun phrases from verbose text.

    Takes sentences like "The IT Security team reviews all access requests
    before approval" and extracts "User Access Review" or similar.
    """
    text = text.strip()
    if not text:
        return text

    # Remove common filler phrases
    text = re.sub(r"\bwe\s+(review|check|verify|ensure|validate)\s+", "", text, flags=re.I)
    text = re.sub(r"\b(the|a|an)\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(to\s+)?ensure\s+that\b.*", "", text, flags=re.I)
    text = re.sub(r"\s+before\s+.*", "", text, flags=re.I)
    text = re.sub(r"\s+(is|are|was|were)\s+.*", "", text, flags=re.I)

    # Clean up
    text = text.strip().strip(".,;:")
    words = text.split()

    # Truncate to word limit
    if len(words) > limit:
        words = words[:limit]

    result = " ".join(words).strip()

    # Capitalize first letter of each word (title case for business terms)
    return " ".join(w.capitalize() for w in result.split())


def _extract_role(text: str) -> str:
    """Extract role/team name from text.

    Finds patterns like "IT Security team", "Finance Manager", etc.
    """
    text = text.strip()
    if not text:
        return text

    # Remove common filler
    text = re.sub(r"\b(reviews?|approves?|checks?|verifies?|validates?)\b.*", "", text, flags=re.I)
    text = re.sub(r"\s+(all|every|the|a|an)\b", " ", text, flags=re.I)
    text = text.strip()

    # Extract role-related phrases (look for department + role pattern)
    match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:" + "|".join(ROLE_KEYWORDS) + r"))?)", text)
    if match:
        text = match.group(1)

    words = text.split()
    if len(words) > 8:
        words = words[:8]

    return " ".join(words).strip()


def _extract_timing(text: str) -> Optional[str]:
    """Extract timing/frequency from text."""
    text_lower = text.lower()

    for pattern, replacement in TIMING_MAP.items():
        if re.search(pattern, text_lower):
            return replacement

    return None


def _format_why(text: str) -> str:
    """Format Why field to start with 'To ensure that...'"""
    text = text.strip()
    if not text:
        return text

    # Remove surrounding filler
    text = re.sub(r"^to\s+ensure\s+that\s+", "", text, flags=re.I)
    text = re.sub(r"^the\s+control\s+", "", text, flags=re.I)
    text = re.sub(r"^to\s+", "", text, flags=re.I)
    text = text.strip()

    # Truncate to ~25 words (roughly 150 chars)
    words = text.split()
    if len(words) > 25:
        words = words[:25]
    text = " ".join(words).rstrip(".,;:")

    return f"To ensure that {text}."


def _extract_where(text: str) -> str:
    """Extract system/location from text.

    Looks for system names like SAP, Active Directory, ServiceNow, etc.
    """
    text = text.strip()

    # Common systems
    systems = [
        "SAP", "ServiceNow", "Active Directory", "AD", "SharePoint", "Excel",
        "Oracle", "Workday", "Salesforce", "Concur", "Ariba", "Coupa",
        "HR System", "ERP", "CRM", "HRIS", "ATS", "LMS", "Database",
    ]

    for sys in systems:
        if sys.lower() in text.lower():
            return sys

    # If no known system, extract key location/area terms
    text = re.sub(r"\b(in|on|at|within|through|via)\s+", "", text, flags=re.I)
    words = text.split()
    if len(words) > 10:
        words = words[:10]

    return " ".join(words).strip()


def _extract_how_steps(text: str) -> str:
    """Extract step-based process from text.

    Can keep detailed multi-step descriptions for How field.
    Max ~500 chars for reasonable display.
    """
    text = text.strip()
    if not text:
        return text

    # If already formatted as steps, keep it
    if re.search(r"^\d+\.\s+", text, re.MULTILINE):
        return text

    # Try to extract numbered/bulleted steps
    steps = re.findall(r"(?:step\s+\d+|[-•]|^\d+\.)\s*([^.!?]+[.!?]?)", text, re.IGNORECASE)
    if steps and len(steps) > 1:
        formatted_steps = []
        for i, step in enumerate(steps, 1):
            step = step.strip().rstrip(".,;:")
            if step:
                formatted_steps.append(f"{i}. {step}.")
        if formatted_steps:
            return "\n".join(formatted_steps)

    # Otherwise keep original but cap length
    if len(text) > 500:
        text = text[:500].rsplit(" ", 1)[0] + "..."

    return text


def condense_what(text: Optional[str]) -> Optional[str]:
    """Condense 'What' field to noun phrase (max 8 words)."""
    if not text:
        return text
    return _extract_noun_phrases(text, limit=8)


def condense_who(text: Optional[str]) -> Optional[str]:
    """Condense 'Who' field to role/team (max 8 words)."""
    if not text:
        return text
    return _extract_role(text)


def condense_when(text: Optional[str]) -> Optional[str]:
    """Condense 'When' field to timing indicator (max 10 words)."""
    if not text:
        return text

    timing = _extract_timing(text)
    if timing:
        return timing

    # Fallback: extract as phrase
    text = re.sub(r"\b(is|are|was|were)\s+", "", text, flags=re.I)
    text = text.strip().rstrip(".,;:")
    words = text.split()
    if len(words) > 10:
        words = words[:10]
    return " ".join(words).strip()


def condense_why(text: Optional[str]) -> Optional[str]:
    """Format 'Why' field as objective (max 25 words, one sentence)."""
    if not text:
        return text
    return _format_why(text)


def condense_where(text: Optional[str]) -> Optional[str]:
    """Condense 'Where' field to system/location (max 10 words)."""
    if not text:
        return text
    return _extract_where(text)


def condense_how(text: Optional[str]) -> Optional[str]:
    """Detailed 'How' field with steps allowed (no strict limit)."""
    if not text:
        return text
    return _extract_how_steps(text)
