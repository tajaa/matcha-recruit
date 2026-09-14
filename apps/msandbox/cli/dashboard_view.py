"""Dependency-free dashboard layout. Rendering never probes or mutates sessions."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from .models import SessionRecord, port_lines
from .terminal_ui import clip, plain

TABS = (
    "Overview",
    "Processes",
    "Tools & access",
    "Files",
    "Testing",
    "Branch & PR",
    "AutoPR",
)
GLOBALS = (
    ("+ New session", "new"),
    ("AutoPR runs", "autopr"),
    ("Legacy workspace", "legacy"),
    ("Clean up resources", "cleanup"),
    ("Exit manager", "exit"),
)


@dataclass(frozen=True)
class Row:
    text: str
    action: str = ""
    tone: str = "text"


@dataclass(frozen=True)
class SidebarEntry:
    """One row of the left list. `session_id` marks the ones backed by a session."""

    label: str
    action: str
    detail: str = ""
    session_id: str = ""
    hint: str = ""


def sidebar_entries(
    records: list[SessionRecord], autopr_entry: SidebarEntry | None = None
) -> list[SidebarEntry]:
    """The single definition of the left list: AutoPR run, sessions, then globals.

    The renderer and the key handler both index this. They used to derive it
    separately (`records + GLOBALS`, `state.sidebar < len(records)`,
    `len(records) + len(GLOBALS)`), which only agreed while every row was a
    session; a row that appears or disappears between frames made the two
    disagree and Enter act on the wrong entry.
    """
    entries: list[SidebarEntry] = []
    if autopr_entry is not None:
        entries.append(autopr_entry)
    entries += [
        SidebarEntry(
            f"{record.name} · {record.phase}",
            f"session:{record.id}",
            f"{record.agent} · {record.permission_mode}",
            record.id,
        )
        for record in records
    ]
    entries += [SidebarEntry(label, action) for label, action in GLOBALS]
    return entries


@dataclass
class ViewState:
    session_id: str | None = None
    tab: int = 0
    region: int = 0  # sidebar, tabs, content
    sidebar: int = 0
    cursor: int = 0
    scroll: int = 0
    notice: str = "Select a session. Saved status is not a live measurement."
    autopr_id: str | None = None


@dataclass(frozen=True)
class Target:
    x: int
    y: int
    width: int
    action: str


@dataclass
class Layout:
    width: int
    height: int
    draws: list[tuple[int, int, str, str]] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    content_height: int = 1
    content_lines: int = 0
    action_lines: list[int] = field(default_factory=list)

    def put(
        self, x: int, y: int, text: str, tone: str = "text", width: int | None = None
    ):
        if 0 <= x < self.width and 0 <= y < self.height:
            value = clip(
                text, min(self.width - x, width if width is not None else self.width)
            )
            self.draws.append((x, y, value, tone))

    def button(self, x: int, y: int, text: str, action: str, width: int, focused=False):
        self.put(x, y, " " * width, "selected" if focused else "button", width)
        self.put(
            x,
            y,
            ("> " if focused else "  ") + text,
            "selected" if focused else "button",
            width,
        )
        if 0 <= y < self.height:
            self.targets.append(Target(x, y, min(width, self.width - x), action))

    def hit(self, x: int, y: int) -> str | None:
        return next(
            (t.action for t in self.targets if t.y == y and t.x <= x < t.x + t.width),
            None,
        )


def overview(record: SessionRecord) -> list[Row]:
    rows = [
        Row("WORKSPACE", tone="accent"),
        Row(f"Harness: {record.agent}    Permissions: {record.permission_mode}"),
        Row(f"Starting point: {record.base_ref}"),
        Row(f"Branch: {record.target_branch or 'Not selected yet'}"),
        Row(f"Worktree: {record.worktree_path}"),
    ]
    if record.pr_number:
        rows.append(
            Row(f"PR #{record.pr_number}: {record.pr_url or 'URL unavailable'}")
        )
    rows.append(Row("Development ports (reachability: Processes tab)", tone="muted"))
    rows += [Row(line) for line in port_lines(record.ports)]
    rows += [
        Row(""),
        Row("WHAT HAPPENS NEXT", tone="accent"),
        Row(
            "Start opens this worktree. Change harness keeps files and commits, but uses a separate conversation."
        ),
        Row(
            "Ctrl-b, then d returns here while the harness keeps running. Ctrl-c interrupts the harness."
        ),
        Row(""),
        Row("QUICK ACTIONS", tone="accent"),
        Row("Run validation  /  choose changed files or full PR", "validate"),
        Row("Manage Chromium  /  start, stop, screenshot", "browser"),
        Row("View exited harness output  /  inspect before restart", "harness-output"),
        Row("Files & attachments  /  import, preview, send, export", "files"),
        Row("Create branch / PR  /  optional Luna high draft", "publish"),
        Row("Stop session  /  preserve workspace files", "stop"),
        Row("Release published session  /  removes worktree after checks", "release"),
    ]
    return rows


def build_layout(
    records: list[SessionRecord],
    state: ViewState,
    rows: list[Row],
    width: int,
    height: int,
    autopr_entry: SidebarEntry | None = None,
) -> Layout:
    """Return clipped drawing commands and exact click targets for this viewport."""
    width, height = max(1, width - 1), max(1, height)
    layout = Layout(width, height)
    entries = sidebar_entries(records, autopr_entry)
    state.sidebar = min(max(0, state.sidebar), len(entries) - 1)
    layout.put(2, 1, "◆  Matcha Sandbox", "accent")
    if width < 72 or height < 20:
        layout.put(1, 4, "Resize to at least 73 columns × 20 rows.")
        layout.put(1, 6, "q: quit   c: classic menu")
        return layout
    side = min(32, max(23, width // 4))
    for y in range(3, height - 3):
        layout.put(side, y, "│", "border")
    layout.put(0, 2, "─" * width, "border")
    layout.put(
        max(side + 3, width - 38), 1, "Local controller · saved session state", "muted"
    )
    layout.put(2, 4, "SESSIONS", "muted")
    visible = max(1, (height - 11) // 3)
    start = max(0, min(state.sidebar - visible // 2, len(entries) - visible))
    for offset, index in enumerate(range(start, min(len(entries), start + visible))):
        entry = entries[index]
        label = entry.label
        y = 6 + offset * 3
        focused = state.region == 0 and index == state.sidebar
        if entry.session_id and entry.session_id == state.session_id:
            label = "● " + label
        layout.button(1, y, label, entry.action, side - 2, focused)
        if entry.detail:
            layout.put(3, y + 1, entry.detail, "muted", side - 4)
    layout.put(
        2,
        height - 5,
        f"{state.sidebar + 1}/{len(entries)} · ↑↓ select",
        "muted",
        side - 3,
    )
    x, content_width = side + 3, width - side - 5
    record = next((r for r in records if r.id == state.session_id), None)
    pinned_actions = (
        record
        and content_width >= 60
        and [r.action for r in rows[:3]] == ["open", "switch", "shell"]
    )
    header_width = content_width - 26 if pinned_actions else content_width
    layout.put(
        x,
        4,
        "AutoPR activity & handoff"
        if state.tab == 6
        else record.name
        if record
        else "Your sandbox",
        "title",
        header_width,
    )
    layout.put(
        x,
        5,
        "View a run, take over, then hand your edits back."
        if state.tab == 6
        else f"{record.agent} · {record.permission_mode} · saved: {record.phase}"
        if record
        else "Create a session to get started.",
        "muted",
        header_width,
    )
    if pinned_actions:
        for index, row in enumerate(rows[:3]):
            layout.button(
                width - 26,
                4 + index,
                row.text,
                row.action,
                24,
                state.region == 2 and state.cursor == index,
            )
            layout.action_lines.append(-1)
        rows = rows[4:]
    # Two tab rows work at laptop terminal widths; one row on wide terminals.
    tab_x, tab_y = x, 8
    for index, label in enumerate(TABS):
        tab_width = len(label) + 4
        if tab_x + tab_width > width - 2:
            tab_x, tab_y = x, tab_y + 1
        layout.button(
            tab_x,
            tab_y,
            label,
            f"tab:{index}",
            tab_width,
            state.region == 1 and state.tab == index,
        )
        if state.tab == index:
            layout.put(tab_x, tab_y, "[" + label + "]", "accent", tab_width)
        tab_x += tab_width
    top, bottom = tab_y + 2, height - 5
    layout.content_height = max(1, bottom - top)
    expanded: list[Row] = []
    for row in rows:
        # Action labels stay on one row; description text wraps and scrolls.
        if row.action:
            layout.action_lines.append(len(expanded))
            expanded.append(row)
        else:
            safe_text = plain(row.text)
            lines = textwrap.wrap(
                safe_text,
                width=max(
                    1,
                    content_width // 2
                    if any(ord(c) > 0x2FFF for c in safe_text)
                    else content_width - 3,
                ),
                replace_whitespace=False,
            )
            expanded.extend(Row(line, tone=row.tone) for line in (lines or [""]))
    layout.content_lines = len(expanded)
    state.cursor = min(state.cursor, max(0, len(layout.action_lines) - 1))
    state.scroll = min(state.scroll, max(0, len(expanded) - layout.content_height))
    for index in range(
        state.scroll, min(len(expanded), state.scroll + layout.content_height)
    ):
        row = expanded[index]
        y = top + index - state.scroll
        if row.action:
            focused = state.region == 2 and index == layout.action_lines[state.cursor]
            layout.button(x, y, row.text, row.action, content_width, focused)
        else:
            if row.tone == "accent" and row.text:
                layout.put(x, y, "─" * content_width, "border", content_width)
                layout.put(x + 1, y, " " + row.text + " ", row.tone, content_width - 2)
            else:
                layout.put(x, y, row.text, row.tone, content_width)
    layout.put(
        x,
        height - 5,
        f"{state.scroll + 1}–{min(len(expanded), state.scroll + layout.content_height)}/{len(expanded)} · PgUp/PgDn scroll",
        "muted",
        content_width,
    )
    layout.put(0, height - 4, "─" * width, "border")
    layout.put(2, height - 3, state.notice, "muted", width - 4)
    footer = "Tab: focus  ↑↓: select  Enter/click: open  1–7: tab  r: refresh  q: quit"
    if state.tab == 6 and autopr_entry is not None and autopr_entry.hint:
        footer += "  " + autopr_entry.hint
    layout.put(2, height - 2, footer, "accent")
    layout.put(
        2,
        height - 1,
        "Inside a harness: Ctrl-b then d returns here · Ctrl-c interrupts",
        "muted",
    )
    return layout
