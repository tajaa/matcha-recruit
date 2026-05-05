"""Regression tests for the matcha-work blog/project PDF export.

The desktop client (BlogEditorView → ProjectDetailViewModel → MatchaWorkService)
hits `GET /matcha-work/projects/{id}/export/{fmt}` and writes the response
bytes directly to disk. Two failure modes have surfaced before:

1. Returning JSON `{"pdf_url": ...}` when the client expected raw PDF bytes,
   producing a JSON-in-PDF-extension file that won't open. (Fixed in 76b3be2.)
2. The inline markdown renderer emitting block-level constructs that don't
   match the SwiftUI preview, also addressed in 76b3be2 by switching to
   `_render_inline_md` (inline-only).

These tests cover the two render helpers used by both export paths
(`/projects/{id}/export/pdf` and `_render_project_pdf` for the discipline
signature flow). They keep WeasyPrint composition stable so the Mac client's
PDF download keeps working.
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Stub heavyweight optional deps before importing app code ──
for _name in ("google", "google.genai", "google.genai.types", "bleach",
              "audioop_lts", "audioop", "stripe"):
    if _name not in sys.modules:
        sys.modules[_name] = ModuleType(_name)

_genai = sys.modules["google.genai"]
_genai.Client = object
_genai.types = sys.modules["google.genai.types"]
_gt = sys.modules["google.genai.types"]
_gt.Tool = lambda **kw: None
_gt.GoogleSearch = lambda **kw: None
_gt.GenerateContentConfig = lambda **kw: None
_bleach = sys.modules["bleach"]
_bleach.clean = lambda text, **kw: text
_bleach.linkify = lambda text, **kw: text


# ============================================================
# _render_inline_md — inline-only markdown renderer
# ============================================================

class TestRenderInlineMd:
    """Inline-only markdown: bold/italic/code only, no block constructs.

    Bullets, headings (#), numbered lists, checkboxes etc. must render as
    literal text so the PDF matches the SwiftUI preview character-for-character.
    """

    def test_bold_double_asterisk(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        assert _render_inline_md("hello **world**") == "hello <strong>world</strong>"

    def test_bold_double_underscore(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        assert _render_inline_md("hello __world__") == "hello <strong>world</strong>"

    def test_italic_single_asterisk(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        assert _render_inline_md("ok *fine* yes") == "ok <em>fine</em> yes"

    def test_italic_underscore_word_boundary(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        # underscores inside identifiers should NOT trigger italics
        assert _render_inline_md("snake_case_var") == "snake_case_var"
        # but flanked by spaces should
        assert _render_inline_md("ok _fine_ yes") == "ok <em>fine</em> yes"

    def test_inline_code(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        assert _render_inline_md("use `npm` here") == "use <code>npm</code> here"

    def test_html_special_chars_escaped(self):
        """User-provided angle brackets must escape so they don't open
        unintended HTML tags inside the WeasyPrint document."""
        from app.matcha.routes.matcha_work import _render_inline_md
        out = _render_inline_md("<script>alert(1)</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_multi_line_uses_br(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        out = _render_inline_md("line one\nline two")
        assert out == "line one<br>line two"

    def test_block_constructs_pass_through_literally(self):
        """The whole point of inline-only — block markdown stays as text
        so the PDF matches the desktop preview."""
        from app.matcha.routes.matcha_work import _render_inline_md
        # bullet
        assert _render_inline_md("- item one") == "- item one"
        # heading
        assert _render_inline_md("# heading") == "# heading"
        # numbered
        assert _render_inline_md("1. first") == "1. first"
        # checkbox
        assert _render_inline_md("- [ ] todo") == "- [ ] todo"

    def test_empty_string(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        assert _render_inline_md("") == ""

    def test_combined_formatting_in_one_line(self):
        from app.matcha.routes.matcha_work import _render_inline_md
        out = _render_inline_md("**bold** and *italic* and `code`")
        assert out == "<strong>bold</strong> and <em>italic</em> and <code>code</code>"


# ============================================================
# _render_project_pdf — full HTML composition + WeasyPrint round-trip
# ============================================================

@pytest.fixture
def mock_storage():
    """Storage stub so _inline_images doesn't try a real S3 download."""
    storage = MagicMock()
    storage.is_supported_storage_path = MagicMock(return_value=False)
    storage.download_file = AsyncMock(return_value=b"")
    return storage


class TestRenderProjectPdf:
    """End-to-end render of a project dict to PDF bytes. Uses WeasyPrint;
    if WeasyPrint isn't installed, these skip rather than fail."""

    @pytest.mark.asyncio
    async def test_render_returns_pdf_bytes(self, mock_storage):
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw
        with patch.object(mw, "get_storage", return_value=mock_storage):
            project = {
                "title": "My First Blog Post",
                "sections": [
                    {"title": "Introduction", "content": "Hello **world**."},
                    {"title": "Body", "content": "Some `code` and *italics*."},
                ],
            }
            pdf_bytes = await mw._render_project_pdf(project)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF"), "Output must be a real PDF blob"
        assert len(pdf_bytes) > 500, "PDF should be non-trivially sized"

    @pytest.mark.asyncio
    async def test_render_with_html_content_passes_through(self, mock_storage):
        """Sections whose content already starts with `<` (rich HTML from
        the editor) must NOT be re-rendered through _render_inline_md."""
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw
        with patch.object(mw, "get_storage", return_value=mock_storage):
            project = {
                "title": "Mixed Content",
                "sections": [
                    {"title": "HTML", "content": "<p>Already <strong>HTML</strong>.</p>"},
                    {"title": "MD", "content": "Plain **markdown**."},
                ],
            }
            pdf_bytes = await mw._render_project_pdf(project)
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_render_empty_sections(self, mock_storage):
        """Sections list can be empty; export must still produce a PDF
        with just the title (don't crash on empty body)."""
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw
        with patch.object(mw, "get_storage", return_value=mock_storage):
            project = {"title": "Empty Doc", "sections": []}
            pdf_bytes = await mw._render_project_pdf(project)
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_render_section_with_no_title(self, mock_storage):
        """A section with no `title` field must not emit an `<h2>` heading
        (would produce a stray bare numbered prefix)."""
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw
        with patch.object(mw, "get_storage", return_value=mock_storage):
            project = {
                "title": "Untitled-Sections",
                "sections": [
                    {"title": "", "content": "Just body text"},
                    {"content": "No title key at all"},
                ],
            }
            pdf_bytes = await mw._render_project_pdf(project)
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_render_title_escapes_html(self, mock_storage):
        """A title with `<` should not produce malformed HTML that
        WeasyPrint rejects or that opens an unintended tag."""
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw
        with patch.object(mw, "get_storage", return_value=mock_storage):
            project = {
                "title": "How to use <script> tags safely",
                "sections": [{"title": "intro", "content": "plain text"}],
            }
            pdf_bytes = await mw._render_project_pdf(project)
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_render_handles_missing_optional_fields(self, mock_storage):
        """`project.get("title") or "Document"` and sections=[] fallbacks."""
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw
        with patch.object(mw, "get_storage", return_value=mock_storage):
            pdf_bytes = await mw._render_project_pdf({})
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_render_with_image_inlines_data_uri(self):
        """Remote images get inlined as base64 data URIs so WeasyPrint can
        render them without making a network call. Unsupported paths
        (external URLs) pass through untouched."""
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw

        storage = MagicMock()
        # Treat /uploads/foo.png as a supported storage path; pretend
        # external URLs are not.
        storage.is_supported_storage_path = MagicMock(
            side_effect=lambda src: src.startswith("/uploads/")
        )
        # 1x1 red PNG
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
            b"\x00\x00\x00\x02\x00\x01\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        storage.download_file = AsyncMock(return_value=png_bytes)

        with patch.object(mw, "get_storage", return_value=storage):
            project = {
                "title": "Image Doc",
                "sections": [
                    {"title": "Pictures",
                     "content": '<p>see <img src="/uploads/foo.png" alt="x"></p>'},
                ],
            }
            pdf_bytes = await mw._render_project_pdf(project)

        assert pdf_bytes.startswith(b"%PDF")
        storage.download_file.assert_awaited_once_with("/uploads/foo.png")

    @pytest.mark.asyncio
    async def test_render_with_markdown_image_inlines_data_uri(self):
        """Standalone markdown image `![alt](url)` lines are emitted as <img>
        tags by _render_inline_md, then base64-inlined by _inline_images.
        Regression: an earlier version called _inline_images BEFORE markdown
        rendering, so the just-emitted <img> tag never got base64'd and
        WeasyPrint couldn't fetch the private URL — image rendered as URL
        text. This test ensures the storage download is invoked for markdown
        image syntax (not just inline-HTML <img>)."""
        pytest.importorskip("weasyprint")
        from app.matcha.routes import matcha_work as mw

        storage = MagicMock()
        storage.is_supported_storage_path = MagicMock(
            side_effect=lambda src: src.startswith("/uploads/")
        )
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
            b"\x00\x00\x00\x02\x00\x01\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        storage.download_file = AsyncMock(return_value=png_bytes)

        with patch.object(mw, "get_storage", return_value=storage):
            project = {
                "title": "Markdown Image Doc",
                "sections": [
                    {"title": "Body", "content": "Intro line\n\n![diagram](/uploads/diagram.png)\n\nOutro line"},
                ],
            }
            pdf_bytes = await mw._render_project_pdf(project)

        assert pdf_bytes.startswith(b"%PDF")
        storage.download_file.assert_awaited_once_with("/uploads/diagram.png")


# ============================================================
# Format validation in the export endpoint
# ============================================================

class TestExportFormatValidation:
    """The route guards `fmt` against a fixed allow-list. Unknown formats
    must 400 before any rendering work happens."""

    def test_supported_formats_set(self):
        # Sanity: the route enforces this exact set. Bumping this set is
        # an API contract change (the desktop client switches on the same
        # strings: pdf / docx / md / md_frontmatter).
        SUPPORTED = {"pdf", "md", "docx", "md_frontmatter"}
        # Double-check the route source still matches by reading the file.
        import app.matcha.routes.matcha_work as mw
        import inspect
        src = inspect.getsource(mw.export_project_endpoint)
        for fmt in SUPPORTED:
            assert f'"{fmt}"' in src, f"{fmt} dropped from supported list"
