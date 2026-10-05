"""Best-effort, deterministic rewrite of first-person interview speech into
third-person passive control-documentation style, e.g.:

    "I create the account in Active Directory" -> "The account was created in Active Directory"

Why this exists: transcript answers are naturally first-person ("I do X",
"we check Y"), but a control description is professional documentation
describing a standing process, not a transcript quote. Rewriting only the
VOICE (never the facts) keeps the documented value readable and audit-style
while everything remains traceable to the same source_references - only
`DocumentedAttribute.value` is touched; `SourceReference.excerpt` always
stays a verbatim quote of the transcript, untouched by this module.

Deliberately narrow, no LLM: only rewrites an "I/We <verb> <object>" clause
when the verb is in a small, curated whitelist we're confident about the
past-participle form for. Anything else - unrecognized verbs, clauses with
no clear object, elided-subject continuations ("...then assign X") - is
left exactly as extracted rather than risking broken grammar. This is a
known, accepted limitation: some sentences will keep a trailing first-person
fragment. A worse (broken or subtly wrong) rewrite is worse than no rewrite.
"""
import re
from typing import Optional

_PAST_PARTICIPLES = {
    "create": "created", "take": "taken", "check": "checked", "review": "reviewed",
    "submit": "submitted", "approve": "approved", "attach": "attached", "assign": "assigned",
    "disable": "disabled", "remove": "removed", "confirm": "confirmed", "provision": "provisioned",
    "grant": "granted", "log": "logged", "record": "recorded", "perform": "performed",
    "complete": "completed", "notify": "notified", "escalate": "escalated", "retain": "retained",
    "verify": "verified", "sign": "signed", "save": "saved", "revoke": "revoked",
    "pull": "pulled", "prepare": "prepared", "reconcile": "reconciled", "monitor": "monitored",
    "inspect": "inspected", "test": "tested", "deploy": "deployed", "send": "sent",
    "use": "used", "handle": "handled", "ask": "asked", "look": "looked", "pick": "picked",
    "file": "filed", "store": "stored", "update": "updated", "upload": "uploaded",
    "compare": "compared", "match": "matched", "investigate": "investigated",
}

_BOUNDARY_WORDS = (
    "in", "on", "using", "to", "for", "with", "before", "after", "during", "from",
    "at", "then", "and", "so", "because", "of", "against", "within", "via", "if",
    "once", "until", "when",
)

_WEAK_OBJECT_HEADS = {
    "do", "does", "did", "it", "so", "this", "that", "them", "along", "also", "just", "really", "not",
    # Phrasal-verb particles ("sign off", "check in", "take up", ...) - a
    # particle immediately after the verb is not a real object, and
    # treating it as one produces broken output (found via review: "I sign
    # off on the review" -> "the off was signed on the review").
    "off", "up", "down", "out", "back", "away",
}
_DETERMINERS = {"a", "an", "the", "my", "our", "their", "his", "her", "its", "this", "that"}
_SINGULAR_S_EXCEPTIONS = {"access", "process", "status", "business", "this"}

_PRONOUN_VERB_OBJECT_RE = re.compile(
    r"\b(?:I'm|I am|I|We're|We are|We)\s+(?P<verb>[A-Za-z]+)\s+(?P<obj>.+?)"
    r"(?=\s+\b(?:" + "|".join(_BOUNDARY_WORDS) + r")\b|[.!?]|$)",
    re.IGNORECASE,
)


def _passivize_match(match: "re.Match[str]") -> str:
    verb = match.group("verb").lower()
    obj = match.group("obj").strip().rstrip(",")
    participle = _PAST_PARTICIPLES.get(verb)
    if not participle or not obj:
        return match.group(0)

    obj_tokens = obj.split()
    first_word = obj_tokens[0].lower().strip(",.")
    # A real object never starts with a preposition/conjunction itself - if
    # it does, the boundary-word scan failed to find an earlier stopping
    # point (e.g. a comma broke up the whitespace the lookahead needed) and
    # swallowed a whole WH-clause instead of a simple noun phrase. Found via
    # review: "We look at what was changed, why, ..." produced an object
    # starting with "at". Safer to leave the clause untouched than guess.
    if first_word in _WEAK_OBJECT_HEADS or first_word in _BOUNDARY_WORDS:
        return match.group(0)

    if first_word not in _DETERMINERS:
        obj = f"the {obj}"
        obj_tokens = obj.split()

    last_word = obj_tokens[-1].lower().strip(",.")
    is_plural = last_word.endswith("s") and last_word not in _SINGULAR_S_EXCEPTIONS and len(last_word) > 3
    to_be = "were" if is_plural else "was"

    replacement = f"{obj} {to_be} {participle}"

    preceding = match.string[: match.start()].rstrip()
    is_sentence_start = not preceding or preceding[-1] in ".!?"
    if is_sentence_start:
        replacement = replacement[:1].upper() + replacement[1:]
    return replacement


# A second verb joined to an already-passive clause: "the journal was prepared in the
# system and attach the schedule" -> "... and the schedule was attached". Only a plain
# noun-phrase object is rewritten; an object that is really a clause (it contains a verb
# such as "is"/"are") is left alone.
_CONJUNCT_RE = re.compile(
    r"(?P<conj>(?:,\s*)?\b(?:and then|and|then)\s+)(?P<verb>[A-Za-z]+)\s+(?P<obj>.+?)"
    r"(?=\s+\b(?:" + "|".join(_BOUNDARY_WORDS) + r")\b|[.!?;,]|$)",
    re.IGNORECASE,
)
_CLAUSE_VERBS = {"is", "are", "was", "were", "has", "have", "had", "will", "should", "can", "must", "does", "do"}
_ALREADY_PASSIVE = re.compile(r"\b(?:was|were)\s+[a-z]+(?:ed|en|t)\b", re.IGNORECASE)


def _passivize_conjunct(match: "re.Match[str]") -> str:
    verb = match.group("verb").lower()
    obj = match.group("obj").strip().rstrip(",")
    participle = _PAST_PARTICIPLES.get(verb)
    if not participle or not obj:
        return match.group(0)
    sentence_so_far = re.split(r"[.!?]", match.string[: match.start()])[-1]
    if not _ALREADY_PASSIVE.search(sentence_so_far):
        return match.group(0)

    tokens = obj.split()
    first_word = tokens[0].lower().strip(",.")
    # If the rest of the sentence still holds a clause verb, the "object" is really the
    # start of a longer clause ("confirm the accounts and amounts are correct"): leave it.
    remainder = re.split(r"[.!?;]", match.string[match.end():], maxsplit=1)[0]
    if (
        first_word in _WEAK_OBJECT_HEADS
        or first_word in _BOUNDARY_WORDS
        or len(tokens) > 8
        or any(t.lower().strip(",.") in _CLAUSE_VERBS for t in tokens)
        or any(t.lower().strip(",.") in _CLAUSE_VERBS for t in remainder.split())
    ):
        return match.group(0)
    if first_word not in _DETERMINERS:
        obj = f"the {obj}"
        tokens = obj.split()
    last_word = tokens[-1].lower().strip(",.")
    is_plural = last_word.endswith("s") and last_word not in _SINGULAR_S_EXCEPTIONS and len(last_word) > 3
    return f"{match.group('conj')}{obj} {'were' if is_plural else 'was'} {participle}"


def to_documentation_voice(text: Optional[str]) -> Optional[str]:
    """Rewrites recognizable first-person clauses in `text` to passive
    voice. Returns text unchanged (including None) when nothing matches."""
    if not text:
        return text
    text = _PRONOUN_VERB_OBJECT_RE.sub(_passivize_match, text)
    return _CONJUNCT_RE.sub(_passivize_conjunct, text)
