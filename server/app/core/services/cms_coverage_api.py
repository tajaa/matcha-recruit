"""CMS Coverage API client.

Fetches Medicare NCDs, LCDs, and associated billing articles with CPT/ICD
code mappings from the CMS Medicare Coverage Database API.

API docs: https://api.coverage.cms.gov/docs/swagger/index.html
No API key required. License agreement token needed for LCD/article endpoints.
"""

import html
import json
import re
from datetime import date, datetime
from typing import Optional
from uuid import UUID

import httpx

BASE_URL = "https://api.coverage.cms.gov"
REQUEST_TIMEOUT = 30.0


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities from CMS API response text."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(date_str: str) -> Optional[date]:
    """Parse MM/DD/YYYY date from CMS API."""
    if not date_str or date_str == "N/A":
        return None
    try:
        return datetime.strptime(date_str, "%m/%d/%Y").date()
    except ValueError:
        return None


class CMSCoverageAPI:
    """Client for the CMS Medicare Coverage Database API."""

    def __init__(self):
        self._token: Optional[str] = None

    async def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT))

    async def get_license_token(self) -> str:
        """Accept license agreement and get a 1-hour bearer token."""
        async with await self._get_client() as client:
            resp = await client.get(f"{BASE_URL}/v1/metadata/license-agreement/")
            resp.raise_for_status()
            data = resp.json()
            self._token = data["data"][0]["Token"]
            return self._token

    def _auth_headers(self) -> dict:
        if not self._token:
            raise RuntimeError("Call get_license_token() first")
        return {"Authorization": f"Bearer {self._token}"}

    async def _get(self, path: str, params: Optional[dict] = None, auth: bool = True) -> dict:
        """Make authenticated GET request to CMS API."""
        headers = self._auth_headers() if auth else {}
        async with await self._get_client() as client:
            resp = await client.get(f"{BASE_URL}{path}", params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _get_paginated(self, path: str, params: Optional[dict] = None) -> list[dict]:
        """Fetch all pages from a paginated CMS API endpoint."""
        all_data = []
        p = dict(params or {})
        p.setdefault("page_size", "100")
        while True:
            result = await self._get(path, params=p)
            all_data.extend(result.get("data", []))
            next_token = result.get("meta", {}).get("next_token", "")
            if not next_token:
                break
            p["next_token"] = next_token
        return all_data

    # ── NCD endpoints ──

    async def list_ncds(self) -> list[dict]:
        """List all National Coverage Determinations."""
        result = await self._get("/v1/reports/national-coverage-ncd/", auth=False)
        return result.get("data", [])

    async def get_ncd(self, ncd_id: int, version: int) -> dict:
        """Get full NCD detail with clinical criteria."""
        result = await self._get("/v1/data/ncd/", params={"ncdid": ncd_id, "ncdver": version})
        data = result.get("data", [])
        return data[0] if data else {}

    # ── LCD endpoints ──

    async def list_lcds(self, state: Optional[str] = None) -> list[dict]:
        """List all final Local Coverage Determinations."""
        params = {}
        if state:
            params["state"] = state
        result = await self._get("/v1/reports/local-coverage-final-lcds/", params=params, auth=False)
        return result.get("data", [])

    async def get_lcd(self, lcd_id: int, version: int) -> dict:
        """Get full LCD detail with clinical criteria."""
        result = await self._get("/v1/data/lcd/", params={"lcdid": lcd_id, "ver": version})
        data = result.get("data", [])
        return data[0] if data else {}

    async def get_lcd_related_documents(self, lcd_id: int, version: int) -> list[dict]:
        """Get articles and related LCDs for an LCD."""
        result = await self._get(
            "/v1/data/lcd/related-documents",
            params={"lcdid": lcd_id, "ver": version},
        )
        return result.get("data", [])

    # ── Article endpoints (billing/coding data) ──

    async def get_article_cpt_codes(self, article_id: int, version: int) -> list[dict]:
        """Get CPT/HCPCS codes for a billing article."""
        return await self._get_paginated(
            "/v1/data/article/hcpc-code",
            params={"articleid": article_id, "ver": version},
        )

    async def get_article_icd10_covered(self, article_id: int, version: int) -> list[dict]:
        """Get ICD-10 codes that support medical necessity."""
        return await self._get_paginated(
            "/v1/data/article/icd10-covered",
            params={"articleid": article_id, "ver": version},
        )

    async def get_article_icd10_noncovered(self, article_id: int, version: int) -> list[dict]:
        """Get ICD-10 codes that do NOT support medical necessity."""
        return await self._get_paginated(
            "/v1/data/article/icd10-noncovered",
            params={"articleid": article_id, "ver": version},
        )

    # ── High-level ingestion methods ──

    async def ingest_ncd(self, ncd_id: int, version: int, conn) -> Optional[dict]:
        """Fetch an NCD and store it as a payer_medical_policies row.

        Returns dict with policy data + _ingest_status ("new"/"updated"/"unchanged")
        and _changes (list of changed field names) on success, None on failure.
        """
        try:
            ncd = await self.get_ncd(ncd_id, version)
        except Exception as e:
            print(f"[CMS API] Failed to fetch NCD {ncd_id}: {e}")
            return None

        if not ncd:
            return None

        title = ncd.get("title", "")
        display_id = ncd.get("document_display_id", str(ncd_id))
        policy_number = f"NCD {display_id}"

        # Parse clinical criteria from HTML fields
        clinical_criteria = _strip_html(ncd.get("indications_limitations", ""))
        item_description = _strip_html(ncd.get("item_service_description", ""))
        reasons_for_denial = _strip_html(ncd.get("reasons_for_denial", ""))

        # Determine coverage status from content
        coverage_status = "covered"
        lower_criteria = clinical_criteria.lower()
        if "non-covered" in lower_criteria or "not covered" in lower_criteria:
            coverage_status = "conditional"

        effective = _parse_date(ncd.get("effective_date", ""))
        source_url = f"https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid={ncd_id}&ncdver={version}"

        # Check existing row for change detection
        existing = await conn.fetchrow(
            "SELECT clinical_criteria, coverage_status, cms_document_version FROM payer_medical_policies WHERE payer_name = 'Medicare' AND policy_number = $1",
            policy_number,
        )

        row = await conn.fetchrow(
            """
            INSERT INTO payer_medical_policies
                (payer_name, payer_type, policy_number, policy_title,
                 procedure_description, coverage_status,
                 clinical_criteria, documentation_requirements,
                 medical_necessity_criteria,
                 effective_date, source_url, source_document,
                 research_source, cms_document_id, cms_document_type, cms_document_version,
                 metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17::jsonb)
            ON CONFLICT (payer_name, policy_number) DO UPDATE SET
                policy_title = EXCLUDED.policy_title,
                coverage_status = EXCLUDED.coverage_status,
                clinical_criteria = EXCLUDED.clinical_criteria,
                documentation_requirements = EXCLUDED.documentation_requirements,
                medical_necessity_criteria = EXCLUDED.medical_necessity_criteria,
                effective_date = EXCLUDED.effective_date,
                source_url = EXCLUDED.source_url,
                cms_document_version = EXCLUDED.cms_document_version,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id, payer_name, policy_number, policy_title
            """,
            "Medicare",
            "government",
            policy_number,
            title,
            item_description[:500] if item_description else title,
            coverage_status,
            clinical_criteria,
            None,
            clinical_criteria[:2000] if clinical_criteria else None,
            effective,
            source_url,
            f"NCD {display_id}",
            "cms_api",
            ncd_id,
            "ncd",
            version,
            json.dumps({
                "benefit_category": ncd.get("benefit_category", ""),
                "transmittal_number": ncd.get("transmittal_number", ""),
            }),
        )

        if not row:
            return None

        result = dict(row)

        # Detect changes
        if not existing:
            result["_ingest_status"] = "new"
            result["_changes"] = []
        else:
            changes = []
            if (existing["clinical_criteria"] or "") != (clinical_criteria or ""):
                changes.append("clinical_criteria")
            if (existing["coverage_status"] or "") != coverage_status:
                changes.append("coverage_status")
            if existing["cms_document_version"] != version:
                changes.append("cms_document_version")
            result["_ingest_status"] = "updated" if changes else "unchanged"
            result["_changes"] = changes

        return result

    async def ingest_lcd_with_codes(self, lcd_id: int, version: int, conn) -> Optional[dict]:
        """Fetch an LCD, its related articles, CPT/ICD codes, and store as a policy row.

        Returns dict with policy data + _ingest_status and _changes on success, None on failure.
        """
        try:
            lcd = await self.get_lcd(lcd_id, version)
        except Exception as e:
            print(f"[CMS API] Failed to fetch LCD {lcd_id}: {e}")
            return None

        if not lcd:
            return None

        title = lcd.get("title", "")
        display_id = lcd.get("display_id", str(lcd_id))
        policy_number = f"LCD {display_id}"

        # Parse clinical criteria
        clinical_criteria = _strip_html(lcd.get("indication", ""))
        doc_reqs = _strip_html(lcd.get("doc_reqs", ""))
        coding_guidelines = _strip_html(lcd.get("coding_guidelines", ""))

        # Fetch CPT and ICD codes from related articles
        procedure_codes: list[str] = []
        diagnosis_codes: list[str] = []

        try:
            related_docs = await self.get_lcd_related_documents(lcd_id, version)
            for doc in related_docs:
                article_id = doc.get("r_article_id")
                article_ver = doc.get("r_article_version")
                if not article_id or not article_ver:
                    continue

                try:
                    cpt_data = await self.get_article_cpt_codes(article_id, article_ver)
                    for code in cpt_data:
                        code_id = code.get("hcpc_code_id", "")
                        if code_id and code_id not in procedure_codes:
                            procedure_codes.append(code_id)

                    icd_data = await self.get_article_icd10_covered(article_id, article_ver)
                    for code in icd_data:
                        code_id = code.get("icd10_code_id", "")
                        if code_id and code_id not in diagnosis_codes:
                            diagnosis_codes.append(code_id)
                except Exception as e:
                    print(f"[CMS API] Failed to fetch codes for article {article_id}: {e}")
        except Exception as e:
            print(f"[CMS API] Failed to fetch related docs for LCD {lcd_id}: {e}")

        # Determine coverage status
        coverage_status = "conditional"
        if clinical_criteria:
            lower = clinical_criteria.lower()
            if "not covered" in lower or "non-covered" in lower:
                coverage_status = "not_covered"
            elif "covered" in lower and "not covered" not in lower:
                coverage_status = "covered"

        effective = _parse_date(lcd.get("rev_eff_date", "") or lcd.get("orig_det_eff_date", ""))
        last_reviewed = _parse_date(lcd.get("last_reviewed_on", ""))
        source_url = f"https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid={lcd_id}&ver={version}"

        # Check existing row for change detection
        existing = await conn.fetchrow(
            "SELECT clinical_criteria, coverage_status, cms_document_version FROM payer_medical_policies WHERE payer_name = 'Medicare' AND policy_number = $1",
            policy_number,
        )

        row = await conn.fetchrow(
            """
            INSERT INTO payer_medical_policies
                (payer_name, payer_type, policy_number, policy_title,
                 procedure_codes, diagnosis_codes, procedure_description,
                 coverage_status, clinical_criteria,
                 documentation_requirements, medical_necessity_criteria,
                 effective_date, last_reviewed, source_url, source_document,
                 research_source, cms_document_id, cms_document_type, cms_document_version,
                 metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20::jsonb)
            ON CONFLICT (payer_name, policy_number) DO UPDATE SET
                policy_title = EXCLUDED.policy_title,
                procedure_codes = EXCLUDED.procedure_codes,
                diagnosis_codes = EXCLUDED.diagnosis_codes,
                coverage_status = EXCLUDED.coverage_status,
                clinical_criteria = EXCLUDED.clinical_criteria,
                documentation_requirements = EXCLUDED.documentation_requirements,
                medical_necessity_criteria = EXCLUDED.medical_necessity_criteria,
                effective_date = EXCLUDED.effective_date,
                last_reviewed = EXCLUDED.last_reviewed,
                source_url = EXCLUDED.source_url,
                cms_document_version = EXCLUDED.cms_document_version,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id, payer_name, policy_number, policy_title
            """,
            "Medicare",
            "government",
            policy_number,
            title,
            procedure_codes or None,
            diagnosis_codes[:500] if diagnosis_codes else None,  # Cap ICD codes at 500
            title,  # procedure_description = title for LCDs
            coverage_status,
            clinical_criteria,
            doc_reqs or None,
            coding_guidelines or None,
            effective,
            last_reviewed,
            source_url,
            f"LCD {display_id}",
            "cms_api",
            lcd_id,
            "lcd",
            version,
            json.dumps({
                "cpt_code_count": len(procedure_codes),
                "icd10_code_count": len(diagnosis_codes),
                "keywords": lcd.get("keywords", ""),
            }),
        )

        if not row:
            return None

        result = dict(row)
        if not existing:
            result["_ingest_status"] = "new"
            result["_changes"] = []
        else:
            changes = []
            if (existing["clinical_criteria"] or "") != (clinical_criteria or ""):
                changes.append("clinical_criteria")
            if (existing["coverage_status"] or "") != coverage_status:
                changes.append("coverage_status")
            if existing["cms_document_version"] != version:
                changes.append("cms_document_version")
            result["_ingest_status"] = "updated" if changes else "unchanged"
            result["_changes"] = changes

        return result

    async def ingest_all_ncds(self, conn) -> dict:
        """Ingest all NCDs from CMS API. Returns summary with change detection."""
        ncds = await self.list_ncds()
        summary = {"total": 0, "new": 0, "updated": 0, "unchanged": 0, "failed": 0, "changes": []}
        for i, ncd in enumerate(ncds):
            result = await self.ingest_ncd(
                ncd["document_id"], ncd["document_version"], conn
            )
            if result:
                summary["total"] += 1
                status = result.get("_ingest_status", "new")
                summary[status] = summary.get(status, 0) + 1
                if status == "updated":
                    summary["changes"].append({
                        "policy_number": result["policy_number"],
                        "policy_title": result["policy_title"],
                        "fields_changed": result.get("_changes", []),
                    })
                if summary["total"] % 50 == 0:
                    print(f"[CMS API] Ingested {summary['total']}/{len(ncds)} NCDs")
            else:
                summary["failed"] += 1
        print(f"[CMS API] NCDs: {summary['total']} total ({summary['new']} new, {summary['updated']} updated, {summary['unchanged']} unchanged)")
        return summary

    async def ingest_all_lcds(self, conn, state: Optional[str] = None) -> dict:
        """Ingest all final LCDs from CMS API. Returns summary with change detection."""
        lcds = await self.list_lcds(state=state)
        summary = {"total": 0, "new": 0, "updated": 0, "unchanged": 0, "failed": 0, "changes": []}
        for i, lcd in enumerate(lcds):
            result = await self.ingest_lcd_with_codes(
                lcd["document_id"], lcd["document_version"], conn
            )
            if result:
                summary["total"] += 1
                status = result.get("_ingest_status", "new")
                summary[status] = summary.get(status, 0) + 1
                if status == "updated":
                    summary["changes"].append({
                        "policy_number": result["policy_number"],
                        "policy_title": result["policy_title"],
                        "fields_changed": result.get("_changes", []),
                    })
                if summary["total"] % 50 == 0:
                    print(f"[CMS API] Ingested {summary['total']}/{len(lcds)} LCDs")
            else:
                summary["failed"] += 1
        print(f"[CMS API] LCDs: {summary['total']} total ({summary['new']} new, {summary['updated']} updated, {summary['unchanged']} unchanged)")
        return summary
