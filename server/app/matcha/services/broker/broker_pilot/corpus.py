"""Corpus build -- platform context sections, contract clauses, uploaded
documents, native-source records, and jurisdiction records, flattened into one
index of {cid, ref, summary, when}. Pure (no DB) and unit-tested.
"""
import json
import logging
from app.matcha.services._shared.pdf import _fmt_dt

from app.matcha.services._shared.text import _hum, _slug

logger = logging.getLogger(__name__)


def _fmt_num(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"{f:,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def _clause_records(ctx: dict) -> list[dict]:
    """One `clause:<contract_id>` record per contract carrying an extracted
    indemnity, so the analyst can cite the clause itself (verbatim quote + page)
    rather than paraphrasing it.

    Its own corpus source, NOT a prefixed record inside `platform` — the memo's
    appendix builder dispatches on cid prefix, and an unrecognized prefix inside
    the platform bucket would fall through to the native branch and re-render
    every cited platform record as a duplicate table.
    """
    recs: list[dict] = []
    for c in ((ctx or {}).get("limits") or {}).get("contracts") or []:
        if not isinstance(c, dict):
            continue
        ind = c.get("indemnity") or {}
        clause = (c.get("risk_transfer") or {}).get("indemnity") or {}
        if not clause.get("present"):
            continue
        bits = [f"{str(clause.get('form') or 'unclassified').replace('_', ' ')} form"]
        if clause.get("covers_sole_negligence"):
            bits.append("reaches the counterparty's sole negligence")
        if clause.get("defense_obligation"):
            bits.append("includes a duty to defend")
        if ind.get("verdict"):
            bits.append(f"verdict: {str(ind['verdict']).replace('_', ' ')}")
        if ind.get("statute"):
            bits.append(f"under {ind['statute']}")
        if c.get("provisional"):
            bits.append("PROVISIONAL — extraction not yet confirmed by a reviewer")
        quote = clause.get("quote")
        if quote:
            page = f", p. {clause['page']}" if clause.get("page") else ""
            bits.append(f'clause text{page}: "{quote}"')
        recs.append({
            "cid": f"clause:{c.get('id')}",
            "ref": f"Indemnity clause — {c.get('name') or 'contract'}",
            "summary": (f"{c.get('name') or 'Contract'}"
                        + (f" (counterparty {c['counterparty']})" if c.get("counterparty") else "")
                        + f": {'; '.join(bits)}."),
            "when": "current",
        })
    return recs


# Named drivers itemized in the corpus. The fleet headline always counts every
# driver; this only bounds how many are named, so a 400-driver fleet can't crowd
# out the rest of the grounding.
_FLEET_DRIVER_CAP = 25


def _platform_records(ctx: dict) -> list[dict]:
    """Serialize a `_tenant_context` / `_external_context` dict into compact
    corpus records. Every accessor is guard-railed — a missing/empty section
    emits nothing (it was already `_safe()`-defaulted upstream)."""
    ctx = ctx or {}
    recs: list[dict] = []

    def add(cid: str, ref: str, summary: str, when: str = "current"):
        recs.append({"cid": cid, "ref": ref, "summary": summary, "when": when})

    # Profile
    bits = [b for b in (
        f"industry {ctx.get('industry')}" if ctx.get("industry") else None,
        f"headcount {ctx.get('headcount')}" if ctx.get("headcount") else None,
        f"primary state {ctx.get('state')}" if ctx.get("state") else None,
    ) if b]
    if ctx.get("name") or bits:
        add("platform:profile", "Client profile",
            f"{ctx.get('name') or 'Client'}: {', '.join(bits) or 'no profile details on file'}.")

    # Workers' comp
    wc = ctx.get("wc") or {}
    if any(wc.get(k) is not None for k in ("trir", "dart_rate", "current_emr", "recordable_cases")):
        parts = []
        if wc.get("trir") is not None:
            parts.append(f"TRIR {_fmt_num(wc['trir'])}")
        if wc.get("dart_rate") is not None:
            parts.append(f"DART {_fmt_num(wc['dart_rate'])}")
        if wc.get("current_emr") is not None:
            parts.append(f"EMR {_fmt_num(wc['current_emr'])}")
        if wc.get("recordable_cases") is not None:
            parts.append(f"{wc['recordable_cases']} recordable case(s)")
        if wc.get("lost_days") is not None:
            parts.append(f"{wc['lost_days']} lost day(s)")
        if wc.get("severity_band"):
            parts.append(f"severity band {_hum(wc['severity_band'])}")
        add("platform:wc", "Workers' comp metrics", "; ".join(parts) + ".")

    # EPL — headline + per-factor sub-records
    epl = ctx.get("epl") or {}
    if epl.get("score") is not None:
        add("platform:epl", "EPL readiness",
            f"EPL readiness score {epl['score']} (band {_hum(epl.get('band')) or '—'}).")
        for f in epl.get("factors") or []:
            key = f.get("key") or f.get("item_key")
            if not key:
                continue
            status = f.get("status") or ("met" if f.get("met") else f.get("value"))
            add(f"platform:epl.{key}", f"EPL factor — {_hum(key)}",
                f"{_hum(key)}: {_hum(status) or 'status unknown'}"
                + (f" ({f['note']})" if f.get("note") else "") + ".")

    # Controls (tenant only)
    controls = (ctx.get("controls") or {}).get("controls") or []
    if controls:
        verified = sum(1 for c in controls if (c.get("status") or "") == "verified")
        add("platform:controls", "Proof of controls",
            f"{len(controls)} risk control(s) compiled; {verified} verified by the company.")

    # Submission readiness (tenant only)
    readiness = ctx.get("readiness") or {}
    if readiness.get("score") is not None:
        missing = readiness.get("items") or readiness.get("missing") or []
        open_items = [i for i in missing if isinstance(i, dict) and not i.get("complete", i.get("done"))]
        add("platform:readiness", "Submission readiness",
            f"Underwriting-data completeness {readiness['score']}/100"
            f" (band {_hum(readiness.get('band')) or '—'})"
            + (f"; {len(open_items)} item(s) outstanding" if open_items else "") + ".")

    # Venue severity
    venue = ctx.get("venue") or {}
    locs = venue.get("locations") or []
    if locs:
        tiers = {str(l.get("tier") or "").strip() for l in locs if isinstance(l, dict) and l.get("tier")}
        add("platform:venue", "Venue severity",
            f"{len(locs)} location(s) venue-scored"
            + (f"; tiers on file: {', '.join(sorted(tiers))}" if tiers else "") + ".")

    # Limit adequacy — per-line sub-records. build_review emits each line as
    # {key, label, carried{...}|None, contract_required{...}|None, gap: str|None,
    #  endorsement_gaps: [...]} (limit_adequacy.py lines_out).
    limits = ctx.get("limits") or {}
    for ln in limits.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        line = ln.get("key")
        label = ln.get("label") or _hum(line)
        carried = ln.get("carried") or {}
        if not line or not (carried or ln.get("contract_required")):
            continue
        bits = []
        if carried.get("per_occurrence") is not None:
            bits.append(f"carried ${_fmt_num(carried['per_occurrence'])}/occ")
        if carried.get("aggregate") is not None:
            bits.append(f"${_fmt_num(carried['aggregate'])} agg")
        if carried.get("carrier"):
            bits.append(f"carrier {carried['carrier']}")
        if carried.get("expiry_date"):
            bits.append(f"expires {carried['expiry_date']}")
        req = ln.get("contract_required") or {}
        if isinstance(req, dict) and req.get("per_occurrence"):
            bits.append(f"contracts require ${_fmt_num(req['per_occurrence'])}/occ")
        if ln.get("gap"):
            bits.append(str(ln["gap"]))
        if ln.get("endorsement_gaps"):
            bits.append(f"{len(ln['endorsement_gaps'])} endorsement gap(s)")
        add(f"platform:limits.{_slug(line)}", f"Coverage line — {label}",
            f"{label}: {'; '.join(bits) or 'recorded, no figures on file'}.")

    # Exclusion gaps
    exclusions = (ctx.get("exclusions") or {}).get("exclusions") or []
    for i, ex in enumerate(exclusions):
        if not isinstance(ex, dict):
            continue
        name = ex.get("name") or ex.get("exclusion") or f"exclusion {i + 1}"
        add(f"platform:exclusions.{i}", f"Exclusion exposure — {_hum(name)}",
            f"{_hum(name)}: {ex.get('why') or ex.get('detail') or 'flagged for this industry/state'}.")

    # Loss development — per line+period sub-records. build_development emits
    # periods as {period_label, points: [{paid, reserved, incurred, claim_count,
    # open_count, ...}], latest_incurred, ultimate, adverse_development}
    # (loss_development.py build_triangle).
    lossdev = ctx.get("loss_development") or {}
    for ln in lossdev.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        line = ln.get("line") or "wc"
        for p in ln.get("periods") or []:
            if not isinstance(p, dict) or not p.get("period_label"):
                continue
            label = p["period_label"]
            latest = (p.get("points") or [{}])[-1]
            bits = []
            if latest.get("claim_count") is not None:
                bits.append(f"{latest['claim_count']} claim(s)")
            if latest.get("open_count") is not None:
                bits.append(f"{latest['open_count']} open")
            if latest.get("paid") is not None:
                bits.append(f"paid ${_fmt_num(latest['paid'])}")
            if p.get("latest_incurred") is not None:
                bits.append(f"incurred ${_fmt_num(p['latest_incurred'])}")
            if p.get("ultimate") is not None:
                bits.append(f"projected ultimate ${_fmt_num(p['ultimate'])}")
            add(f"platform:lossdev.{_slug(line)}.{_slug(label)}",
                f"Loss history — {_hum(line)} {label}",
                f"{_hum(line)} policy period {label}: {'; '.join(bits) or 'on file'}.",
                when=str(label))

    # Property
    prop = ctx.get("property") or {}
    rollup = prop.get("rollup") or prop if isinstance(prop, dict) else {}
    if isinstance(rollup, dict) and (rollup.get("building_count") or rollup.get("total_tiv")):
        bits = []
        if rollup.get("building_count"):
            bits.append(f"{rollup['building_count']} building(s)")
        if rollup.get("total_tiv"):
            bits.append(f"TIV ${_fmt_num(rollup['total_tiv'])}")
        if rollup.get("cope_grade") or rollup.get("worst_cope_grade"):
            bits.append(f"COPE grade {rollup.get('cope_grade') or rollup.get('worst_cope_grade')}")
        if rollup.get("insured_to_value_pct") is not None:
            bits.append(f"ITV {_fmt_num(rollup['insured_to_value_pct'])}%")
        add("platform:property", "Commercial property",
            f"Property on file: {'; '.join(bits)}.")

    # Property sub-structures — cat / exposure / plan / risk are computed by
    # `_tenant_context` alongside the rollup (submission.py) and were previously
    # dropped here, so the broker could read them in the packet PDF while the
    # chat could not cite them at all. Off-platform clients carry a flat
    # broker-entered snapshot under `property` with none of these keys, so every
    # guard below silently emits nothing for them (never a KeyError).
    prop = prop if isinstance(prop, dict) else {}
    cat = prop.get("cat")
    if isinstance(cat, dict) and cat.get("worst_tier"):
        bits = ["worst catastrophe tier " + _hum(cat["worst_tier"])
                + (f" ({_hum(cat['worst_peril'])})" if cat.get("worst_peril") else "")]
        if cat.get("buildings_total"):
            bits.append(f"{cat.get('severe_high_count') or 0} of {cat['buildings_total']}"
                        " building(s) at high or severe")
            if cat.get("buildings_geocoded") is not None:
                bits.append(f"{cat['buildings_geocoded']}/{cat['buildings_total']} geocoded")
        tiers = cat.get("by_peril")
        if isinstance(tiers, dict) and tiers:
            bits.append("tiers by peril: "
                        + ", ".join(f"{_hum(p)} {_hum(t)}" for p, t in sorted(tiers.items())))
        # A wind/wildfire tier is a directional baseline, not a hazard-agency
        # probability — say so, or it gets cited as if it were modeled.
        if cat.get("worst_peril_documented") is False:
            bits.append("the worst peril's tier is a directional baseline, "
                        "not a hazard-agency-documented probability")
        add("platform:property.cat", "Property catastrophe exposure", "; ".join(bits) + ".")

    exposure = prop.get("exposure")
    if isinstance(exposure, dict) and any(
            exposure.get(k) for k in ("total_aal", "worst_pml", "coinsurance_shortfall")):
        bits = []
        if exposure.get("total_aal"):
            bits.append(f"modeled AAL ${_fmt_num(exposure['total_aal'])}")
        if exposure.get("worst_pml"):
            bits.append(f"worst PML ${_fmt_num(exposure['worst_pml'])}"
                        + (f" ({_hum(exposure['worst_pml_peril'])})"
                           if exposure.get("worst_pml_peril") else ""))
        if exposure.get("coinsurance_shortfall"):
            bits.append(f"coinsurance shortfall ${_fmt_num(exposure['coinsurance_shortfall'])}")
        summary = "; ".join(bits) + "."
        if exposure.get("basis"):
            summary += f" Basis: {exposure['basis']}."
        add("platform:property.exposure", "Property modeled exposure", summary)

    plan = prop.get("plan")
    fixes = plan.get("fixes") if isinstance(plan, dict) else None
    # The cid keys on the fix's own key (+ its building), NOT its list position:
    # build_plan re-ranks by severity and $ impact on every corpus build, and the
    # corpus is rebuilt for each chat turn AND again at memo time. A positional
    # cid would silently point at a different fix once the ranking moved, and the
    # citation gate can't catch that — the id still resolves.
    plan_seen: dict[str, int] = {}
    for i, fx in enumerate(fixes or []):
        if not isinstance(fx, dict):
            continue
        label = fx.get("label") or _hum(fx.get("key")) or f"property fix {i + 1}"
        slug = _slug(fx.get("key") or label)
        if fx.get("building_id"):
            slug = f"{slug}.{_slug(fx['building_id'])}"
        n = plan_seen.get(slug, 0)
        plan_seen[slug] = n + 1
        if n:                      # same fix twice on one building — keep cids unique
            slug = f"{slug}-{n + 1}"
        bits = [f"severity {_hum(fx.get('severity')) or 'unrated'}"]
        if fx.get("impact"):
            bits.append(f"projected impact {fx['impact']}")
        if fx.get("detail"):
            bits.append(str(fx["detail"]))
        add(f"platform:property.plan.{slug}", f"Property fix — {label}",
            f"{label}: {'; '.join(bits)}.")

    prisk = prop.get("risk")
    if isinstance(prisk, dict) and prisk.get("score") is not None:
        bits = [f"TIV-weighted property risk score {prisk['score']}/100"]
        if prisk.get("grade"):
            bits.append(f"grade {prisk['grade']}")
        if prisk.get("risk_level"):
            bits.append(f"level {_hum(prisk['risk_level'])}")
        if prisk.get("rated") is not None:
            bits.append(f"{prisk['rated']} building(s) rated")
        top = next((t for t in (prisk.get("top_risks") or []) if isinstance(t, dict)), None)
        if top:
            bits.append(f"worst building {top.get('name') or 'unnamed'} at {top.get('score')}"
                        + (f" ({top['grade']})" if top.get("grade") else ""))
        add("platform:property.risk", "Property risk score", "; ".join(bits) + ".")

    # Fleet / driver risk — the commercial-auto input. Tenant only, and only
    # when the client owns `driver_risk` (`_tenant_context` gates the fetch).
    fleet = ctx.get("fleet") or {}
    fsum = fleet.get("summary") if isinstance(fleet, dict) else None
    if isinstance(fsum, dict) and fsum.get("total_drivers"):
        bits = [f"fleet grade {fsum.get('grade') or 'n/a'}",
                f"{fsum['total_drivers']} driver(s) on file",
                f"{fsum.get('clean', 0)} clean / {fsum.get('marginal', 0)} marginal / "
                f"{fsum.get('high_risk', 0)} high-risk"]
        if fsum.get("clean_pct") is not None:
            bits.append(f"{fsum['clean_pct']}% clean")
        if fsum.get("overdue_reviews"):
            bits.append(f"{fsum['overdue_reviews']} overdue MVR review(s)")
        add("platform:fleet", "Driver risk — fleet",
            "; ".join(bits) + ". Tiers are derived from employer-recorded MVR reviews, "
            "not a pulled motor-vehicle record — directional.")
        # Sub-records for the drivers that move an auto quote: high-risk first,
        # then marginal, capped. `build_fleet` already sorts worst-first. The cid
        # keys on the row id, not the list position, because the sort is by score
        # and re-runs on every corpus build (the `platform:property.plan.*`
        # lesson: a positional cid still resolves after a re-rank, just to a
        # different driver).
        rated = [d for d in (fleet.get("drivers") or [])
                 if isinstance(d, dict) and d.get("tier") in ("high_risk", "marginal")]
        if len(rated) > _FLEET_DRIVER_CAP:
            add("platform:fleet.truncated", "Driver risk — coverage note",
                f"{len(rated)} driver(s) are rated marginal or high-risk; the "
                f"{_FLEET_DRIVER_CAP} worst are itemized below. The fleet totals in "
                "`platform:fleet` count all of them.")
            rated = rated[:_FLEET_DRIVER_CAP]
        for d in rated:
            name = d.get("driver_name") or "Unnamed driver"
            dbits = [f"tier {_hum(d['tier'])}", f"severity score {d.get('score')}/100"]
            if d.get("license_status"):
                dbits.append(f"license {_hum(d['license_status'])}")
            if d.get("violation_count"):
                dbits.append(f"{d['violation_count']} moving violation(s)")
            if d.get("accident_count"):
                dbits.append(f"{d['accident_count']} accident(s)")
            if d.get("major_violation"):
                dbits.append("major violation (DUI/reckless)")
            if d.get("overdue"):
                dbits.append("MVR review overdue")
            add(f"platform:fleet.{_slug(d.get('id') or name)}", f"Driver — {name}",
                f"{name}: {'; '.join(dbits)}.",
                when=str(d.get("review_date") or "current"))

    # Schedule Intelligence — headline only (the tenant's own /schedule-
    # intelligence page has the drill-down). Tenant only, and only when the
    # client owns `schedule_intelligence` (`_tenant_context` gates the fetch).
    schedint = ctx.get("schedule_intelligence") or {}
    modules = schedint.get("modules") if isinstance(schedint, dict) else None
    if isinstance(modules, dict):
        inc = modules.get("incidents") or {}
        if not inc.get("suppressed") and inc.get("by_staffing"):
            under = (inc["by_staffing"] or {}).get("understaffed") or {}
            bits = [f"{under.get('incidents', 0)} incident(s) on {under.get('shifts', 0)} "
                    f"understaffed shift(s) (rate {under.get('incident_rate')})"]
        else:
            bits = [f"{inc.get('n_incidents', 0)} incident(s) across "
                    f"{inc.get('n_shifts', 0)} scheduled shift(s) — too few for a rate"]
        fw = modules.get("fair_workweek") or {}
        if fw.get("total_exposure_estimate") is not None:
            bits.append(f"Fair Workweek exposure estimate ${fw['total_exposure_estimate']:,.2f} "
                        f"across {fw.get('location_count', 0)} location(s)")
        elif fw.get("location_count"):
            bits.append(f"{fw['location_count']} location(s) under a Fair Workweek ordinance "
                        "(no priced events this window)")
        cov = modules.get("coverage") or {}
        if cov.get("shifts_with_lapses"):
            bits.append(f"{cov['shifts_with_lapses']} upcoming shift(s) with a qualified-"
                        "coverage gap (credential/training lapse)")
        add("platform:schedule", "Schedule Intelligence — staffing risk",
            "; ".join(bits) + ". Directional estimate computed from the tenant's own "
            "scheduling data — not a causal claim, payroll figure, or legal advice.")

    # Composite risk index — headline + per-component sub-records, mirroring the
    # EPL block above. Tenant only: `_external_context` has no company row to
    # compute it from, so the key is simply absent for off-platform clients.
    risk = ctx.get("risk_index") or {}
    if isinstance(risk, dict) and risk.get("index") is not None:
        bits = [f"composite risk index {risk['index']}/100"]
        if risk.get("band"):
            bits.append(f"band {_hum(risk['band'])}")
        if risk.get("index_low") is not None and risk.get("index_high") is not None:
            bits.append(f"uncertainty band {risk['index_low']}–{risk['index_high']}")
        if risk.get("index_confidence"):
            bits.append(f"{_hum(risk['index_confidence'])} confidence")
        if risk.get("coverage") is not None:
            try:
                bits.append(f"{round(float(risk['coverage']) * 100)}% of component weight scored")
            except (TypeError, ValueError):
                pass
        missing = [m.get("label") or _hum(m.get("key"))
                   for m in (risk.get("components_missing") or []) if isinstance(m, dict)]
        if missing:
            bits.append("not scored: " + ", ".join(m for m in missing if m))
        add("platform:risk", "Composite risk index", "; ".join(bits) + ".")
        for c in risk.get("components") or []:
            if not isinstance(c, dict) or not c.get("key") or c.get("score") is None:
                continue
            label = c.get("label") or _hum(c["key"])
            cbits = [f"score {c['score']}/100", f"weight {c.get('weight')}"]
            if c.get("confidence"):
                cbits.append(f"{_hum(c['confidence'])} confidence")
            if c.get("detail"):
                cbits.append(str(c["detail"]))
            add(f"platform:risk.{_slug(c['key'])}", f"Risk index component — {label}",
                f"{label}: {'; '.join(cbits)}.")

    return recs


def _doc_records(docs: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """(doc records, docfig records, notes) for the corpus. `docs` are
    broker_pilot_documents rows (dicts; `extraction` may be a JSON string)."""
    doc_recs, fig_recs, notes = [], [], []
    for d in docs or []:
        status = d.get("status") or "processing"
        name = d.get("filename") or "document"
        if status == "failed":
            notes.append(f"Document '{name}' failed processing and is not in scope.")
            continue
        if status == "processing":
            notes.append(f"Document '{name}' is still processing and is not in scope.")
            continue
        ext = d.get("extraction")
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}
        ext = ext or {}
        did = str(d.get("id"))
        when = ext.get("period_label") or ext.get("effective_date") or _fmt_dt(d.get("created_at"))
        if status == "text_only" or not ext.get("summary"):
            summary = (f"Uploaded document '{name}' (classification unavailable — "
                       "raw text included below).")
        else:
            bits = [ext["summary"]]
            if ext.get("carrier"):
                bits.append(f"Carrier: {ext['carrier']}.")
            if ext.get("notable"):
                bits.append("Notable: " + "; ".join(ext["notable"]) + ".")
            summary = " ".join(bits)
        doc_recs.append({
            "cid": f"doc:{did}",
            "ref": ext.get("title") or name,
            "summary": summary,
            "when": str(when or "—"),
        })
        for n, f in enumerate(ext.get("key_figures") or []):
            fig_recs.append({
                "cid": f"docfig:{did}.{n}",
                "ref": f"{ext.get('title') or name} — {f.get('label')}",
                "summary": f"{f.get('label')}: {f.get('value')}"
                           + (f" ({f['context']})" if f.get("context") else ""),
                "when": str(when or "—"),
            })
    return doc_recs, fig_recs, notes


# Native operational records are leaner than Legal Pilot's 100/source — this
# corpus also carries the analytics aggregates and uploaded documents.
_NATIVE_PER_SOURCE_CAP = 50


# Legal Pilot sources that must NOT reach a broker chat. `gather_native_sources`
# iterates `legal_defense._SOURCES` wholesale, so anything added there lands here
# by default — right for agency charges and the termination-lifecycle records
# (core EPL underwriting context, and brokers already see named discipline
# records), wrong for leave: who took FMLA is medical-adjacent and belongs to the
# legal-defense corpus only. The filter lives here, not in the `_SOURCES` tuple,
# because it is a broker-side policy and two call sites unpack that tuple as a
# 4-tuple.
_BROKER_EXCLUDED_SOURCES = {"leave"}


async def gather_native_sources(conn, company_id) -> dict:
    """The operational records the platform natively generates for an
    on-platform company — IR/OSHA incidents, ER cases, compliance, discipline,
    training, policy acks, accommodations — reusing Legal Pilot's per-subsystem
    gatherers (same record shape, whole-company scope, feature-gated).

    Returns ``{"sources": {key: {label, records}}, "notes": [...]}``.
    Best-effort at every level: a failed gatherer degrades to a note, a total
    failure returns empty — the chat still grounds on analytics + documents.
    """
    from app.core.feature_flags import merge_company_features
    from app.matcha.services.pilots import legal_defense as ldef

    sources: dict = {}
    notes: list[str] = []
    try:
        row = await conn.fetchrow(
            "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id
        )
        features = merge_company_features(row["enabled_features"], row["signup_source"]) if row else {}
        for key, label, fn, enabled in ldef._SOURCES:
            if key in _BROKER_EXCLUDED_SOURCES or not enabled(features):
                continue
            try:
                recs = await fn(conn, company_id, None, None, None, None)
            except Exception as e:  # noqa: BLE001 — isolation is the point
                logger.warning("broker_pilot: native source %s unavailable: %s", key, e)
                notes.append(f"{label}: unavailable")
                continue
            if not recs:
                continue
            if len(recs) > _NATIVE_PER_SOURCE_CAP:
                notes.append(f"{label}: showing {_NATIVE_PER_SOURCE_CAP} most recent of {len(recs)}")
                recs = recs[:_NATIVE_PER_SOURCE_CAP]
            sources[key] = {"label": label, "records": recs}
    except Exception:  # noqa: BLE001 - degrade to analytics-only grounding
        logger.exception("broker_pilot: native gather failed for company %s", company_id)
        return {"sources": {}, "notes": ["Platform operational records: unavailable"]}
    return {"sources": sources, "notes": notes}


def _jurisdiction_records(index: dict) -> list[dict]:
    """Reshape `er_compliance_grounding.build_jurisdiction_corpus`'s flat index
    (``jur:<id>`` → {cid, requirement_id, state, category, title, description,
    statute_citation, source_url}) into corpus records (`{cid, ref, summary,
    when}`), the same shape every other source uses.

    ``summary`` mirrors ER's own corpus line — ``(STATE — category) title:
    description Citation: x`` — because `_corpus_text` renders ONLY `summary`
    (`ref` reaches the memo appendix, never the prompt). Two consequences are
    load-bearing: the **state** must be in the summary or a multi-state client's
    federal and per-state rows are byte-identical to the model, which then
    attributes one state's rule to another; and the **description** must be
    there or the model has a real cid with no statement of what the law
    requires, so it supplies the rule from its own weights while citing a
    genuine ID — the one hallucination `validate_citations` cannot catch.

    ``source_url`` rides along for the appendix (extra keys flow through
    `build_corpus`'s `{**r}` into the index untouched).

    Pure. Empty index → []."""
    recs: list[dict] = []
    for rec in (index or {}).values():
        state = (rec.get("state") or "").strip().upper() or "—"
        category = (rec.get("category") or "").strip()
        title = (rec.get("title") or "Requirement").strip()
        desc = (rec.get("description") or "").strip()
        citation = (rec.get("statute_citation") or "").strip() or "uncited"
        body = f"{title}: {desc}" if desc else title
        recs.append({
            "cid": rec["cid"],
            "ref": f"{state} — {title}",
            "summary": f"({state} — {category}) {body} Citation: {citation}",
            "when": "current",
            "source_url": rec.get("source_url") or None,
        })
    return recs


def build_corpus(subject_name: str, ctx: dict, docs: list[dict], native: dict | None = None,
                 jurisdiction: list[dict] | None = None,
                 jurisdiction_truncated: bool = False) -> dict:
    """Assemble the grounding corpus: `{sources, index, notes}` — the same shape
    Legal Pilot's `gather_evidence` returns, so `validate_citations` and the
    memo renderer work unchanged.

    ``native`` is the platform-generated operational corpus from
    ``gather_native_sources`` (company subjects only); None for off-platform
    clients, which instead get a note naming what an on-platform client adds.

    ``jurisdiction`` is the codified statutory-obligation corpus (``jur:`` cids)
    from ``_jurisdiction_records`` (company subjects only); empty/None for
    off-platform clients. It flows into the flat index like every other source,
    so the shared ``validate_citations`` gates ``jur:`` cids automatically.
    """
    platform = _platform_records(ctx)
    clauses = _clause_records(ctx)
    doc_recs, fig_recs, notes = _doc_records(docs)
    sources = {
        "platform": {"label": "Platform data on file", "records": platform},
    }
    if clauses:
        sources["clauses"] = {"label": "Contract indemnity clauses", "records": clauses}
    if jurisdiction:
        sources["jurisdiction"] = {"label": "Codified compliance obligations", "records": jurisdiction}
    if native is not None:
        sources.update(native.get("sources") or {})
        notes.extend(native.get("notes") or [])
    sources["documents"] = {"label": "Uploaded documents", "records": doc_recs}
    sources["doc_figures"] = {"label": "Key figures extracted from documents", "records": fig_recs}
    if not platform:
        notes.append("No platform data on file for this client yet.")
    if native is not None and not jurisdiction:
        # On-platform client (native is the company-subject signal) whose
        # codified grounding came back empty — no work states resolved, the
        # catalog held nothing for them, or the lookup failed. Say so: `_SYSTEM`
        # tells the model `jur:` records are present for on-platform clients, so
        # without this the broker reads a confident analysis with no statutory
        # grounding and no indication any was expected.
        notes.append(
            "Codified statutory obligations (`jur:`) are unavailable for this client — "
            "no work states resolved, or no codified requirements on file for them. "
            "Employment-law points in this analysis are NOT grounded in the statute catalog."
        )
    if jurisdiction and jurisdiction_truncated:
        # The catalog held more than the corpus cap. Say so, or the obligations
        # that fell off the LIMIT read as obligations that do not exist.
        notes.append(
            f"Codified statutory obligations were truncated to the first {len(jurisdiction)} "
            "records — this client has more codified obligations than are grounded here."
        )
    if native is None:
        notes.append(
            "Off-platform client: only broker-entered records ground this analysis. "
            "On-platform clients add native operational history — incidents, ER cases, "
            "compliance, discipline, training, policy acknowledgments."
        )
    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}
    return {"sources": sources, "index": index, "notes": notes}
