"""Payer Policy Research Service.

Tier 2 data source: Uses Gemini with Google Search grounding to research
commercial payer medical policies when no API is available.
Falls back for non-Medicare payers (Aetna, UHC, BCBS, Cigna, etc.).
"""

import json
from typing import Optional

import asyncpg

from .gemini_compliance import GeminiComplianceService


RESEARCH_PROMPT_TEMPLATE = """You are a medical coding and insurance policy expert.

Research {payer_name}'s medical policy for: {procedure}

Find the payer's published clinical policy bulletin or medical coverage policy.
Extract the following information and respond with JSON only (no markdown fences):

{{
  "payer_name": "{payer_name}",
  "payer_type": "government" or "commercial" or "medicaid_managed_care",
  "policy_number": "the payer's policy ID (e.g., CPB 0123, Policy 12345)",
  "policy_title": "policy title",
  "procedure_codes": ["CPT or HCPCS codes covered by this policy"],
  "diagnosis_codes": ["ICD-10 codes that commonly apply"],
  "procedure_description": "plain English procedure name",
  "coverage_status": "covered" or "not_covered" or "conditional",
  "requires_prior_auth": true or false,
  "clinical_criteria": "detailed clinical criteria for approval — be specific about what conditions must be documented",
  "documentation_requirements": "what documents/records must be submitted with the prior auth request",
  "medical_necessity_criteria": "specific medical necessity language from the policy",
  "age_restrictions": "age limits if any, or null",
  "frequency_limits": "how often the procedure is covered (e.g., once per 12 months), or null",
  "place_of_service": ["inpatient", "outpatient", "office"],
  "source_url": "URL to the payer's published policy document",
  "source_document": "document name/number",
  "confidence": 0.0 to 1.0
}}

Be specific about clinical criteria — physicians need the exact conditions that must be documented for approval.
If you cannot find the specific policy, set coverage_status to "conditional" and confidence below 0.5.
Return ONLY valid JSON."""


async def research_payer_policy(
    payer_name: str,
    procedure: str,
    conn: asyncpg.Connection,
) -> Optional[dict]:
    """Research a payer's medical policy for a procedure using Gemini.

    Stores the result in payer_medical_policies and triggers embedding.
    Returns the inserted policy dict, or None on failure.
    """
    prompt = RESEARCH_PROMPT_TEMPLATE.format(
        payer_name=payer_name, procedure=procedure
    )

    try:
        service = GeminiComplianceService()
        result = await service._call_with_retry(
            prompt,
            None,  # return full dict
            max_retries=1,
            label=f"Payer policy: {payer_name} / {procedure}",
        )
    except Exception as e:
        print(f"[Payer Research] Gemini failed for {payer_name}/{procedure}: {e}")
        return None

    if not result or not isinstance(result, dict):
        return None

    # Validate minimum fields
    policy_number = result.get("policy_number")
    if not policy_number:
        policy_number = f"gemini_{payer_name.lower().replace(' ', '_')}_{procedure.lower().replace(' ', '_')[:30]}"

    confidence = result.get("confidence", 0.5)
    procedure_codes = result.get("procedure_codes") or []
    diagnosis_codes = result.get("diagnosis_codes") or []

    if isinstance(procedure_codes, str):
        procedure_codes = [procedure_codes]
    if isinstance(diagnosis_codes, str):
        diagnosis_codes = [diagnosis_codes]

    row = await conn.fetchrow(
        """
        INSERT INTO payer_medical_policies
            (payer_name, payer_type, policy_number, policy_title,
             procedure_codes, diagnosis_codes, procedure_description,
             coverage_status, requires_prior_auth,
             clinical_criteria, documentation_requirements,
             medical_necessity_criteria, age_restrictions, frequency_limits,
             place_of_service, source_url, source_document,
             research_source, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, 'gemini', $18::jsonb)
        ON CONFLICT (payer_name, policy_number) DO UPDATE SET
            policy_title = EXCLUDED.policy_title,
            procedure_codes = EXCLUDED.procedure_codes,
            diagnosis_codes = EXCLUDED.diagnosis_codes,
            coverage_status = EXCLUDED.coverage_status,
            requires_prior_auth = EXCLUDED.requires_prior_auth,
            clinical_criteria = EXCLUDED.clinical_criteria,
            documentation_requirements = EXCLUDED.documentation_requirements,
            medical_necessity_criteria = EXCLUDED.medical_necessity_criteria,
            source_url = EXCLUDED.source_url,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        RETURNING id, payer_name, policy_number, policy_title, coverage_status
        """,
        result.get("payer_name", payer_name),
        result.get("payer_type", "commercial"),
        policy_number,
        result.get("policy_title", f"{payer_name} policy for {procedure}"),
        procedure_codes or None,
        diagnosis_codes or None,
        result.get("procedure_description", procedure),
        result.get("coverage_status", "conditional"),
        result.get("requires_prior_auth", False),
        result.get("clinical_criteria"),
        result.get("documentation_requirements"),
        result.get("medical_necessity_criteria"),
        result.get("age_restrictions"),
        result.get("frequency_limits"),
        result.get("place_of_service") or None,
        result.get("source_url"),
        result.get("source_document"),
        json.dumps({"confidence": confidence, "raw_research": True}),
    )

    if row:
        # Embed the new policy
        try:
            from .payer_policy_embedding_pipeline import embed_updated_policies
            await embed_updated_policies(conn)
        except Exception as e:
            print(f"[Payer Research] Embedding failed: {e}")

    return dict(row) if row else None
