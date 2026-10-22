"""Word-for-word captions: timed words in, an ASS file (burned into the
video by ffmpeg's libass) and an SRT file (for YouTube's own captions) out.

The look is the one people know from TikTok: a few words at a time, low in
the middle of the frame, white with a heavy outline, and the word being
spoken lit up in the accent colour. Each spoken word is its own ASS event
showing the whole line with that word coloured, so the highlight moves with
the voice and the line never jumps.

Lines break on length (`CaptionBox.max_chars`, `max_words`), on a pause, and
after a sentence ends. Pure: nothing here runs ffmpeg or reads a file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .presets import FONT, CaptionBox

# Gummfit lime (#A3E635) in ASS's &HAABBGGRR.
ACCENT = "&H0035E6A3&"
PAUSE_MS = 600          # a gap this long starts a new line
MIN_SHOW_MS = 400
HOLD_MS = 300           # a line stays up this long after its last word
# YouTube's captions read better as whole phrases.
SRT_MAX_CHARS = 42
SRT_MAX_WORDS = 12

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SENTENCE_END = (".", "!", "?", "…")


@dataclass(frozen=True)
class Word:
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Line:
    words: tuple[Word, ...]
    start_ms: int
    end_ms: int

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def clean(words: Iterable[Word]) -> list[Word]:
    """Non-empty words in time order, each ending no earlier than it starts."""
    out = []
    for w in words:
        text = " ".join(_CONTROL.sub(" ", w.text or "").split())
        if text:
            start = max(0, int(w.start_ms))
            out.append(Word(text, start, max(start, int(w.end_ms))))
    return sorted(out, key=lambda w: (w.start_ms, w.end_ms))


def group(words: Iterable[Word], *, max_chars: int, max_words: int = 4, pause_ms: int = PAUSE_MS,
          min_show_ms: int = MIN_SHOW_MS, hold_ms: int = HOLD_MS) -> list[Line]:
    """Timed words → caption lines. A line stays up `hold_ms` past its last
    word (at least `min_show_ms` in all), but never into the next line."""
    chunks: list[list[Word]] = []
    for w in clean(words):
        current = chunks[-1] if chunks else None
        if current:
            prev = current[-1]
            joined = len(" ".join(x.text for x in current)) + 1 + len(w.text)
            if (joined > max_chars or len(current) >= max_words or w.start_ms - prev.end_ms >= pause_ms
                    or prev.text.endswith(_SENTENCE_END)):
                current = None
        if current is None:
            chunks.append([w])
        else:
            current.append(w)
    lines: list[Line] = []
    for i, chunk in enumerate(chunks):
        start = chunk[0].start_ms
        end = max(chunk[-1].end_ms + hold_ms, start + min_show_ms)
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1][0].start_ms)
        lines.append(Line(tuple(chunk), start, end))
    return lines


def escape_ass(text: str) -> str:
    """Text that libass shows as written: braces open override blocks and a
    backslash starts a tag, so neither may reach it."""
    text = _CONTROL.sub(" ", text or "")
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def ass_time(ms: int) -> str:
    cs = max(0, int(ms)) // 10
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def ass_document(lines: list[Line], *, width: int, height: int, box: CaptionBox, font: str = FONT,
                 accent: str = ACCENT) -> str:
    """The captions as an ASS script sized to the frame."""
    head = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Pop,{font},{box.font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{box.outline},{box.shadow},2,{box.margin_h},{box.margin_h},{box.margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = []
    for line in lines:
        texts = [escape_ass(w.text) for w in line.words]
        for i, word in enumerate(line.words):
            end = line.words[i + 1].start_ms if i + 1 < len(line.words) else line.end_ms
            start = line.start_ms if i == 0 else word.start_ms
            if end <= start:
                continue
            shown = " ".join(f"{{\\c{accent}}}{t}{{\\r}}" if j == i else t for j, t in enumerate(texts))
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Pop,,0,0,0,,{shown}")
    return "\n".join(head + events) + "\n"


def srt_document(lines: list[Line]) -> str:
    """Phrase-level captions YouTube can take as a caption track."""
    blocks = [f"{n}\n{srt_time(line.start_ms)} --> {srt_time(line.end_ms)}\n{line.text}"
              for n, line in enumerate(lines, start=1)]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def srt_lines(words: Iterable[Word]) -> list[Line]:
    return group(words, max_chars=SRT_MAX_CHARS, max_words=SRT_MAX_WORDS)


def compact(words: Iterable[Word]) -> list[dict[str, Any]]:
    """How the words are kept on the asset row."""
    return [{"t": w.text, "s": w.start_ms, "e": w.end_ms} for w in words]


def expand(payload: Any) -> list[Word]:
    out = []
    for raw in payload if isinstance(payload, list) else []:
        if isinstance(raw, dict) and raw.get("t"):
            try:
                out.append(Word(str(raw["t"]), int(raw.get("s") or 0), int(raw.get("e") or 0)))
            except (TypeError, ValueError):
                continue
    return out


__all__ = [
    "ACCENT", "Word", "Line", "clean", "group", "escape_ass", "ass_time", "srt_time", "ass_document",
    "srt_document", "srt_lines", "compact", "expand",
]
