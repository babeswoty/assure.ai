"""Parses the line-tagged transcript format already used by every pilot
fixture (`[L01] Speaker: text`) into a structured Transcript.

Deliberately narrow: this is the one transcript format the project
currently has. No timestamps or speaker names are invented for lines that
don't have them - a line that doesn't match the tagged format is simply
skipped (it's header/label text, not dialogue - see the pilot fixtures'
own header blocks).
"""
import re

from app.transcript_extraction.models import Transcript, TranscriptSegment

_LINE_PATTERN = re.compile(
    r"^\[(?P<segment_id>[^\]]+)\]\s*(?:(?P<speaker>[^:]+):\s*)?(?P<text>.*)$", re.MULTILINE
)


def parse_line_tagged_transcript(
    raw_text: str, transcript_id: str, control_id: str, source_name: str
) -> Transcript:
    """Parses text where dialogue lines look like `[L01] Interviewer: ...`.

    Non-matching lines (blank lines, header/label text at the top of the
    fixture files) are skipped rather than guessed at.
    """
    segments = []
    for line in raw_text.splitlines():
        match = _LINE_PATTERN.match(line.strip())
        if not match:
            continue
        text = match.group("text").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                segment_id=match.group("segment_id").strip(),
                speaker=(match.group("speaker") or "").strip() or None,
                text=text,
            )
        )

    return Transcript(
        transcript_id=transcript_id,
        control_id=control_id,
        source_name=source_name,
        segments=segments,
    )


_SPEAKER_LINE_PATTERN = re.compile(r"^(?P<speaker>[^:]{1,60}):\s*(?P<text>.+)$")


def parse_transcript_text(
    raw_text: str, transcript_id: str, control_id: str, source_name: str
) -> Transcript:
    """Parses whatever transcript text a tester pastes into the test UI.

    Uses parse_line_tagged_transcript() unchanged when the text already has
    `[L01]`-style tags (the pilot fixture format). Otherwise, falls back to
    auto-numbering each non-blank line (`L01`, `L02`, ...), still detecting
    a leading "Speaker:" prefix where present. No content is invented -
    this only assigns positional ids to text the tester supplied.
    """
    if _LINE_PATTERN.search(raw_text):
        return parse_line_tagged_transcript(raw_text, transcript_id, control_id, source_name)

    segments = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _SPEAKER_LINE_PATTERN.match(stripped)
        speaker = match.group("speaker").strip() if match else None
        text = match.group("text").strip() if match else stripped
        segments.append(
            TranscriptSegment(segment_id=f"L{len(segments) + 1:02d}", speaker=speaker, text=text)
        )

    return Transcript(
        transcript_id=transcript_id,
        control_id=control_id,
        source_name=source_name,
        segments=segments,
    )
