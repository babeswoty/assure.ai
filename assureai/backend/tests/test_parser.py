from app.transcript_extraction.parser import parse_line_tagged_transcript, parse_transcript_text


def test_parse_transcript_text_detects_bracket_format_with_header_text_above_it():
    """Regression test: _LINE_PATTERN.search() previously used `^` without
    re.MULTILINE, so detection only matched if a [L01]-tagged line was the
    VERY FIRST line of the whole string. Every real pilot fixture has
    header/label text before the first tagged line, so detection always
    silently failed and fell through to the crude line-by-line fallback -
    which re-numbers every line sequentially (including the header lines),
    offsetting every real segment id (found while building the
    design-assessment agent: potential_gap's first exchange didn't end in
    '?' and its garbled fallback-parser speaker field ("[L01] Interviewer")
    no longer exact-matched the prompt-detection set, so it was silently
    dropped instead of classified as a prompt at all).
    """
    raw = (
        "SOME HEADER TEXT ABOVE THE TAGGED LINES\n"
        "Another label line: not dialogue\n"
        "\n"
        "[L01] Interviewer: Walk me through what happens.\n"
        "[L02] Interviewee: We do the thing.\n"
    )
    via_text = parse_transcript_text(raw, transcript_id="x", control_id="C-1", source_name="t")
    via_tagged = parse_line_tagged_transcript(raw, transcript_id="x", control_id="C-1", source_name="t")

    assert [s.segment_id for s in via_text.segments] == ["L01", "L02"]
    assert via_text.segments[0].speaker == "Interviewer"
    assert via_text.segments[0].text == "Walk me through what happens."
    assert via_text.model_dump() == via_tagged.model_dump()


def test_parse_transcript_text_falls_back_for_genuinely_untagged_text():
    raw = "Interviewer: Who performs this?\nInterviewee: The manager does.\n"
    result = parse_transcript_text(raw, transcript_id="x", control_id="C-1", source_name="t")
    assert [s.segment_id for s in result.segments] == ["L01", "L02"]
    assert result.segments[0].speaker == "Interviewer"
