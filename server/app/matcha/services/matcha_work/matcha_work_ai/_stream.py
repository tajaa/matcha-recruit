"""Reading the `reply` out of the engine's JSON while it is still being written.

Claude answers a thread turn with one JSON object (`_claude_thread.ENGINE_SCHEMA`).
The person should see the reply as it is written, and a reply cut short by
`max_tokens` should still be readable, so this decodes the top-level `reply`
string from a JSON prefix of any length:

    extractor = ReplyStreamExtractor()
    extractor.feed('{"mode":"general","reply":"Hel')   # -> "Hel"
    extractor.feed('lo\\nthere"}')                      # -> "lo\\nthere" (a real newline)

Only the top-level key counts: a `"reply"` inside another value (the
`updates_json` string, a nested object) is skipped, wherever the key sits in
the object. Escapes are decoded as JSON defines them, including a `\\uXXXX`
pair or an escape split across two chunks.
"""
from __future__ import annotations

_SIMPLE_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


class ReplyStreamExtractor:
    """Feed it the model's text as it arrives; it returns the newly decoded
    part of the top-level `reply` string each time."""

    def __init__(self) -> None:
        self.reply = ""
        self.done = False
        self._depth = 0
        self._in_string = False
        self._escape = ""  # an escape sequence being read: "\\", "\\u12", ...
        self._expect_key = False  # at depth 1, the next string is a key
        self._key = ""  # the depth-1 key being read
        self._reading_key = False
        self._last_key = ""
        self._in_reply = False
        self._pending_high = ""  # a high surrogate waiting for its pair

    def feed(self, chunk: str) -> str:
        out: list[str] = []
        for ch in chunk:
            if self._in_string:
                self._string_char(ch, out)
                continue
            if ch == "{" or ch == "[":
                self._depth += 1
                self._expect_key = self._depth == 1 and ch == "{"
            elif ch == "}" or ch == "]":
                self._depth -= 1
            elif ch == "," and self._depth == 1:
                self._expect_key = True
            elif ch == ":" and self._depth == 1:
                self._expect_key = False
            elif ch == '"':
                self._in_string = True
                if self._depth == 1 and self._expect_key:
                    self._reading_key, self._key = True, ""
                elif self._depth == 1 and self._last_key == "reply" and not self.done:
                    self._in_reply = True
        text = "".join(out)
        self.reply += text
        return text

    def _string_char(self, ch: str, out: list[str]) -> None:
        if self._escape:
            self._escape += ch
            decoded = self._finish_escape()
            if decoded is not None and self._in_reply:
                self._emit(decoded, out)
            return
        if ch == "\\":
            self._escape = "\\"
            return
        if ch == '"':
            self._in_string = False
            if self._reading_key:
                self._reading_key = False
                self._last_key = self._key
            elif self._in_reply:
                self._in_reply = False
                self.done = True
                if self._pending_high:  # an unpaired high surrogate at the end
                    out.append("�")
                    self._pending_high = ""
            elif self._depth == 1:
                self._last_key = ""
            return
        if self._reading_key:
            self._key += ch
        elif self._in_reply:
            self._emit(ch, out)

    def _finish_escape(self) -> str | None:
        """The decoded escape once it is complete, else None (keep reading)."""
        body = self._escape[1:]
        if body[0] != "u":
            self._escape = ""
            return _SIMPLE_ESCAPES.get(body[0], body[0])
        if len(body) < 5:
            return None
        self._escape = ""
        try:
            return chr(int(body[1:5], 16))
        except ValueError:
            return "�"

    def _emit(self, text: str, out: list[str]) -> None:
        """Pair surrogates that arrive as two `\\u` escapes."""
        for ch in text:
            code = ord(ch)
            if 0xD800 <= code <= 0xDBFF:
                if self._pending_high:
                    out.append("�")
                self._pending_high = ch
                continue
            if 0xDC00 <= code <= 0xDFFF and self._pending_high:
                high = ord(self._pending_high)
                self._pending_high = ""
                out.append(chr(0x10000 + ((high - 0xD800) << 10) + (code - 0xDC00)))
                continue
            if self._pending_high:
                out.append("�")
                self._pending_high = ""
            out.append(ch)


def partial_reply(text: str) -> str | None:
    """The top-level `reply` decoded from a JSON prefix, or None when the
    prefix never reached it."""
    extractor = ReplyStreamExtractor()
    extractor.feed(text)
    if not extractor.reply and not extractor.done:
        return None
    return extractor.reply
