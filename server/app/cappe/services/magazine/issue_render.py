"""An issue → HTML: its cover, its contents, and the whole issue as one book
(`/issues/<number>`), plus the archive (`/issues`) and the front page's lead.

The cover is a 4:5 artboard (`.mzc`): the photo, the darkening behind the
words, then each element placed in percent of the artboard with its type size
in container-query units (`cqw`), so the same cover is drawn at every size —
a page of the book, a card in the archive, the editor. `element_style` is the
one place an element's look is decided; the cover editor's live canvas
mirrors it (`client/src/cappe/magazine/issues/coverStyle.ts`).

The photo's credit is always printed on the cover, from the library row; an
AI picture always reads "AI illustration".

In the book the cover lies on the mat alone, on the right of the first spread
like a closed magazine, and opens onto the contents. Its face is drawn over
the cover page from outside the flowing columns (`.mz-issue__face`, a child
of the pages box), so it bleeds to the paper's edges without being split
across pages; the page itself is an empty placeholder in the flow. Each story
starts on a new page with its own opener; a paid story shows its free part
and its own paywall, and one script serves every paywall on the page
(`render/assets/paywall.js`). The contents' page numbers are filled in by
`render/assets/book.js` (and by the editor's `reader/book.ts`) from where
each story's first page falls.
"""
from __future__ import annotations

from html import escape
from typing import Optional

from .figures import credit_html, credit_text, img_html
from .issue_schema import issue_line_text
from .story_render import field
from .topics import topic_label

_WEIGHT = {"regular": 400, "bold": 700, "black": 900}
_TRACKING = {"normal": "0", "tight": "-0.02em", "wide": "0.12em"}


def issue_path(number: int) -> str:
    return f"/issues/{int(number)}"


def story_anchor(slug: str) -> str:
    return f"mz-s-{slug}"


def issue_label(issue: dict) -> str:
    """"No. 3" or "No. 3 — The tide issue"."""
    title = (issue.get("title") or "").strip()
    return f"No. {issue['number']}" + (f" — {title}" if title else "")


def _n(value: float) -> str:
    """4.0 → "4", 5.6 → "5.6" (as JavaScript prints them)."""
    return format(float(value), "g")


def _colour(value: str) -> str:
    return "var(--mz-accent)" if value == "accent" else value


def element_style(el: dict) -> str:
    """Where a cover element sits and how its words look."""
    parts = [
        f"left:{_n(el['x'])}%", f"top:{_n(el['y'])}%", f"width:{_n(el['w'])}%",
        f"font-size:{_n(el['size'])}cqw", f"color:{_colour(el['color'])}", f"text-align:{el['align']}",
        f"font-weight:{_WEIGHT.get(el['weight'], 700)}", f"letter-spacing:{_TRACKING.get(el['tracking'], '0')}",
        f"font-family:var({'--mz-b' if el['font'] == 'body' else '--mz-h'})",
    ]
    if el.get("case") == "upper":
        parts.append("text-transform:uppercase")
    if el.get("italic"):
        parts.append("font-style:italic")
    return ";".join(parts)


def _scrim(scrim: dict) -> str:
    kind, alpha = scrim.get("kind"), int(scrim.get("strength") or 0) / 100
    if kind not in ("top", "bottom", "full") or alpha <= 0:
        return ""
    if kind == "full":
        background = f"rgba(0,0,0,{alpha * 0.75:.3f})"
    else:
        towards = "bottom" if kind == "top" else "top"
        background = (f"linear-gradient(to {towards},rgba(0,0,0,{alpha:.3f}) 0%,rgba(0,0,0,{alpha * 0.45:.3f}) 28%,"
                      "rgba(0,0,0,0) 55%)")
    return f'<div class="mzc__scrim" style="background:{background}"></div>'


def _photo(cover: dict, asset: Optional[dict], *, size: str, eager: bool, edit: bool = False) -> str:
    photo = cover.get("photo") or {}
    if not asset:
        return ""
    focal = photo.get("focal") or {}
    x, y = int(focal.get("x", 50)), int(focal.get("y", 50))
    style = f"object-position:{x}% {y}%"
    zoom = int(photo.get("zoom") or 100)
    if zoom > 100:
        style += f";transform:scale({_n(zoom / 100)});transform-origin:{x}% {y}%"
    img = img_html(asset, size=size, eager=eager, cls="mzc__img", style=style)
    if not img:
        return ""
    focal_attr = f' data-mz-focal="{x},{y}"' if edit else ""
    return f'<div class="mzc__photo mz-filter--{escape(photo.get("filter") or "none")}"{focal_attr}>{img}</div>'


def _line(index: int, line: dict, hrefs: dict[str, str], *, edit: bool = False) -> str:
    text, sub = line.get("text") or "", line.get("sub") or ""
    words = escape(text)
    if line.get("box") == "solid" and text:
        words = f'<span class="mzc__box" style="background:{_colour(line["box_color"])}">{words}</span>'
    if edit:
        inner = (f'<p class="mzc__text"{field(f"issue:lines.{index}.text", ph="Cover line")}>{words}</p>'
                 f'<p class="mzc__sub"{field(f"issue:lines.{index}.sub", ph="Smaller line")}>{escape(sub)}</p>')
    else:
        inner = (f'<p class="mzc__text">{words}</p>' if text else "") + (
            f'<p class="mzc__sub">{escape(sub)}</p>' if sub else "")
    href = hrefs.get(line.get("post_id") or "")
    if href:
        inner = f'<a class="mzc__link" href="{escape(href, quote=True)}">{inner}</a>'
    return (f'<div class="mzc__el mzc__line" data-mzc-el="line:{index}" style="{element_style(line)}">'
            f"{inner}</div>")


def cover_html(cover: dict, *, mag: dict, number: int, when=None, asset: Optional[dict] = None,
               hrefs: Optional[dict[str, str]] = None, size: str = "card", eager: bool = False,
               link_credit: bool = True, edit: bool = False) -> str:
    """The cover artboard. `hrefs` maps a story's id to where its cover line
    links (only in the book); `link_credit` is off where the cover is itself
    a link, since a link can't hold another. `edit`: the owner's editor —
    each line's words and the issue line can be typed into, every element
    dragged within `.mzc__art`, and the photo's focus dragged."""
    hrefs = hrefs or {}
    mast, issue_line = cover.get("masthead") or {}, cover.get("issue_line") or {}
    art = '<div class="mzc__art" data-mz-art>' if edit else '<div class="mzc__art">'
    parts = [_photo(cover, asset, size=size, eager=eager, edit=edit), _scrim(cover.get("scrim") or {}), art]
    if mast:
        parts.append(f'<p class="mzc__el mzc__mast" data-mzc-el="masthead" style="{element_style(mast)}">'
                     f"{escape(mag.get('name') or '')}</p>")
    if issue_line and not issue_line.get("hidden"):
        words = field("issue:issue_line.text", ph="No. and date") if edit else ""
        parts.append(f'<p class="mzc__el mzc__issue" data-mzc-el="issue_line" style="{element_style(issue_line)}"{words}>'
                     f"{escape(issue_line_text(cover, number, when))}</p>")
    parts += [_line(i, ln, hrefs, edit=edit) for i, ln in enumerate(cover.get("lines") or [])]
    if asset:
        credit = (credit_html(asset, cropped=True) if link_credit
                  else escape(credit_text(asset, cropped=True)))
        if credit:
            c = cover.get("credit") or {}
            parts.append(f'<p class="mzc__credit mzc__credit--{escape(c.get("corner") or "br")} '
                         f'mzc__credit--{escape(c.get("tone") or "light")}">{credit}</p>')
    parts.append("</div>")
    background = _colour(cover.get("background") or "#1b1916")
    return f'<div class="mzc" style="--mzc-bg:{background}">{"".join(parts)}</div>'


# ── contents ────────────────────────────────────────────────────────────────

def _toc_entry(entry: dict, contents: dict, *, feature: bool, edit: bool = False) -> str:
    post, asset = entry["post"], entry.get("asset")
    slug = post["slug"]
    pic = ""
    if contents.get("show_pictures", True) and asset:
        img = img_html(asset, size="wide" if feature else "card", cls="mz-toc__img")
        pic = f'<span class="mz-toc__pic">{img}</span>' if img else ""
    number = (f'<span class="mz-toc__no" data-mz-pageno="{escape(slug, quote=True)}"></span>'
              if contents.get("show_numbers", True) else "")
    kicker = post.get("kicker") or topic_label(post.get("topic"))
    words = [f'<span class="mz-toc__kicker">{escape(kicker)}</span>' if kicker else "",
             f'<span class="mz-toc__title">{escape(post.get("title") or "")}</span>']
    line = entry.get("line") or (post.get("excerpt") if contents.get("show_deks", True) else None)
    if edit:
        # Built apart: quotes nested inside an f-string's braces need Python 3.12 (CI checks 3.11).
        dek = field(f"issue:line:{post['id']}", ph="A line for the contents")
        words.append(f'<span class="mz-toc__dek"{dek}>{escape(line or "")}</span>')
    elif line:
        words.append(f'<span class="mz-toc__dek">{escape(line)}</span>')
    if contents.get("show_bylines") and post.get("byline"):
        words.append(f'<span class="mz-toc__by">By {escape(post["byline"])}</span>')
    cls = "mz-toc mz-toc--feature" if feature else "mz-toc"
    return (f'<a class="{cls}" href="#{story_anchor(slug)}">{pic}{number}'
            f'<span class="mz-toc__words">{"".join(words)}</span></a>')


def contents_html(contents: dict, entries: list[dict], *, label: str, edit: bool = False) -> str:
    """The contents: the heading, then the stories in order, grouped under
    their sections, as a list, a grid of pictures, or a feature (the first
    story large)."""
    layout = contents.get("layout") or "list"
    # (section, its entries, the first story in it: what renaming it changes)
    groups: list[tuple[Optional[str], list[str], str]] = []
    for i, entry in enumerate(entries):
        html = _toc_entry(entry, contents, feature=layout == "feature" and i == 0, edit=edit)
        section = entry.get("section")
        if groups and groups[-1][0] == section:
            groups[-1][1].append(html)
        else:
            groups.append((section, [html], str(entry["post"]["id"])))
    # A section's heading is kept on the page with its first row of entries.
    row = 2 if layout == "grid" else 1
    def sec_head(sec: str, first: str) -> str:
        words = field(f"issue:section:{first}", ph="Section") if edit else ""
        return f'<h3 class="mz-contents__sec"{words}>{escape(sec)}</h3>'

    body = "".join(
        '<div class="mz-contents__group">'
        + (f'<div class="mz-contents__keep">{sec_head(sec, first)}{"".join(items[:row])}</div>'
           + "".join(items[row:]) if sec else "".join(items))
        + "</div>"
        for sec, items, first in groups
    )
    heading = contents.get("heading") or ""
    accent = _colour(contents.get("accent") or "accent")
    cls = f"mz-contents mz-contents--{escape(layout)}" + ("" if contents.get("show_numbers", True) else " mz-contents--nonum")
    if edit:
        head = f'<h2 class="mz-contents__heading"{field("issue:contents.heading", ph="Heading")}>{escape(heading)}</h2>'
    else:
        head = f'<h2 class="mz-contents__heading">{escape(heading)}</h2>' if heading else ""
    return (f'<section class="{cls}" style="--mz-c:{accent}"{" data-mz-contents" if edit else ""}>'
            f'<p class="mz-contents__issue">{escape(label)}</p>{head}{body}</section>')

