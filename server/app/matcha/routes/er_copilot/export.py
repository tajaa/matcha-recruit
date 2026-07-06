"""Case export + share links (authed) and public share-link download."""
import base64
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from io import BytesIO

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ....core.services.storage import get_storage
from ....core.services.auth import hash_password, verify_password_async
from ...services.er_export import extract_analysis_export_text

from ._shared import (
    logger,
    _verify_case_company,
)

router = APIRouter()

public_router = APIRouter()

class ExportCaseFileRequest(BaseModel):
    password: str = Field(..., min_length=4, max_length=128)


class CreateShareLinkRequest(BaseModel):
    password: str = Field(..., min_length=4, max_length=128)
    expires_in_days: Optional[int] = Field(None, ge=0, le=365)


class ShareLinkResponse(BaseModel):
    token: str
    url: str
    expires_at: Optional[datetime] = None
    created_at: datetime


class ShareLinkListItem(BaseModel):
    id: str
    token: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    download_count: int
    last_downloaded_at: Optional[datetime] = None
    filename: str


class ShareLinkDownloadRequest(BaseModel):
    password: str


class ShareLinkInfoResponse(BaseModel):
    filename: str
    created_at: datetime
    expired: bool


async def _generate_case_pdf(case_id: UUID, company_id: UUID, is_admin: bool, password: str) -> tuple[bytes, str]:
    """Generate encrypted PDF for case. Returns (pdf_bytes, filename)."""
    try:
        async with get_connection() as conn:
            await _verify_case_company(conn, case_id, company_id, is_admin)

            case_row = await conn.fetchrow(
                "SELECT * FROM er_cases WHERE id = $1", case_id
            )
            if not case_row:
                raise HTTPException(status_code=404, detail="Case not found")

            doc_rows = await conn.fetch(
                "SELECT filename, document_type, file_size, file_path, mime_type, original_text, created_at FROM er_case_documents WHERE case_id = $1 ORDER BY created_at",
                case_id,
            )

            analysis_rows = await conn.fetch(
                "SELECT analysis_type, analysis_data, generated_at FROM er_case_analysis WHERE case_id = $1 ORDER BY generated_at",
                case_id,
            )

            note_rows = await conn.fetch(
                "SELECT note_type, content, created_at FROM er_case_notes WHERE case_id = $1 ORDER BY created_at",
                case_id,
            )

        import html as html_mod

        def esc(val: str) -> str:
            return html_mod.escape(str(val)) if val else ""

        case_title = esc(case_row["title"] or "Untitled Case")
        case_number = esc(case_row["case_number"])
        status = esc(case_row["status"])
        category = esc(case_row.get("category") or "\u2014")
        outcome = esc(case_row.get("outcome") or "\u2014")
        description = esc(case_row["description"] or "No description provided.")
        created_at = case_row["created_at"].strftime("%Y-%m-%d %H:%M") if case_row["created_at"] else "\u2014"
        closed_at = case_row["closed_at"].strftime("%Y-%m-%d %H:%M") if case_row.get("closed_at") else "\u2014"

        # Classify attachments for embedding in the export
        IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}
        TEXT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".csv", ".json"}
        SKIP_MIMES = {"video/", "audio/"}

        docs_html = ""
        attachment_pdfs: list[bytes] = []  # raw PDF bytes to append after the report

        if doc_rows:
            storage = get_storage()
            rows_html = "".join(
                f"<tr><td>{esc(r['filename'])}</td><td>{esc(r['document_type'])}</td><td>{(r['file_size'] or 0) // 1024} KB</td><td>{r['created_at'].strftime('%Y-%m-%d')}</td></tr>"
                for r in doc_rows
            )
            docs_html = f"<h2>Documents ({len(doc_rows)})</h2><table><tr><th>Filename</th><th>Type</th><th>Size</th><th>Uploaded</th></tr>{rows_html}</table>"

            for r in doc_rows:
                mime = (r["mime_type"] or "").lower()
                fname = r["filename"] or ""
                ext = os.path.splitext(fname)[1].lower()

                # Skip video/audio
                if any(mime.startswith(s) for s in SKIP_MIMES):
                    continue

                # Images: download and embed as base64
                if mime in IMAGE_MIMES and r["file_path"]:
                    try:
                        img_bytes = await storage.download_file(r["file_path"])
                        b64 = base64.b64encode(img_bytes).decode("ascii")
                        docs_html += (
                            f'<h3>{esc(fname)}</h3>'
                            f'<img src="data:{mime};base64,{b64}" '
                            f'style="max-width:100%;max-height:600px;margin:8px 0;" />'
                        )
                    except Exception as img_exc:
                        logger.warning("Could not embed image %s in export: %s", fname, img_exc)
                    continue

                # PDF attachments: append original pages (preserves formatting)
                if ext == ".pdf" and r["file_path"]:
                    try:
                        pdf_attachment = await storage.download_file(r["file_path"])
                        attachment_pdfs.append(pdf_attachment)
                        docs_html += f'<h3>{esc(fname)}</h3><p style="color:#666;font-size:10px;">(Original PDF attached at end of export)</p>'
                    except Exception as pdf_exc:
                        logger.warning("Could not fetch PDF attachment %s for export: %s", fname, pdf_exc)
                    continue

                # Other text-extractable files: include extracted text
                if ext in TEXT_EXTENSIONS:
                    text_content = r.get("original_text") or ""
                    if text_content:
                        if len(text_content) > 20000:
                            text_content = text_content[:20000] + "\n\n[... truncated ...]"
                        docs_html += f'<h3>{esc(fname)}</h3><pre style="white-space:pre-wrap;font-size:10px;background:#f9f9f9;padding:12px;border:1px solid #eee;max-height:800px;overflow:hidden;">{esc(text_content)}</pre>'


        analyses_html = ""
        for a in analysis_rows:
            if a["analysis_type"] == "similar_cases":
                continue
            atype = esc((a["analysis_type"] or "unknown").replace("_", " ").title())
            result = a["analysis_data"]
            summary = extract_analysis_export_text(result)
            analyses_html += f"<h3>{atype}</h3><div class='analysis-text'>{esc(summary)}</div>"
        if analyses_html:
            analyses_html = f"<h2>Analyses</h2>{analyses_html}"

        notes_html = ""
        if note_rows:
            items = "".join(
                f"<div class='note'><span class='note-type'>{esc(r['note_type'])}</span> <span class='note-date'>{r['created_at'].strftime('%Y-%m-%d %H:%M')}</span><p>{esc(r['content'])}</p></div>"
                for r in note_rows
            )
            notes_html = f"<h2>Case Notes ({len(note_rows)})</h2>{items}"
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Export failed for case %s during data/HTML phase: %s", case_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export preparation failed: {exc}")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; color: #1a1a1a; font-size: 12px; line-height: 1.6; }}
h1 {{ font-size: 20px; margin-bottom: 4px; }}
h2 {{ font-size: 14px; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 28px; text-transform: uppercase; letter-spacing: 1px; color: #555; }}
h3 {{ font-size: 12px; margin-top: 16px; color: #333; }}
.meta {{ color: #666; font-size: 11px; margin-bottom: 20px; }}
.meta span {{ display: inline-block; margin-right: 20px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin: 12px 0; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
th {{ background: #f5f5f5; font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px; }}
.note {{ border-left: 3px solid #ddd; padding: 8px 12px; margin: 8px 0; background: #fafafa; }}
.note-type {{ font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px; }}
.note-date {{ color: #999; font-size: 10px; margin-left: 8px; }}
.analysis-text {{ white-space: pre-wrap; }}
.footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 12px; color: #999; font-size: 10px; text-align: center; }}
</style></head><body>
<h1>{case_title}</h1>
<div class="meta">
  <span><strong>Case:</strong> {case_number}</span>
  <span><strong>Status:</strong> {status}</span>
  <span><strong>Category:</strong> {category}</span>
  <span><strong>Outcome:</strong> {outcome}</span>
  <span><strong>Created:</strong> {created_at}</span>
  <span><strong>Closed:</strong> {closed_at}</span>
</div>
<h2>Description</h2>
<p>{description}</p>
{docs_html}
{analyses_html}
{notes_html}
<div class="footer">Confidential — ER Case Export — Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
</body></html>"""

    try:
        from weasyprint import HTML as WeasyHTML
        from ....core.services.pdf import safe_url_fetcher
        pdf_bytes = WeasyHTML(string=html, url_fetcher=safe_url_fetcher).write_pdf()
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF generation not available (WeasyPrint not installed)")
    except Exception as exc:
        logger.error("PDF generation failed for case %s: %s", case_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        # Append original PDF attachments after the report pages
        for att_bytes in attachment_pdfs:
            try:
                att_reader = PdfReader(BytesIO(att_bytes))
                for page in att_reader.pages:
                    writer.add_page(page)
            except Exception as att_exc:
                logger.warning("Skipping unreadable PDF attachment in export: %s", att_exc)

        writer.encrypt(password)

        output = BytesIO()
        writer.write(output)
        output.seek(0)
        encrypted_bytes = output.read()
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF encryption not available (pypdf not installed)")
    except Exception as exc:
        logger.error("PDF encryption failed for case %s: %s", case_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF encryption failed: {exc}")

    filename = f"ER-Case-{case_number}.pdf"
    return encrypted_bytes, filename


@router.post("/{case_id}/export")
async def export_case_file(
    case_id: UUID,
    body: ExportCaseFileRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Export a case as a password-protected PDF."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")
    is_admin = current_user.role == "admin"
    pdf_bytes, filename = await _generate_case_pdf(case_id, company_id, is_admin, body.password)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{case_id}/export/share", response_model=ShareLinkResponse)
async def create_share_link(
    case_id: UUID,
    body: CreateShareLinkRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a shareable download link for a case export."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")
    is_admin = current_user.role == "admin"

    pdf_bytes, filename = await _generate_case_pdf(case_id, company_id, is_admin, body.password)

    try:
        storage = get_storage()
        # Private bucket: ER exports are confidential. The download is served only
        # via the password+lockout-gated /shared/er-export/{token}/download stream,
        # never a public CloudFront URL.
        storage_path = await storage.upload_private_file(pdf_bytes, filename, prefix="er-exports", content_type="application/pdf")
    except Exception as exc:
        logger.error("Failed to upload share link PDF for case %s: %s", case_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to store export file") from exc

    token = secrets.token_urlsafe(32)
    pw_hash = hash_password(body.password)

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO er_case_export_links
                    (case_id, org_id, token, password_hash, storage_path, filename, created_by, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, created_at
                """,
                case_id, company_id, token, pw_hash, storage_path, filename, current_user.id, expires_at,
            )
    except Exception as exc:
        logger.error("Failed to create share link record for case %s: %s", case_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create share link") from exc

    url = f"/s/{token}"

    return ShareLinkResponse(
        token=token,
        url=url,
        expires_at=expires_at,
        created_at=row["created_at"],
    )


@router.get("/{case_id}/export/links", response_model=list[ShareLinkListItem])
async def list_share_links(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List share links for a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")
    is_admin = current_user.role == "admin"

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, is_admin)
        rows = await conn.fetch(
            """
            SELECT id, token, created_at, expires_at, revoked_at, download_count, last_downloaded_at, filename
            FROM er_case_export_links
            WHERE case_id = $1
            ORDER BY created_at DESC
            """,
            case_id,
        )

    return [
        ShareLinkListItem(
            id=str(r["id"]),
            token=r["token"],
            created_at=r["created_at"],
            expires_at=r["expires_at"],
            revoked_at=r["revoked_at"],
            download_count=r["download_count"],
            last_downloaded_at=r["last_downloaded_at"],
            filename=r["filename"],
        )
        for r in rows
    ]


@router.delete("/{case_id}/export/links/{link_id}")
async def revoke_share_link(
    case_id: UUID,
    link_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Revoke a share link and delete its S3 file."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")
    is_admin = current_user.role == "admin"

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, is_admin)
        row = await conn.fetchrow(
            "SELECT storage_path FROM er_case_export_links WHERE id = $1 AND case_id = $2",
            link_id, case_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Link not found")

        await conn.execute(
            "UPDATE er_case_export_links SET revoked_at = now() WHERE id = $1",
            link_id,
        )

    storage = get_storage()
    try:
        await storage.delete_file(row["storage_path"])
    except Exception:
        logger.warning("Failed to delete S3 file for revoked link %s", link_id)

    return {"status": "revoked"}


# ===========================================
# Public Share Link Endpoints
# ===========================================

@public_router.get("/{token}/info", response_model=ShareLinkInfoResponse)
async def share_link_info(token: str):
    """Get info about a share link (public, no auth)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT filename, created_at, expires_at, revoked_at FROM er_case_export_links WHERE token = $1",
            token,
        )
    if not row or row["revoked_at"] is not None:
        raise HTTPException(status_code=404, detail="Link not found")

    expired = row["expires_at"] is not None and row["expires_at"] < datetime.now(timezone.utc)
    return ShareLinkInfoResponse(
        filename=row["filename"],
        created_at=row["created_at"],
        expired=expired,
    )


@public_router.post("/{token}/download")
async def share_link_download(token: str, body: ShareLinkDownloadRequest):
    """Download a shared export (public, password-protected)."""
    lockout_minutes = 15
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, password_hash, storage_path, filename, expires_at, revoked_at,
                   failed_attempts, last_failed_at
            FROM er_case_export_links WHERE token = $1
            """,
            token,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Link not found")
        if row["revoked_at"] is not None:
            raise HTTPException(status_code=404, detail="Link not found")
        if row["expires_at"] is not None and row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Link has expired")

        # Time-windowed lockout: reset counter if lockout period has elapsed
        failed = row["failed_attempts"]
        last_failed = row["last_failed_at"]
        if failed >= 5 and last_failed and last_failed > datetime.now(timezone.utc) - timedelta(minutes=lockout_minutes):
            raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {lockout_minutes} minutes.")
        if failed >= 5:
            # Lockout window expired — reset counter
            await conn.execute(
                "UPDATE er_case_export_links SET failed_attempts = 0, last_failed_at = NULL WHERE id = $1",
                row["id"],
            )

        valid = await verify_password_async(body.password, row["password_hash"])
        if not valid:
            await conn.execute(
                "UPDATE er_case_export_links SET failed_attempts = failed_attempts + 1, last_failed_at = now() WHERE id = $1",
                row["id"],
            )
            raise HTTPException(status_code=403, detail="Invalid password")

        await conn.execute(
            "UPDATE er_case_export_links SET download_count = download_count + 1, last_downloaded_at = now(), failed_attempts = 0, last_failed_at = NULL WHERE id = $1",
            row["id"],
        )

    storage = get_storage()
    file_bytes = await storage.download_file(row["storage_path"])

    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'},
    )


# ===========================================
# Case Notes
# ===========================================

