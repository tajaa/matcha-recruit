"""PDF / cover-image generation for offer letters + presentations."""
import asyncio
import html
import logging
import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.database import get_connection
from app.core.services.storage import get_storage

from ._coerce import _parse_date_str
from ._storage import (
    build_matcha_work_thread_storage_prefix,
    _should_enforce_company_scoped_matcha_work_storage,
    _storage_path_has_prefix,
)

logger = logging.getLogger(__name__)


async def _get_cached_pdf_url(
    thread_id: UUID,
    version: int,
    is_draft: bool,
    expected_prefix: Optional[str] = None,
) -> Optional[str]:
    async with get_connection() as conn:
        pdf_url = await conn.fetchval(
            """
            SELECT pdf_url
            FROM mw_pdf_cache
            WHERE thread_id=$1 AND version=$2 AND is_draft=$3
            """,
            thread_id,
            version,
            is_draft,
        )
    if expected_prefix and _should_enforce_company_scoped_matcha_work_storage():
        if not _storage_path_has_prefix(pdf_url, expected_prefix):
            return None
    return pdf_url


async def _cache_pdf_url(
    thread_id: UUID, version: int, pdf_url: str, is_draft: bool = True
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO mw_pdf_cache(thread_id, version, pdf_url, is_draft)
            VALUES($1, $2, $3, $4)
            ON CONFLICT(thread_id, version, is_draft) DO UPDATE
            SET pdf_url=EXCLUDED.pdf_url
            """,
            thread_id,
            version,
            pdf_url,
            is_draft,
        )


async def generate_pdf(
    state: dict,
    thread_id: UUID,
    version: int,
    company_id: UUID,
    is_draft: bool = True,
    logo_src: Optional[str] = None,
) -> Optional[str]:
    """Check cache → render HTML → WeasyPrint → S3 → cache URL."""
    expected_prefix = build_matcha_work_thread_storage_prefix(company_id, thread_id, "pdfs")
    cached = await _get_cached_pdf_url(thread_id, version, is_draft, expected_prefix=expected_prefix)
    if cached:
        return cached

    # Lazy import to avoid circular imports at module load time
    from app.matcha.routes.employee_lifecycle.offer_letters import _generate_offer_letter_html

    render_state = dict(state)
    render_state.setdefault("created_at", datetime.utcnow())

    # Convert date strings to datetime objects for the HTML template
    for date_field in ("start_date", "expiration_date"):
        val = render_state.get(date_field)
        if isinstance(val, str):
            parsed = _parse_date_str(val)
            render_state[date_field] = parsed  # None if unparseable → shows "TBD"

    def _render_pdf() -> Optional[bytes]:
        try:
            html_content = _generate_offer_letter_html(render_state, logo_src=logo_src)
            if is_draft:
                watermark_css = """
                body::before {
                    content: 'DRAFT';
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%) rotate(-45deg);
                    font-size: 120pt;
                    color: rgba(200, 200, 200, 0.3);
                    font-weight: bold;
                    z-index: -1;
                    pointer-events: none;
                }
                """
                html_content = html_content.replace("</style>", watermark_css + "</style>")
            from app.core.services.pdf import render_pdf

            return render_pdf(html_content)
        except ImportError:
            logger.error("WeasyPrint not installed — PDF generation skipped")
            return None
        except Exception as e:
            logger.error("PDF generation failed: %s", e, exc_info=True)
            return None

    pdf_bytes = await asyncio.to_thread(_render_pdf)
    if pdf_bytes is None:
        return None

    filename = f"v{version}{'_draft' if is_draft else '_final'}.pdf"
    try:
        pdf_url = await get_storage().upload_file(
            pdf_bytes,
            filename,
            prefix=expected_prefix,
            content_type="application/pdf",
        )
    except Exception as e:
        logger.error("Failed to upload PDF to storage: %s", e, exc_info=True)
        return None

    await _cache_pdf_url(thread_id, version, pdf_url, is_draft=is_draft)
    return pdf_url


def _render_presentation_html(state: dict) -> str:
    """Build HTML for a presentation PDF (slides → printable pages)."""
    title = html.escape(str(state.get("presentation_title") or "Presentation"))
    subtitle = html.escape(str(state.get("subtitle") or ""))
    theme = str(state.get("theme") or "professional").lower()
    slides = state.get("slides") or []

    # Theme-based color palette
    themes = {
        "professional": {"bg": "#1a1a2e", "accent": "#4ade80", "text": "#f1f5f9", "slide_bg": "#16213e"},
        "minimal": {"bg": "#ffffff", "accent": "#334155", "text": "#0f172a", "slide_bg": "#f8fafc"},
        "bold": {"bg": "#0f172a", "accent": "#f59e0b", "text": "#f8fafc", "slide_bg": "#1e293b"},
    }
    colors = themes.get(theme, themes["professional"])

    cover_image_url = state.get("cover_image_url")
    slides_html = []
    # Cover slide
    subtitle_html = f"<p class='subtitle'>{subtitle}</p>" if subtitle else ""
    cover_img_html = f"<img src='{html.escape(cover_image_url)}' class='cover-img' />" if cover_image_url else ""
    slides_html.append(f"""
        <div class="slide cover-slide">
          {cover_img_html}
          <div class="cover-content">
            <h1 class="cover-title">{title}</h1>
            {subtitle_html}
          </div>
        </div>""")

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_title = html.escape(str(slide.get("title") or ""))
        bullets = slide.get("bullets") or []
        if not slide_title and not bullets:
            continue
        bullets_html = "".join(
            f"<li>{html.escape(str(b))}</li>"
            for b in bullets
            if str(b).strip()
        )
        slides_html.append(f"""
        <div class="slide content-slide">
          <h2 class="slide-title">{slide_title}</h2>
          <ul class="bullets">{bullets_html}</ul>
        </div>""")

    slides_block = "\n".join(slides_html)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: 1280px 720px; margin: 0; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: {colors['bg']}; color: {colors['text']}; }}
  .slide {{
    width: 1280px; height: 720px;
    display: flex; flex-direction: column; justify-content: center;
    padding: 60px 80px;
    page-break-after: always;
    background: {colors['slide_bg']};
    border-top: 6px solid {colors['accent']};
  }}
  .cover-slide {{
    background: {colors['bg']};
    border-top: none;
    align-items: flex-start;
    border-left: 8px solid {colors['accent']};
    padding-left: 72px;
    position: relative;
    overflow: hidden;
  }}
  .cover-img {{
    position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    object-fit: cover; opacity: 0.25;
  }}
  .cover-content {{ max-width: 800px; position: relative; z-index: 1; }}
  .cover-title {{
    font-size: 52px; font-weight: 800; line-height: 1.15;
    color: {colors['text']}; margin-bottom: 20px; letter-spacing: -1px;
  }}
  .subtitle {{
    font-size: 24px; color: {colors['accent']}; font-weight: 500;
  }}
  .slide-title {{
    font-size: 34px; font-weight: 700; color: {colors['accent']};
    margin-bottom: 32px; letter-spacing: -0.5px;
  }}
  .bullets {{
    list-style: none; padding: 0;
  }}
  .bullets li {{
    font-size: 22px; line-height: 1.5; padding: 8px 0 8px 28px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    position: relative;
  }}
  .bullets li:last-child {{ border-bottom: none; }}
  .bullets li::before {{
    content: '▸';
    position: absolute; left: 0;
    color: {colors['accent']}; font-size: 16px;
  }}
</style>
</head>
<body>
{slides_block}
</body>
</html>"""


async def generate_presentation_pdf(
    state: dict,
    thread_id: UUID,
    version: int,
    company_id: UUID,
) -> Optional[str]:
    """Render presentation slides to PDF via WeasyPrint and upload to S3."""
    expected_prefix = build_matcha_work_thread_storage_prefix(company_id, thread_id, "presentation-pdfs")
    cached = await _get_cached_pdf_url(thread_id, version, is_draft=False, expected_prefix=expected_prefix)
    if cached:
        return cached

    # Inline the storage-owned cover image to a `data:` URI BEFORE the render
    # thread — the SSRF-safe fetcher blocks raw storage URLs, so the cover would
    # otherwise silently drop. Inlining returns None for external/failed URLs,
    # in which case the cover is omitted gracefully (None falls back to the
    # original value so a data:/non-storage URL is left as-is for the fetcher).
    render_state = state
    cover_url = state.get("cover_image_url")
    if cover_url:
        inlined_cover = await get_storage().inline_image_data_uri(cover_url)
        render_state = dict(state)
        render_state["cover_image_url"] = inlined_cover  # None → cover omitted

    def _render() -> Optional[bytes]:
        try:
            from weasyprint import CSS
            from app.core.services.pdf import render_pdf
            html_content = _render_presentation_html(render_state)
            return render_pdf(
                html_content,
                stylesheets=[CSS(string="@page { size: 1280px 720px; margin: 0; }")],
            )
        except ImportError:
            logger.error("WeasyPrint not installed — presentation PDF skipped")
            return None
        except Exception as e:
            logger.error("Presentation PDF render failed: %s", e, exc_info=True)
            return None

    pdf_bytes = await asyncio.to_thread(_render)
    if pdf_bytes is None:
        return None

    filename = f"presentation_v{version}.pdf"
    try:
        pdf_url = await get_storage().upload_file(
            pdf_bytes,
            filename,
            prefix=expected_prefix,
            content_type="application/pdf",
        )
    except Exception as e:
        logger.error("Failed to upload presentation PDF: %s", e, exc_info=True)
        return None

    await _cache_pdf_url(thread_id, version, pdf_url, is_draft=False)
    return pdf_url


async def generate_cover_image(
    presentation_title: str,
    subtitle: Optional[str] = None,
    *,
    company_id: UUID,
    thread_id: UUID,
) -> Optional[str]:
    """Generate a cover image via Gemini 3.1 Flash Image and upload to S3."""
    import os
    try:
        from app.core.services.genai_client import get_genai_client
        from google.genai import types as _genai_types
        from app.config import get_settings
        settings = get_settings()
        api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        if not api_key:
            return None
        client = get_genai_client(api_key=api_key)
        prompt_parts = [f"Professional corporate presentation cover slide illustration for: {presentation_title}"]
        if subtitle:
            prompt_parts.append(f"Subtitle: {subtitle}")
        prompt_parts.append("Clean, modern, abstract data visualization, dark background with green accents, no text, high quality, 16:9 aspect ratio")
        prompt = ". ".join(prompt_parts)

        def _call() -> Optional[tuple[bytes, str]]:
            try:
                response = client.models.generate_content(
                    # GA name — Google shut the preview model down 2026-06-25.
                    # Matches core.services.image_gen.IMAGE_MODEL.
                    model="gemini-3.1-flash-image",
                    contents=prompt,
                    config=_genai_types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                        image_config=_genai_types.ImageConfig(aspect_ratio="16:9"),
                    ),
                )
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        mime = part.inline_data.mime_type or "image/png"
                        return part.inline_data.data, mime
            except Exception as e:
                logger.warning("Gemini image generation call failed: %s", e)
            return None

        result = await asyncio.to_thread(_call)
        if result is None:
            return None

        image_bytes, mime_type = result
        ext = "png" if "png" in mime_type else "jpg"
        filename = f"cover_{secrets.token_hex(8)}.{ext}"
        prefix = build_matcha_work_thread_storage_prefix(company_id, thread_id, "covers")
        url = await get_storage().upload_file(
            image_bytes,
            filename,
            prefix=prefix,
            content_type=mime_type,
        )
        return url
    except Exception as e:
        logger.warning("Cover image generation failed: %s", e)
        return None
