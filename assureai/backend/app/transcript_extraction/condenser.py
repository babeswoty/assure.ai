"""Turns a conversational answer into a short documentation phrase.

An interviewee answers in speech ("It's triggered every time HR notifies us of a
new starter, so it happens continuously..."); the structured control
documentation should read like a RACM entry instead:

    WHEN   Triggered each time HR notifies of a new starter
    WHO    AP Supervisor and Finance Manager
    WHY    To prevent unauthorised, duplicate or incorrect payments to suppliers
    WHERE  ServiceNow

Rules that keep this safe:
- Every word in a result comes from the answer itself (or is a fixed label such as
  "Weekly" for "every Thursday"). Nothing is invented.
- When a field cannot be condensed confidently, the original wording is kept (only
  filler such as "Sure." is removed). A longer answer is better than a wrong one.
- A result is never cut off mid-clause: whole trailing sentences or clauses are dropped,
  or nothing is.
- The verbatim evidence is untouched: the full conversational answer stays available
  through each attribute's source references ("View source").
"""

import re
from typing import List, Optional

# ----------------------------------------------------------------------------- shared

_FILLER_SENTENCE = re.compile(
    r"^(?:sure|okay|ok|yes|yeah|yep|right|well|so|um+|uh+|alright|of course|good question|absolutely)\W*$",
    re.IGNORECASE,
)
_LEADING_FILLER = re.compile(
    r"^(?:(?:so|well|okay|ok|yes|yeah|yep|um+|uh+|basically|actually|honestly|look|right)\b[,.\s-]*)+",
    re.IGNORECASE,
)
_NUMBERED = re.compile(r"^\s*\d+[.)]\s*")


def _sentences(text: str) -> List[str]:
    """Split into sentences, dropping pure filler ("Sure.", "Okay.") and leading
    filler words ("So, ...")."""
    out: List[str] = []
    for chunk in re.split(r"\n+|(?<=[.!?])\s+", text or ""):
        chunk = _NUMBERED.sub("", chunk).strip()
        if not chunk or _FILLER_SENTENCE.match(chunk):
            continue
        chunk = _LEADING_FILLER.sub("", chunk).strip()
        if chunk:
            out.append(chunk)
    return out


_CONTRACTIONS = [
    (r"\bnobody's still got\b", "nobody still has"),
    (r"\b(\w+)'ve\b", r"\1 have"),
    (r"\bit's\b", "it is"),
    (r"\bthat's\b", "that is"),
    (r"\bthere's\b", "there is"),
    (r"\bcan't\b", "cannot"),
    (r"\bwon't\b", "will not"),
    (r"\b(do|does|did|is|are|was|were|has|have|had|would|should|could)n't\b", r"\1 not"),
]


def _formalise(text: str) -> str:
    """Expand contractions so the phrase reads as documentation, not speech."""
    for pattern, repl in _CONTRACTIONS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def _tidy(sentence: str) -> str:
    sentence = _formalise(re.sub(r"\s+", " ", sentence)).strip().rstrip(".!?;, ")
    return (sentence[:1].upper() + sentence[1:]) if sentence else sentence


# Only a pronoun that starts a clause is dropped ("... and then we go into AD"); one inside a
# relative clause ("the groups we check") stays, or the sentence would stop making sense.
_SUBJECT_PRONOUN = re.compile(
    r"(?:^|(?<=, )|(?<=\b[Aa]nd )|(?<=\b[Tt]hen )|(?<=\b[Bb]ut )|(?<=\b[Ss]o )|(?<=\b[Ww]hen )|(?<=\b[Ii]f ))"
    r"(?:I|[Ww]e)\s+(?=(?:then\s+|also\s+|just\s+|usually\s+|always\s+|will\s+|can\s+)?[a-z]{2,}\b)"
)
_POSSESSIVE = re.compile(r"\b(?:my|our)\b", re.IGNORECASE)
_OBJECT_PRONOUN = re.compile(r"\s+(?:us|me)\b(?=\s+(?:a|an|the|of|to|with|that)\b)")


def _depersonalise(sentence: str) -> str:
    """"I go through the list and we sign off on our review" becomes "go through the list
    and sign off on the review": the procedure without the speaker. Only pronouns are
    dropped or swapped for "the"; every other word is the interviewee's."""
    sentence = _SUBJECT_PRONOUN.sub("", sentence)
    sentence = _POSSESSIVE.sub("the", sentence)
    return _OBJECT_PRONOUN.sub("", sentence)


def _clause_trim(sentence: str, limit: int) -> str:
    """Shorten a long sentence only at a clause boundary; never mid-clause."""
    if len(sentence) <= limit:
        return sentence
    best = -1
    for m in re.finditer(r",\s+|;\s+|\s+-\s+|\s+and then\s+|\s+which\s+", sentence):
        if m.start() <= limit:
            best = m.start()
    return sentence[:best].rstrip(",;- ") if best > 20 else sentence


def _first_sentences(text: Optional[str], max_sentences: int, limit: int, depersonalise: bool = False) -> Optional[str]:
    """Fallback: the first substantive sentence(s), with filler removed."""
    sentences = _sentences(text or "")
    if depersonalise:
        sentences = [_depersonalise(x) for x in sentences]
    if not sentences:
        return text
    kept: List[str] = []
    for s in sentences[:max_sentences]:
        if kept and len(" ".join(kept + [s])) > limit:
            break
        kept.append(s)
    kept = [_clause_trim(_tidy(s), limit) for s in kept]
    # after "; " a sentence starts lowercase, unless it opens with an acronym or name
    kept[1:] = [s[:1].lower() + s[1:] if s[1:2].islower() else s for s in kept[1:]]
    return "; ".join(kept)


# ----------------------------------------------------------------------------- WHEN

_DAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?"

# Most specific first. The label is a fixed keyword, not a quote from the answer.
_FREQUENCY_RULES = [
    (r"\b(?:twice|two times|2 times)\s+(?:a|per|every|each)\s+(?:year|annum)\b"
     r"|\bsemi[- ]?annual(?:ly)?\b|\bbi[- ]?annual(?:ly)?\b|\bhalf[- ]yearly\b"
     r"|\bevery\s+(?:six|6)\s+months\b", "Twice a year"),
    (r"\b(?:three times|thrice|3 times)\s+(?:a|per|every|each)\s+year\b"
     r"|\bevery\s+(?:four|4)\s+months\b", "Three times a year"),
    (r"\bonce\s+(?:a|per|every|each)\s+year\b|\bonce\s+annually\b|\bannual(?:ly)?\b|\byearly\b"
     r"|\bevery\s+year\b|\beach\s+year\b|\bper\s+year\b|\byear[- ]end\b", "Yearly"),
    (r"\bquarterly\b|\b(?:every|each|per|once\s+a)\s+quarter\b|\bquarter[- ]end\b", "Quarterly"),
    (r"\bfortnight(?:ly)?\b|\bbi[- ]?weekly\b|\bevery\s+(?:two|2)\s+weeks\b|\bevery\s+other\s+week\b", "Fortnightly"),
    (r"\bmonthly\b|\b(?:every|each|per|once\s+a)\s+month\b|\bmonth[- ]end\b|\bend\s+of\s+(?:the|each|every)\s+month\b", "Monthly"),
    (r"\bweekly\b|\b(?:every|each|per|once\s+a)\s+week\b|\b(?:every|each|on)\s+" + _DAYS, "Weekly"),
    (r"\bdaily\b|\b(?:every|each|per|once\s+a)\s+(?:business\s+|working\s+)?day\b|\bevery\s+(?:morning|evening)\b"
     r"|\bend\s+of\s+(?:the|each|every)\s+day\b", "Daily"),
]

# "every time ...", "whenever ...", "triggered when ..." are triggers, not frequencies.
_TRIGGER = re.compile(
    r"\b(?P<lead>triggered\s+(?:by|when|whenever|each time|every time|once)|every\s+time|each\s+time|whenever"
    r"|as\s+and\s+when|as\s+soon\s+as|upon|on\s+receipt\s+of|when)\s+(?P<rest>[^.;:,—–]+)",
    re.IGNORECASE,
)
_CLAUSE_END = re.compile(r"\s+(?:so|because|and then|which|but|although)\b.*$", re.IGNORECASE)


def _trigger_phrase(text: str) -> Optional[str]:
    for m in _TRIGGER.finditer(text):
        lead = re.sub(r"\s+", " ", m.group("lead").lower())
        rest = _CLAUSE_END.sub("", m.group("rest")).strip(" -")
        rest = re.sub(r"\s+(?:us|me)\b", "", rest)  # "notifies us of" -> "notifies of"
        if len(rest.split()) < 2:
            continue
        if lead.startswith("triggered"):
            phrase = f"{lead} {rest}"
        elif lead in ("every time", "each time"):
            phrase = f"triggered each time {rest}"
        elif lead == "whenever":
            phrase = f"triggered whenever {rest}"
        elif lead == "when":
            phrase = f"triggered when {rest}"
        else:
            phrase = f"triggered {lead} {rest}"
        return _tidy(phrase)
    return None


def _frequency(text: str) -> Optional[str]:
    lowered = text.lower()
    for pattern, label in _FREQUENCY_RULES:
        if re.search(pattern, lowered):
            return label
    return None


def condense_when(text: Optional[str]) -> Optional[str]:
    if not text or not text.strip():
        return text
    trigger = _trigger_phrase(text)
    # "every <period>" is a frequency; a trigger is something that happens.
    frequency = _frequency(text)
    if trigger and frequency:
        return f"{frequency}; {trigger[0].lower() + trigger[1:]}"
    return trigger or frequency or _first_sentences(text, 1, 120)


# ----------------------------------------------------------------------------- WHO

_ROLE_NOUNS = (
    "Manager|Supervisor|Analyst|Administrator|Admin|Officer|Controller|Director|Head|Lead|Accountant|Clerk|"
    "Engineer|Developer|Reviewer|Approver|Owner|Coordinator|Specialist|Executive|Auditor|Treasurer|Assistant|"
    "Team|Department|Committee|Board|Desk|Function|Group|Staff|Personnel"
)
_CAPITALISED_ROLE = re.compile(
    rf"\b((?:[A-Z][A-Za-z&/\-]*\s+){{0,3}}(?:{_ROLE_NOUNS}))\b"
)
_LOWERCASE_ROLE = re.compile(
    rf"\b(?i:the|our|my|a|an)\s+((?:[a-z]+\s+){{0,2}}(?:{_ROLE_NOUNS.lower()}))\b"
)
_KNOWN_BODY = re.compile(r"\b(Change Advisory Board|CAB)\b")
_PERSON_IN_ORG = re.compile(
    r"\b(?:colleagues?|teammates?|team\s+members?|people|staff|someone|member|members|person|one\s+of\s+(?:my|the)\s+\w+)"
    r"\s+(?:in|from|within|on)\s+(?:the\s+)?([A-Z][A-Za-z&]*(?:\s+[A-Z][A-Za-z&]*)*)"
)
_LEADING_ARTICLE = re.compile(r"^(?:The|Our|My|A|An)\s+", re.IGNORECASE)
# Words that describe a part played, not who plays it ("the approver is independent of the preparer").
_GENERIC_ALONE = {
    "team", "group", "staff", "function", "department", "board", "desk", "personnel",
    "approver", "reviewer", "owner", "preparer", "assistant", "specialist", "executive",
}


def _title(role: str) -> str:
    return " ".join(w if w.isupper() else w.capitalize() for w in role.split())


_NEGATED = re.compile(
    r"\b(?:rarely|never|seldom|hardly|not|unavailable|absent|away|busy|nobody|no one)\b|n't\b", re.IGNORECASE
)


def _is_negated(text: str, end: int) -> bool:
    """A role mentioned as NOT doing it ("the Finance Manager is rarely available")
    is not who performs the control, so it must not be reported as WHO."""
    tail = re.split(r"[.;,]|\s-\s", text[end:], maxsplit=1)[0]
    return bool(_NEGATED.search(tail))


def condense_who(text: Optional[str]) -> Optional[str]:
    if not text or not text.strip():
        return text
    found: List[tuple] = []
    for m in _CAPITALISED_ROLE.finditer(text):
        if not _is_negated(text, m.end()):
            found.append((m.start(), _LEADING_ARTICLE.sub("", m.group(1)).strip()))
    for m in _LOWERCASE_ROLE.finditer(text):
        if not _is_negated(text, m.end()):
            found.append((m.start(1), _title(m.group(1))))
    for m in _PERSON_IN_ORG.finditer(text):
        if not _is_negated(text, m.end()):
            found.append((m.start(1), m.group(1).strip()))
    for m in _KNOWN_BODY.finditer(text):
        if not _is_negated(text, m.end()):
            found.append((m.start(1), m.group(1)))

    roles: List[str] = []
    for _, role in sorted(found):
        if not role or role.lower() in _GENERIC_ALONE:
            continue
        if role.lower() not in (r.lower() for r in roles):
            roles.append(role)
    roles = roles[:3]
    if not roles:
        # e.g. a first-person answer with no role named: keep what was said
        return _first_sentences(text, 2, 160)
    if len(roles) == 1:
        return roles[0]
    return ", ".join(roles[:-1]) + " and " + roles[-1]


# ----------------------------------------------------------------------------- WHY

_VERB_BASE = {
    "prevents": "prevent", "preventing": "prevent", "prevent": "prevent",
    "ensures": "ensure", "ensuring": "ensure", "ensure": "ensure",
    "avoids": "avoid", "avoiding": "avoid", "avoid": "avoid",
    "stops": "stop", "stopping": "stop", "stop": "stop",
    "detects": "detect", "detecting": "detect", "detect": "detect",
    "reduces": "reduce", "reducing": "reduce", "reduce": "reduce",
    "protects against": "protect against", "protecting against": "protect against",
    "mitigates": "mitigate", "mitigating": "mitigate", "mitigate": "mitigate",
    "confirms": "confirm", "confirming": "confirm", "verifies": "verify", "verifying": "verify",
    "limits": "limit", "limiting": "limit", "safeguards": "safeguard", "safeguarding": "safeguard",
}
_VERBS = "|".join(sorted(_VERB_BASE, key=len, reverse=True))
_PURPOSE_PATTERNS = [
    # "so that / in order to ... " is left alone; these name the purpose directly
    re.compile(rf"\b(?:this|it|that)\s+(?:also\s+|helps\s+)?(?P<v>{_VERBS})\s+(?P<o>[^.;]+)", re.IGNORECASE),
    re.compile(rf"\b(?:way|aim|goal|purpose|point|idea|reason)\s+(?:of|is\s+(?:to|for))\s+(?P<v>{_VERBS})\s+(?P<o>[^.;]+)", re.IGNORECASE),
    re.compile(rf"\b(?:to|in\s+order\s+to)\s+(?P<v>{_VERBS})\s+(?P<o>[^.;]+)", re.IGNORECASE),
    re.compile(r"\bto\s+(?P<v>make\s+sure)\s+(?P<o>[^.;]+)", re.IGNORECASE),
    re.compile(r"\b(?:the\s+)?(?:point|purpose|aim|goal|idea)\s+is\s+to\s+(?P<v>)(?P<o>[^.;]+)", re.IGNORECASE),
]


def condense_why(text: Optional[str]) -> Optional[str]:
    if not text or not text.strip():
        return text
    for pattern in _PURPOSE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        verb = m.group("v").lower()
        verb = "ensure" if verb == "make sure" else _VERB_BASE.get(verb, verb)
        obj = _CLAUSE_END.sub("", m.group("o")).strip(" ,")
        if len(obj.split()) >= 2:
            return _tidy(f"to {verb} {obj}".replace("to  ", "to "))
    return _first_sentences(text, 1, 160, depersonalise=True)


# ----------------------------------------------------------------------------- WHERE

_PLACE_SUFFIX = (
    "system|tool|platform|portal|application|app|database|folder|drive|spreadsheet|workbook|repository|"
    "register|log|tracker|ticketing system|mailbox|server|site|module"
)
_CAMEL = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")  # ServiceNow, SharePoint
_PROPER_PAIR = re.compile(r"(?<=[a-z,] )([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b")  # Active Directory (not sentence-initial)
_PLACE_NOUN = re.compile(
    rf"\b(?:in|on|within|via|using|through|from|into|to)\s+(?:the|our|a|an)\s+((?:[a-z]+\s+){{0,3}}(?:{_PLACE_SUFFIX}))\b",
    re.IGNORECASE,
)
_CALLED = re.compile(r"(?:called|named|titled)\s+[\"“']([^\"”']+)[\"”']")
_NOT_PLACES = {"the", "our", "each", "every", "this", "that", "one", "same", "all", "my"}


def condense_where(text: Optional[str]) -> Optional[str]:
    if not text or not text.strip():
        return text
    found: List[tuple] = []
    for m in _CAMEL.finditer(text):
        found.append((m.start(), m.group(0)))
    for m in _PROPER_PAIR.finditer(text):
        found.append((m.start(1), m.group(1)))
    for m in _PLACE_NOUN.finditer(text):
        phrase = " ".join(m.group(1).split())
        if phrase.split()[0].lower() in _NOT_PLACES:
            phrase = " ".join(phrase.split()[1:])
        if phrase and len(phrase.split()) >= 2 or phrase.lower() in ("database", "spreadsheet", "workbook", "portal"):
            found.append((m.start(1), _title(phrase)))
    for m in _CALLED.finditer(text):
        found.append((m.start(), "“" + m.group(1).strip().rstrip(".,;") + "”"))

    places: List[str] = []
    for _, place in sorted(found):
        if not any(place.lower() == p.lower() or place.lower() in p.lower() or p.lower() in place.lower() for p in places):
            places.append(place)
    # "shared drive folder called "Access Reviews"" is one place, not two
    if len(places) >= 2 and places[-1].startswith("“") and not places[-2].startswith("“"):
        places[-2:] = [f"{places[-2]} {places[-1]}"]
    places = places[:3]
    if not places:
        return _first_sentences(text, 1, 140)
    return ", ".join(places)


# ----------------------------------------------------------------------------- WHAT / HOW

def condense_what(text: Optional[str]) -> Optional[str]:
    """What happens: the first substantive sentence (a second only if both stay short), filler removed."""
    if not text or not text.strip():
        return text
    return _first_sentences(text, 2, 160, depersonalise=True)


_SEQUENCE_WORD = re.compile(r"^(?:then|next|after that|afterwards|finally|first|also|and then)\b[,\s]*", re.IGNORECASE)


def condense_how(text: Optional[str]) -> Optional[str]:
    """How it is done: keep the steps (numbered), tidy each, drop filler steps."""
    if not text or not text.strip():
        return text
    steps = []
    for s in _sentences(text):
        # the numbering already carries the order, so "then"/"next" add nothing
        s = _SEQUENCE_WORD.sub("", _depersonalise(s))
        s = _clause_trim(_tidy(s), 170)
        if len(s.split()) >= 3 and s.lower() not in (x.lower() for x in steps):
            steps.append(s)
    if not steps:
        return text
    if len(steps) == 1:
        return steps[0]
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps[:6], start=1))
