"""AI guidance: suggested guidance (+stream) and outcome analysis (+stream)."""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Response, Query

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ...services.er_guidance import (
    _build_fallback_guidance_payload,
    _determination_confidence_floor,
    _normalize_analysis_payload,
    _normalize_suggested_guidance_payload,
)
from ...services import er_compliance_grounding, legal_defense
from ...models.er_case import (
    SuggestedGuidanceResponse,
    OutcomeAnalysisResponse,
    OutcomeOption,
    PartyAction,
)

from ._shared import (
    logger,
    _verify_case_company,
    _normalize_intake_context,
    _build_document_excerpts,
    _collect_raw_evidence_context,
    _fetch_company_policy_context,
    _resolve_involved_parties,
    _involved_employee_ids,
    _load_guidance_context,
    _build_er_analyzer,
)


async def _attach_grounding(payload: dict, raw_map, corpus_index: dict, *, case_id) -> None:
    """Gate the model's evidence_map against the corpus and stamp the 3 grounding
    fields onto a response payload dict. Central so every ER AI surface (the
    normalizers/constructors otherwise whitelist these keys away) enforces
    validate_citations identically — a hallucinated jur: id can never reach the UI."""
    clean_map, dropped = legal_defense.validate_citations(raw_map, corpus_index)
    payload["evidence_map"] = clean_map if corpus_index else []
    payload["compliance_citations"] = er_compliance_grounding.build_citation_records(clean_map, corpus_index)
    payload["grounding_available"] = bool(corpus_index)
    if dropped:
        logger.info("er grounding: dropped %d hallucinated citation(s) for case %s", len(dropped), case_id)

router = APIRouter()


@router.get("/{case_id}/guidance/suggested", response_model=Optional[SuggestedGuidanceResponse])
async def get_cached_guidance(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return the last cached guidance stored in intake_context.last_guidance."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        row = await conn.fetchrow(
            "SELECT intake_context FROM er_cases WHERE id = $1",
            case_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Case not found")

        intake_context = _normalize_intake_context(row["intake_context"]) or {}
        last_guidance = intake_context.get("last_guidance") if isinstance(intake_context, dict) else None
        if not last_guidance:
            return Response(status_code=204)

        try:
            return SuggestedGuidanceResponse(**last_guidance)
        except Exception:
            return Response(status_code=204)


@router.post("/{case_id}/guidance/suggested", response_model=SuggestedGuidanceResponse)
async def generate_suggested_guidance(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    model: Optional[str] = Query(None, pattern="^(flash|pro)$"),
):
    """Generate Gemini-backed interactive suggested guidance from current case analyses."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        case_row = await conn.fetchrow(
            """
            SELECT case_number, title, description, status, intake_context, created_at, updated_at, involved_employees
            FROM er_cases
            WHERE id = $1
            """,
            case_id,
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        analysis_rows = await conn.fetch(
            """
            SELECT analysis_type, analysis_data
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = ANY($2::text[])
            """,
            case_id,
            ["timeline", "discrepancies", "policy_check"],
        )

        ctx = await _load_guidance_context(conn, case_id, case_row)
        enriched_employees = ctx["enriched_employees"]
        evidence_rows = ctx["evidence_rows"]
        transcript_rows = ctx["transcript_rows"]
        all_doc_text_rows = ctx["all_doc_text_rows"]
        linked_incident = ctx["linked_incident"]
        completed_investigation_transcript_count = ctx["completed_investigation_transcript_count"]

        try:
            corpus_text, corpus_index = await er_compliance_grounding.build_jurisdiction_corpus(
                conn, company_id, _involved_employee_ids(case_row["involved_employees"])
            )
        except Exception:
            logger.exception("er guidance: grounding build failed for case %s", case_id)
            corpus_text, corpus_index = "", {}

    analysis_map: dict[str, dict[str, Any]] = {}
    for row in analysis_rows:
        analysis_type = str(row["analysis_type"])
        analysis_map[analysis_type] = _normalize_analysis_payload(row["analysis_data"], {})

    timeline_data = _normalize_analysis_payload(
        analysis_map.get("timeline"),
        {"events": [], "gaps_identified": [], "timeline_summary": ""},
    )
    discrepancies_data = _normalize_analysis_payload(
        analysis_map.get("discrepancies"),
        {"discrepancies": [], "credibility_notes": [], "summary": ""},
    )
    policy_data = _normalize_analysis_payload(
        analysis_map.get("policy_check"),
        {"violations": [], "policies_potentially_applicable": [], "summary": ""},
    )

    intake_context = _normalize_intake_context(case_row["intake_context"]) or {}
    assistance_answers = intake_context.get("answers", {}) if isinstance(intake_context, dict) else {}
    objective = assistance_answers.get("objective") if isinstance(assistance_answers, dict) else None
    immediate_risk = assistance_answers.get("immediate_risk") if isinstance(assistance_answers, dict) else None

    completed_non_policy_docs = [
        {
            "id": str(row["id"]),
            "filename": row["filename"] or f"Document {idx + 1}",
        }
        for idx, row in enumerate(evidence_rows)
    ]
    can_run_discrepancies = len(completed_non_policy_docs) >= 2

    linked_incident_has_witnesses = False
    if linked_incident:
        witnesses = linked_incident["witnesses"]
        if isinstance(witnesses, str):
            witnesses = json.loads(witnesses)
        if isinstance(witnesses, list) and len(witnesses) > 0:
            linked_incident_has_witnesses = True

    fallback_payload = _build_fallback_guidance_payload(
        timeline_data=timeline_data,
        discrepancies_data=discrepancies_data,
        policy_data=policy_data,
        completed_non_policy_docs=completed_non_policy_docs,
        objective=objective if isinstance(objective, str) else None,
        immediate_risk=immediate_risk if isinstance(immediate_risk, str) else None,
        linked_incident_has_witnesses=linked_incident_has_witnesses,
        completed_investigation_transcript_count=completed_investigation_transcript_count,
    )

    case_info = {
        "case_number": case_row["case_number"],
        "title": case_row["title"],
        "description": case_row["description"],
        "status": case_row["status"],
        "created_at": case_row["created_at"].isoformat() if case_row["created_at"] else None,
        "updated_at": case_row["updated_at"].isoformat() if case_row["updated_at"] else None,
        "involved_employees": enriched_employees,
    }
    analyses_completed = {
        "timeline": "timeline" in analysis_map and bool(
            timeline_data.get("events") or timeline_data.get("timeline_summary")
        ),
        "discrepancies": "discrepancies" in analysis_map and bool(
            discrepancies_data.get("discrepancies") or discrepancies_data.get("summary")
        ),
        "policy_check": "policy_check" in analysis_map and bool(
            policy_data.get("violations") or policy_data.get("summary")
        ),
    }
    evidence_overview = {
        "completed_non_policy_doc_count": len(completed_non_policy_docs),
        "completed_non_policy_doc_names": [doc["filename"] for doc in completed_non_policy_docs[:12]],
        "can_run_discrepancies": can_run_discrepancies,
        "analyses_completed": analyses_completed,
    }
    analysis_results = {
        "timeline": timeline_data,
        "discrepancies": discrepancies_data,
        "policy_check": policy_data,
    }

    # Build document excerpts from ALL completed docs with text (used for guidance and confidence eval)
    transcript_excerpts = _build_document_excerpts(all_doc_text_rows, text_key="scrubbed_text")

    has_policy_violations = bool(policy_data.get("violations"))
    has_analyses = any(analyses_completed.values())
    floor_confidence = _determination_confidence_floor(
        completed_doc_count=len(completed_non_policy_docs),
        transcript_count=len(transcript_rows),
        has_analyses=has_analyses,
        has_policy_violations=has_policy_violations,
    )

    try:
        analyzer = _build_er_analyzer(model_override=model)
        guidance_task = analyzer.generate_suggested_guidance(
            case_info=case_info,
            intake_context=intake_context if isinstance(intake_context, dict) else {},
            evidence_overview=evidence_overview,
            analysis_results=analysis_results,
            document_excerpts=transcript_excerpts,
            jurisdiction_requirements=corpus_text,
        )
        confidence_task = analyzer.evaluate_determination_confidence(
            case_info=case_info,
            evidence_overview={"doc_count": len(completed_non_policy_docs), "transcript_count": len(transcript_rows)},
            transcript_excerpts=transcript_excerpts,
            timeline_summary=timeline_data.get("timeline_summary", ""),
            discrepancies_summary=discrepancies_data.get("summary", ""),
            policy_summary=policy_data.get("summary", ""),
        )
        raw_payload, confidence_result = await asyncio.gather(
            guidance_task, confidence_task, return_exceptions=True,
        )

        # Handle guidance result
        if isinstance(raw_payload, BaseException):
            logger.error(
                "Suggested guidance generation failed for case %s: %s", case_id, raw_payload,
                exc_info=raw_payload,
            )
            payload = fallback_payload
        else:
            payload = _normalize_suggested_guidance_payload(
                raw_payload,
                fallback_payload=fallback_payload,
                can_run_discrepancies=can_run_discrepancies,
                model_name=analyzer.model,
            )

        # Handle confidence result
        if isinstance(confidence_result, BaseException):
            logger.error(
                "Confidence eval failed for case %s: %s", case_id, confidence_result,
                exc_info=confidence_result,
            )
            confidence_result = {"confidence": floor_confidence, "signals": [], "summary": ""}

        confidence = confidence_result.get("confidence", floor_confidence)
        if not isinstance(confidence, (int, float)):
            confidence = floor_confidence
        confidence = max(floor_confidence, float(confidence))
        signals = [s for s in confidence_result.get("signals", []) if isinstance(s, dict) and s.get("present")]
        determination_signals = [s["reasoning"] for s in signals if isinstance(s.get("reasoning"), str)]

        payload["determination_suggested"] = confidence >= 0.80
        payload["determination_confidence"] = round(confidence, 2)
        payload["determination_signals"] = determination_signals

        raw_map = raw_payload.get("evidence_map") if isinstance(raw_payload, dict) else None
        await _attach_grounding(payload, raw_map, corpus_index, case_id=case_id)

        result = SuggestedGuidanceResponse(**payload)

        # Cache result in intake_context.last_guidance
        # Use a fresh connection — the original `async with get_connection()` scope has closed
        try:
            existing_intake = _normalize_intake_context(case_row["intake_context"]) or {}
            if not isinstance(existing_intake, dict):
                existing_intake = {}
            existing_intake["last_guidance"] = result.model_dump(mode="json")
            async with get_connection() as cache_conn:
                await cache_conn.execute(
                    "UPDATE er_cases SET intake_context = $1::jsonb WHERE id = $2",
                    json.dumps(existing_intake),
                    case_id,
                )
        except Exception as cache_err:
            logger.warning("Failed to cache guidance for case %s: %s", case_id, cache_err)

        return result
    except Exception as exc:
        logger.error(
            "Suggested guidance generation failed for case %s: %s", case_id, exc, exc_info=True,
        )
        fallback_payload["determination_confidence"] = floor_confidence
        return SuggestedGuidanceResponse(**fallback_payload)


@router.post("/{case_id}/guidance/suggested/stream")
async def generate_suggested_guidance_stream(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    model: Optional[str] = Query(None, pattern="^(flash|pro)$"),
):
    """Stream SSE progress events during guidance generation, ending with the final result."""
    from fastapi.responses import StreamingResponse

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        case_row = await conn.fetchrow(
            """
            SELECT case_number, title, description, status, intake_context, created_at, updated_at, involved_employees
            FROM er_cases
            WHERE id = $1
            """,
            case_id,
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        analysis_rows = await conn.fetch(
            """
            SELECT analysis_type, analysis_data
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = ANY($2::text[])
            """,
            case_id,
            ["timeline", "discrepancies", "policy_check"],
        )

        ctx = await _load_guidance_context(conn, case_id, case_row)
        enriched_employees_s = ctx["enriched_employees"]
        evidence_rows = ctx["evidence_rows"]
        transcript_rows = ctx["transcript_rows"]
        all_doc_text_rows_s = ctx["all_doc_text_rows"]

        try:
            corpus_text, corpus_index = await er_compliance_grounding.build_jurisdiction_corpus(
                conn, company_id, _involved_employee_ids(case_row["involved_employees"])
            )
        except Exception:
            logger.exception("er guidance stream: grounding build failed for case %s", case_id)
            corpus_text, corpus_index = "", {}

    async def event_stream():
        def sse(event: dict) -> str:
            return f"data: {json.dumps(event)}\n\n"

        yield sse({"type": "status", "message": f"Loading case {case_row['case_number']}..."})

        analysis_map_local: dict[str, dict[str, Any]] = {}
        for row in analysis_rows:
            analysis_type_key = str(row["analysis_type"])
            analysis_map_local[analysis_type_key] = _normalize_analysis_payload(row["analysis_data"], {})

        timeline_data_local = _normalize_analysis_payload(
            analysis_map_local.get("timeline"),
            {"events": [], "gaps_identified": [], "timeline_summary": ""},
        )
        discrepancies_data_local = _normalize_analysis_payload(
            analysis_map_local.get("discrepancies"),
            {"discrepancies": [], "credibility_notes": [], "summary": ""},
        )
        policy_data_local = _normalize_analysis_payload(
            analysis_map_local.get("policy_check"),
            {"violations": [], "policies_potentially_applicable": [], "summary": ""},
        )

        doc_count = len(evidence_rows)
        transcript_count = len(transcript_rows)
        yield sse({"type": "status", "message": f"Found {doc_count} evidence document(s) and {transcript_count} transcript(s)"})

        intake_ctx = _normalize_intake_context(case_row["intake_context"]) or {}
        assistance_ans = intake_ctx.get("answers", {}) if isinstance(intake_ctx, dict) else {}
        obj = assistance_ans.get("objective") if isinstance(assistance_ans, dict) else None
        imm_risk = assistance_ans.get("immediate_risk") if isinstance(assistance_ans, dict) else None

        completed_docs = [
            {"id": str(row["id"]), "filename": row["filename"] or f"Document {idx + 1}"}
            for idx, row in enumerate(evidence_rows)
        ]
        can_run_disc = len(completed_docs) >= 2

        fallback = _build_fallback_guidance_payload(
            timeline_data=timeline_data_local,
            discrepancies_data=discrepancies_data_local,
            policy_data=policy_data_local,
            completed_non_policy_docs=completed_docs,
            objective=obj if isinstance(obj, str) else None,
            immediate_risk=imm_risk if isinstance(imm_risk, str) else None,
        )

        c_info = {
            "case_number": case_row["case_number"],
            "title": case_row["title"],
            "description": case_row["description"],
            "status": case_row["status"],
            "created_at": case_row["created_at"].isoformat() if case_row["created_at"] else None,
            "updated_at": case_row["updated_at"].isoformat() if case_row["updated_at"] else None,
            "involved_employees": enriched_employees_s,
        }
        analyses_done = {
            "timeline": "timeline" in analysis_map_local and bool(
                timeline_data_local.get("events") or timeline_data_local.get("timeline_summary")
            ),
            "discrepancies": "discrepancies" in analysis_map_local and bool(
                discrepancies_data_local.get("discrepancies") or discrepancies_data_local.get("summary")
            ),
            "policy_check": "policy_check" in analysis_map_local and bool(
                policy_data_local.get("violations") or policy_data_local.get("summary")
            ),
        }
        ev_overview = {
            "completed_non_policy_doc_count": len(completed_docs),
            "completed_non_policy_doc_names": [d["filename"] for d in completed_docs[:12]],
            "can_run_discrepancies": can_run_disc,
            "analyses_completed": analyses_done,
        }
        a_results = {
            "timeline": timeline_data_local,
            "discrepancies": discrepancies_data_local,
            "policy_check": policy_data_local,
        }

        # Build document excerpts from ALL completed docs with text
        t_excerpts = _build_document_excerpts(all_doc_text_rows_s, text_key="scrubbed_text")

        has_violations = bool(policy_data_local.get("violations"))
        has_any_analysis = any(analyses_done.values())
        floor_conf = _determination_confidence_floor(
            completed_doc_count=len(completed_docs),
            transcript_count=transcript_count,
            has_analyses=has_any_analysis,
            has_policy_violations=has_violations,
        )

        try:
            analyzer = _build_er_analyzer(model_override=model)

            if corpus_text:
                yield sse({"type": "status", "message": "Checking state employment requirements..."})
            yield sse({"type": "status", "message": "Generating investigative guidance..."})

            guidance_task = analyzer.generate_suggested_guidance(
                case_info=c_info,
                intake_context=intake_ctx if isinstance(intake_ctx, dict) else {},
                evidence_overview=ev_overview,
                analysis_results=a_results,
                document_excerpts=t_excerpts,
                jurisdiction_requirements=corpus_text,
            )

            yield sse({"type": "status", "message": "Scoring evidence confidence..."})

            confidence_task = analyzer.evaluate_determination_confidence(
                case_info=c_info,
                evidence_overview={"doc_count": len(completed_docs), "transcript_count": transcript_count},
                transcript_excerpts=t_excerpts,
                timeline_summary=timeline_data_local.get("timeline_summary", ""),
                discrepancies_summary=discrepancies_data_local.get("summary", ""),
                policy_summary=policy_data_local.get("summary", ""),
            )

            raw_result, conf_result = await asyncio.gather(
                guidance_task, confidence_task, return_exceptions=True,
            )

            yield sse({"type": "status", "message": "Assembling recommendations..."})

            if isinstance(raw_result, BaseException):
                logger.error(
                    "Streaming guidance generation failed for case %s: %s", case_id, raw_result,
                    exc_info=raw_result,
                )
                payload = fallback
            else:
                payload = _normalize_suggested_guidance_payload(
                    raw_result,
                    fallback_payload=fallback,
                    can_run_discrepancies=can_run_disc,
                    model_name=analyzer.model,
                )

            if isinstance(conf_result, BaseException):
                logger.error(
                    "Streaming confidence eval failed for case %s: %s", case_id, conf_result,
                    exc_info=conf_result,
                )
                conf_result = {"confidence": floor_conf, "signals": [], "summary": ""}

            conf = conf_result.get("confidence", floor_conf)
            if not isinstance(conf, (int, float)):
                conf = floor_conf
            conf = max(floor_conf, float(conf))
            present_signals = [s for s in conf_result.get("signals", []) if isinstance(s, dict) and s.get("present")]
            det_signals = [s["reasoning"] for s in present_signals if isinstance(s.get("reasoning"), str)]

            payload["determination_suggested"] = conf >= 0.80
            payload["determination_confidence"] = round(conf, 2)
            payload["determination_signals"] = det_signals

            raw_map = raw_result.get("evidence_map") if isinstance(raw_result, dict) else None
            await _attach_grounding(payload, raw_map, corpus_index, case_id=case_id)

            response_obj = SuggestedGuidanceResponse(**payload)
            yield sse({"type": "result", "data": response_obj.model_dump(mode="json")})
        except Exception as exc:
            logger.error(
                "Streaming guidance generation failed for case %s: %s", case_id, exc, exc_info=True,
            )
            fallback["determination_confidence"] = floor_conf
            response_obj = SuggestedGuidanceResponse(**fallback)
            yield sse({"type": "result", "data": response_obj.model_dump(mode="json")})

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


# ===========================================
# Outcome Analysis (Case Determination)
# ===========================================

@router.post("/{case_id}/guidance/outcomes/stream")
async def generate_outcome_analysis_stream(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    model: Optional[str] = Query(None, pattern="^(flash|pro)$"),
):
    """Stream SSE progress events during outcome analysis generation for case determination."""
    from fastapi.responses import StreamingResponse

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        is_admin = current_user.role == "admin"
        await _verify_case_company(conn, case_id, company_id, is_admin)

        case_row = await conn.fetchrow(
            """
            SELECT case_number, title, description, status, intake_context, category, created_at, updated_at, involved_employees
            FROM er_cases
            WHERE id = $1
            """,
            case_id,
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        involved_parties = await _resolve_involved_parties(conn, case_row.get("involved_employees"))
        try:
            corpus_text, corpus_index = await er_compliance_grounding.build_jurisdiction_corpus(
                conn, company_id, _involved_employee_ids(case_row.get("involved_employees"))
            )
        except Exception:
            logger.exception("er outcome stream: grounding build failed for case %s", case_id)
            corpus_text, corpus_index = "", {}

        analysis_rows = await conn.fetch(
            """
            SELECT analysis_type, analysis_data
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = ANY($2::text[])
            """,
            case_id,
            ["timeline", "discrepancies", "policy_check"],
        )

        # Query past case precedent for this company
        company_filter = "(company_id = $1 OR company_id IS NULL)" if is_admin else "company_id = $1"
        precedent_rows = await conn.fetch(
            f"""
            SELECT outcome, COUNT(*) as cnt
            FROM er_cases
            WHERE {company_filter} AND status = 'closed' AND outcome IS NOT NULL
            GROUP BY outcome
            """,
            company_id,
        )

        company_row = await conn.fetchrow(
            "SELECT industry, healthcare_specialties FROM companies WHERE id = $1",
            company_id,
        )

    precedent_stats = {r["outcome"]: r["cnt"] for r in precedent_rows}
    total_closed = sum(precedent_stats.values())

    healthcare_context = None
    if company_row:
        is_healthcare = (
            (company_row["industry"] or "").lower() in ("healthcare", "health care", "medical")
            or bool(company_row["healthcare_specialties"])
        )
        if is_healthcare:
            healthcare_context = {
                "industry": company_row["industry"],
                "specialties": company_row["healthcare_specialties"] or [],
            }

    intake_ctx = _normalize_intake_context(case_row["intake_context"]) or {}
    last_guidance = intake_ctx.get("last_guidance", {}) if isinstance(intake_ctx, dict) else {}
    cached_determination_confidence = (
        float(last_guidance["determination_confidence"])
        if isinstance(last_guidance, dict) and isinstance(last_guidance.get("determination_confidence"), (int, float))
        else None
    )

    async def event_stream():
        def sse(event: dict) -> str:
            return f"data: {json.dumps(event)}\n\n"

        # Parse analysis data
        analysis_map: dict[str, dict[str, Any]] = {}
        for row in analysis_rows:
            raw = row["analysis_data"]
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            analysis_map[str(row["analysis_type"])] = raw if isinstance(raw, dict) else {}

        timeline_data = analysis_map.get("timeline", {})
        disc_data = analysis_map.get("discrepancies", {})
        policy_data = analysis_map.get("policy_check", {})

        # Data-aware status messages
        n_events = len(timeline_data.get("events", []))
        n_discrepancies = len(disc_data.get("discrepancies", []))
        n_violations = len(policy_data.get("violations", []))

        yield sse({"type": "status", "message": f"Reviewing {n_events} timeline events..."})

        analysis_summary_parts = []
        if timeline_data.get("timeline_summary"):
            analysis_summary_parts.append(f"Timeline: {timeline_data['timeline_summary']}")
        if disc_data.get("summary"):
            analysis_summary_parts.append(f"Discrepancies: {disc_data['summary']}")

        # Fallback: when no pre-computed analysis exists, pull raw documents
        # and investigation notes directly so the LLM still has source
        # material. Mature cases with timeline/discrepancy summaries don't
        # need this — the summaries already distill the docs.
        if not analysis_summary_parts:
            try:
                async with get_connection() as ev_conn:
                    raw_evidence_ctx = await _collect_raw_evidence_context(ev_conn, case_id)
            except Exception as exc:
                logger.warning(
                    "Failed to collect raw evidence context for case %s: %s",
                    case_id, exc,
                )
                raw_evidence_ctx = ""
            if raw_evidence_ctx:
                analysis_summary_parts.append(raw_evidence_ctx)

        analysis_summary = "\n\n".join(analysis_summary_parts) or "No analysis summaries available."

        policy_findings = policy_data.get("summary", "")

        # Fallback: if policy_check analysis is empty, pull company policies + handbook directly
        if not policy_findings or policy_findings == "No policy findings available.":
            async with get_connection() as policy_conn:
                direct_policy_ctx = await _fetch_company_policy_context(policy_conn, company_id)
            if direct_policy_ctx:
                policy_findings = direct_policy_ctx
            else:
                policy_findings = "No policy findings available."

        yield sse({"type": "status", "message": f"Found {n_discrepancies} discrepancies and {n_violations} policy violations"})

        precedent_display = {
            "total_closed_cases": total_closed,
            "outcome_distribution": precedent_stats,
        }

        yield sse({"type": "status", "message": f"Checking precedent across {total_closed} prior closed cases..."})

        c_info = {
            "case_number": case_row["case_number"],
            "title": case_row["title"],
            "description": case_row["description"],
            "status": case_row["status"],
            "category": case_row.get("category"),
            "created_at": case_row["created_at"].isoformat() if case_row["created_at"] else None,
        }
        if involved_parties:
            c_info["involved_parties"] = involved_parties

        if healthcare_context:
            yield sse({"type": "status", "message": "Applying Just Culture framework for clinical safety analysis..."})

        yield sse({"type": "status", "message": "Starting AI outcome analysis..."})

        try:
            analyzer = _build_er_analyzer(model_override=model)

            # Queue bridge: stream status from the analyzer callback into SSE
            status_queue: asyncio.Queue[str] = asyncio.Queue()

            async def on_status(msg: str):
                await status_queue.put(msg)

            task = asyncio.create_task(
                analyzer.generate_outcome_analysis_streaming(
                    case_info=c_info,
                    analysis_summary=analysis_summary,
                    policy_findings=policy_findings,
                    precedent_stats=precedent_display,
                    on_status=on_status,
                    healthcare_context=healthcare_context,
                    determination_confidence=cached_determination_confidence,
                    jurisdiction_requirements=corpus_text,
                )
            )

            # Drain status messages while analysis runs
            while not task.done():
                try:
                    msg = await asyncio.wait_for(status_queue.get(), timeout=0.3)
                    yield sse({"type": "status", "message": msg})
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining queued messages
            while not status_queue.empty():
                msg = status_queue.get_nowait()
                yield sse({"type": "status", "message": msg})

            raw_result = task.result()

            # Normalize outcomes
            outcomes = []
            for o in raw_result.get("outcomes", []):
                if not isinstance(o, dict):
                    continue
                det = o.get("determination", "inconclusive")
                if det not in ("substantiated", "unsubstantiated", "inconclusive"):
                    det = "inconclusive"
                action = o.get("recommended_action", "other")
                valid_actions = {"termination", "disciplinary_action", "retraining", "no_action", "resignation", "other"}
                if action not in valid_actions:
                    action = "other"
                conf = o.get("confidence", "medium")
                if conf not in ("high", "medium", "low"):
                    conf = "medium"
                outcomes.append(OutcomeOption(
                    determination=det,
                    recommended_action=action,
                    action_label=o.get("action_label", action.replace("_", " ").title()),
                    reasoning=o.get("reasoning", ""),
                    policy_basis=o.get("policy_basis", ""),
                    hr_considerations=o.get("hr_considerations", ""),
                    precedent_note=o.get("precedent_note", ""),
                    confidence=conf,
                    party_actions=[
                        PartyAction(**pa) for pa in o.get("party_actions", [])
                        if isinstance(pa, dict) and "name" in pa and "action" in pa
                    ],
                ))

            # Filter contradictory outcomes when evidence readiness >= 80%
            if cached_determination_confidence is not None and cached_determination_confidence >= 0.80:
                outcomes = [
                    o for o in outcomes
                    if not (
                        "insufficient" in o.action_label.lower()
                        or ("case closure" in o.action_label.lower() and "insufficient" in o.reasoning.lower())
                    )
                ]

            # Sort by confidence: high first, then medium, then low
            _CONF_ORDER = {"high": 0, "medium": 1, "low": 2}
            outcomes.sort(key=lambda o: _CONF_ORDER.get(o.confidence, 99))

            grounding: dict[str, Any] = {}
            await _attach_grounding(grounding, raw_result.get("evidence_map"), corpus_index, case_id=case_id)

            response_obj = OutcomeAnalysisResponse(
                outcomes=outcomes,
                case_summary=raw_result.get("case_summary", ""),
                generated_at=datetime.now(timezone.utc),
                model=raw_result.get("model", analyzer.model),
                evidence_map=grounding["evidence_map"],
                compliance_citations=grounding["compliance_citations"],
                grounding_available=grounding["grounding_available"],
            )
            yield sse({"type": "result", "data": response_obj.model_dump(mode="json")})

        except Exception as exc:
            import traceback
            logger.error(
                "Outcome analysis streaming failed for case %s: %s\n%s",
                case_id, exc, traceback.format_exc(),
            )

            fallback = OutcomeAnalysisResponse(
                outcomes=[],
                case_summary="Unable to generate outcome analysis. Please review the case manually.",
                generated_at=datetime.now(timezone.utc),
                model="unknown",
            )
            yield sse({"type": "result", "data": fallback.model_dump(mode="json")})

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/{case_id}/guidance/outcomes", response_model=OutcomeAnalysisResponse)
async def generate_outcome_analysis(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    model: Optional[str] = Query(None, pattern="^(flash|pro)$"),
):
    """Non-streaming outcome analysis generation for case determination."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        is_admin = current_user.role == "admin"
        await _verify_case_company(conn, case_id, company_id, is_admin)

        case_row = await conn.fetchrow(
            "SELECT case_number, title, description, status, category, created_at, intake_context, involved_employees FROM er_cases WHERE id = $1",
            case_id,
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        involved_parties_ns = await _resolve_involved_parties(conn, case_row.get("involved_employees"))
        try:
            corpus_text, corpus_index = await er_compliance_grounding.build_jurisdiction_corpus(
                conn, company_id, _involved_employee_ids(case_row.get("involved_employees"))
            )
        except Exception:
            logger.exception("er outcome: grounding build failed for case %s", case_id)
            corpus_text, corpus_index = "", {}

        analysis_rows = await conn.fetch(
            """
            SELECT analysis_type, analysis_data
            FROM er_case_analysis
            WHERE case_id = $1 AND analysis_type = ANY($2::text[])
            """,
            case_id,
            ["timeline", "discrepancies", "policy_check"],
        )

        company_filter = "(company_id = $1 OR company_id IS NULL)" if is_admin else "company_id = $1"
        precedent_rows = await conn.fetch(
            f"""
            SELECT outcome, COUNT(*) as cnt
            FROM er_cases
            WHERE {company_filter} AND status = 'closed' AND outcome IS NOT NULL
            GROUP BY outcome
            """,
            company_id,
        )

        company_row = await conn.fetchrow(
            "SELECT industry, healthcare_specialties FROM companies WHERE id = $1",
            company_id,
        )

    precedent_stats = {r["outcome"]: r["cnt"] for r in precedent_rows}
    total_closed = sum(precedent_stats.values())

    healthcare_context = None
    if company_row:
        is_healthcare = (
            (company_row["industry"] or "").lower() in ("healthcare", "health care", "medical")
            or bool(company_row["healthcare_specialties"])
        )
        if is_healthcare:
            healthcare_context = {
                "industry": company_row["industry"],
                "specialties": company_row["healthcare_specialties"] or [],
            }

    analysis_map: dict[str, dict[str, Any]] = {}
    for row in analysis_rows:
        raw = row["analysis_data"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        analysis_map[str(row["analysis_type"])] = raw if isinstance(raw, dict) else {}

    timeline_data = analysis_map.get("timeline", {})
    disc_data = analysis_map.get("discrepancies", {})
    policy_data = analysis_map.get("policy_check", {})

    summary_parts = []
    if timeline_data.get("timeline_summary"):
        summary_parts.append(f"Timeline: {timeline_data['timeline_summary']}")
    if disc_data.get("summary"):
        summary_parts.append(f"Discrepancies: {disc_data['summary']}")

    # Fallback: when no pre-computed analysis exists, pull raw documents
    # and investigation notes directly so the LLM still has source
    # material. Mature cases with timeline/discrepancy summaries don't
    # need this — the summaries already distill the docs.
    if not summary_parts:
        try:
            async with get_connection() as ev_conn:
                raw_evidence_ctx = await _collect_raw_evidence_context(ev_conn, case_id)
        except Exception as exc:
            logger.warning(
                "Failed to collect raw evidence context for case %s: %s",
                case_id, exc,
            )
            raw_evidence_ctx = ""
        if raw_evidence_ctx:
            summary_parts.append(raw_evidence_ctx)

    analysis_summary = "\n\n".join(summary_parts) or "No analysis summaries available."

    policy_findings = policy_data.get("summary", "")

    # Fallback: if policy_check analysis is empty, pull company policies + handbook directly
    if not policy_findings or policy_findings == "No policy findings available.":
        async with get_connection() as policy_conn:
            direct_policy_ctx = await _fetch_company_policy_context(policy_conn, company_id)
        if direct_policy_ctx:
            policy_findings = direct_policy_ctx
        else:
            policy_findings = "No policy findings available."

    c_info = {
        "case_number": case_row["case_number"],
        "title": case_row["title"],
        "description": case_row["description"],
        "status": case_row["status"],
        "category": case_row.get("category"),
        "created_at": case_row["created_at"].isoformat() if case_row["created_at"] else None,
    }
    if involved_parties_ns:
        c_info["involved_parties"] = involved_parties_ns

    intake_ctx = _normalize_intake_context(case_row["intake_context"]) or {}
    last_guidance = intake_ctx.get("last_guidance", {}) if isinstance(intake_ctx, dict) else {}
    cached_determination_confidence = (
        float(last_guidance["determination_confidence"])
        if isinstance(last_guidance, dict) and isinstance(last_guidance.get("determination_confidence"), (int, float))
        else None
    )

    analyzer = _build_er_analyzer(model_override=model)
    raw_result = await analyzer.generate_outcome_analysis(
        case_info=c_info,
        analysis_summary=analysis_summary,
        policy_findings=policy_findings,
        precedent_stats={"total_closed_cases": total_closed, "outcome_distribution": precedent_stats},
        healthcare_context=healthcare_context,
        determination_confidence=cached_determination_confidence,
        jurisdiction_requirements=corpus_text,
    )

    outcomes = []
    for o in raw_result.get("outcomes", []):
        if not isinstance(o, dict):
            continue
        det = o.get("determination", "inconclusive")
        if det not in ("substantiated", "unsubstantiated", "inconclusive"):
            det = "inconclusive"
        action = o.get("recommended_action", "other")
        valid_actions = {"termination", "disciplinary_action", "retraining", "no_action", "resignation", "other"}
        if action not in valid_actions:
            action = "other"
        conf = o.get("confidence", "medium")
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        outcomes.append(OutcomeOption(
            determination=det,
            recommended_action=action,
            action_label=o.get("action_label", action.replace("_", " ").title()),
            reasoning=o.get("reasoning", ""),
            policy_basis=o.get("policy_basis", ""),
            hr_considerations=o.get("hr_considerations", ""),
            precedent_note=o.get("precedent_note", ""),
            confidence=conf,
            applies_to=o.get("applies_to"),
        ))

    # Filter contradictory outcomes when evidence readiness >= 80%
    if cached_determination_confidence is not None and cached_determination_confidence >= 0.80:
        outcomes = [
            o for o in outcomes
            if not (
                "insufficient" in o.action_label.lower()
                or ("case closure" in o.action_label.lower() and "insufficient" in o.reasoning.lower())
            )
        ]

    # Sort by confidence: high first, then medium, then low
    _CONF_ORDER = {"high": 0, "medium": 1, "low": 2}
    outcomes.sort(key=lambda o: _CONF_ORDER.get(o.confidence, 99))

    grounding: dict[str, Any] = {}
    await _attach_grounding(grounding, raw_result.get("evidence_map"), corpus_index, case_id=case_id)

    return OutcomeAnalysisResponse(
        outcomes=outcomes,
        case_summary=raw_result.get("case_summary", ""),
        generated_at=datetime.now(timezone.utc),
        model=raw_result.get("model", analyzer.model),
        evidence_map=grounding["evidence_map"],
        compliance_citations=grounding["compliance_citations"],
        grounding_available=grounding["grounding_available"],
    )


# ===========================================
# Evidence Search (RAG)
# ===========================================

