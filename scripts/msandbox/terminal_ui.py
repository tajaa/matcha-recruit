"""Small terminal renderer shared by every manager screen (no dependencies)."""

from __future__ import annotations

import re
import unicodedata


def plain(value: object) -> str:
    """Never interpret terminal escapes supplied by files, Git, or processes."""
    return "".join(
        c
        for c in str(value)
        if c == "\n" or not unicodedata.category(c).startswith("C")
    )


def clip(value: str, width: int) -> str:
    result = ""
    used = 0
    for char in plain(value).replace("\n", " "):
        cells = (
            0
            if unicodedata.combining(char)
            else (2 if unicodedata.east_asian_width(char) in "WF" else 1)
        )
        if used + cells > max(0, width):
            break
        result += char
        used += cells
    return result


def mouse_key(data: bytes) -> str | None:
    # X10 reports are ESC [ M followed by three encoded bytes. Some terminal
    # hops support mouse tracking but ignore the requested SGR (1006) mode.
    if len(data) == 6 and data.startswith(b"\x1b[M"):
        return "ignore"
    match = re.fullmatch(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])", data)
    if not match:
        return None
    button, x, y = (int(v) for v in match.groups()[:3])
    if button == 64:
        return "up"
    if button == 65:
        return "down"
    if button == 0 and match[4] == b"M":
        return f"click:{x}:{y}"
    return "ignore"


def frame(
    title: str, labels: list[str], selected: int, width: int, height: int
) -> tuple[str, dict[int, int]]:
    """Render a bounded viewport and return its clickable row -> choice map."""
    width, height = max(20, width - 1), max(10, height)
    heading = plain(title).splitlines() or ["Sandbox"]
    limit = max(1, height - 7)
    if len(heading) > limit:
        heading = [heading[0], *heading[-(limit - 1):]] if limit > 1 else [heading[-1]]
    lines = ["\x1b[1;36m" + clip(heading[0], width) + "\x1b[0m"]
    for line in heading[1:]:
        lines.append("\x1b[2m" + clip(line, width) + "\x1b[0m")
    lines.append("─" * width)
    available = max(1, height - len(lines) - 5)
    start = min(max(0, selected - available // 2), max(0, len(labels) - available))
    targets: dict[int, int] = {}
    for index in range(start, min(len(labels), start + available)):
        name = labels[index].split(" — ", 1)[0]
        text = clip(
            f" {'›' if index == selected else ' '} {index + 1:2}. {name}", width
        )
        targets[len(lines) + 1] = index
        lines.append(("\x1b[30;46m" + text + "\x1b[0m") if index == selected else text)
    lines.extend([""] * max(0, height - 5 - len(lines)))
    detail = labels[selected].partition(" — ")[2]
    lines += [
        "─" * width,
        clip(detail or "Select an action to continue.", width),
        clip(
            f"{selected + 1}/{len(labels)}  ↑↓ / j k   Enter / click   Esc / q: back",
            width,
        ),
        clip("Ctrl-C: back · Inside a harness: Ctrl-b d returns here", width),
    ]
    return "\x1b[H\x1b[2J" + "\n".join(lines), targets
