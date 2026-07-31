"""Tests for services/huume/ir_skill.py — the IR Copilot chat bridge and
analysis-runner tools (fake conn, no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_ir_skill.py -q

Symbols ir_skill.py lazily imports (log_audit, parse_witnesses,
get_ir_analyzer, the ir_ai_orchestrator functions) must be patched at their
DEFINING module — same rule as test_ems_skill.py's docstring. get_connection
IS a module-level import in ir_skill.py, patched directly on ir_skill.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services.rate_limiter import RateLimitExceeded
from app.matcha.services.huume import ir_skill

COMPANY_ID = uuid4()
ACTOR_ID = uuid4()
INCIDENT_ID = uuid4()


class _ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, *, incident_exists=True, cached_row=None, incident_row=None, incident_number="IR-2"):
        self.incident_exists = incident_exists
        self.cached_row = cached_row
        self.incident_row = incident_row
        self.incident_number = incident_number
        self.executed = []

    async def fetchval(self, query, *args):
        q = " ".join(query.split())
        if q.startswith("SELECT incident_number FROM ir_incidents WHERE id"):
            return self.incident_number if self.incident_exists else None
        if "FROM ir_incidents WHERE id" in q:
            return INCIDENT_ID if self.incident_exists else None
        raise AssertionError(f"unexpected fetchval: {q}")

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if "SELECT analysis_data FROM ir_incident_analysis" in q:
            return self.cached_row
        if "SELECT * FROM ir_incidents WHERE id" in q:
            return self.incident_row
        if "FROM companies WHERE id" in q or "FROM business_locations WHERE id" in q:
            return None
        raise AssertionError(f"unexpected fetchrow: {q}")

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "INSERT 0 1"


def _patch_conn(monkeypatch, conn):
    monkeypatch.setattr(ir_skill, "get_connection", lambda: _ConnCtx(conn))


def _patch_log_audit(monkeypatch):
    import app.matcha.routes.ir_incidents._shared as shared
    mock = AsyncMock()
    monkeypatch.setattr(shared, "log_audit", mock)
    return mock


class TestResolveIncident:
    @pytest.mark.asyncio
    async def test_explicit_id_wins_over_state(self):
        conn = _FakeConn(incident_exists=True)
        iid, err = await ir_skill._resolve_incident(conn, COMPANY_ID, str(INCIDENT_ID), "different-state-id")
        assert err is None
        assert iid == INCIDENT_ID

    @pytest.mark.asyncio
    async def test_falls_back_to_state(self):
        conn = _FakeConn(incident_exists=True)
        iid, err = await ir_skill._resolve_incident(conn, COMPANY_ID, None, str(INCIDENT_ID))
        assert err is None
        assert iid == INCIDENT_ID

    @pytest.mark.asyncio
    async def test_neither_refuses_naming_both_options(self):
        conn = _FakeConn()
        iid, err = await ir_skill._resolve_incident(conn, COMPANY_ID, None, None)
        assert iid is None
        assert err and "promote" in err.lower()

    @pytest.mark.asyncio
    async def test_bad_uuid_refuses(self):
        conn = _FakeConn()
        iid, err = await ir_skill._resolve_incident(conn, COMPANY_ID, "not-a-uuid", None)
        assert iid is None
        assert err

    @pytest.mark.asyncio
    async def test_nonexistent_incident_refuses(self):
        conn = _FakeConn(incident_exists=False)
        iid, err = await ir_skill._resolve_incident(conn, COMPANY_ID, str(INCIDENT_ID), None)
        assert iid is None
        assert err


class TestAskCopilot:
    @pytest.mark.asyncio
    async def test_empty_question_refuses_without_touching_db(self, monkeypatch):
        # No get_connection patch — proves the guard runs before any DB call.
        result = await ir_skill.ask_copilot(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, question="   ",
        )
        assert result["status"] == "error"


class TestRunAnalysis:
    @pytest.mark.asyncio
    async def test_unknown_type_refuses_without_touching_db(self):
        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="similar",
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_analyzer(self, monkeypatch):
        conn = _FakeConn(incident_exists=True, cached_row={"analysis_data": '{"primary_cause": "cached"}'})
        _patch_conn(monkeypatch, conn)
        _patch_log_audit(monkeypatch)

        import app.matcha.services.ir.ir_analysis as ir_analysis
        analyzer_factory = AsyncMock()
        monkeypatch.setattr(ir_analysis, "get_ir_analyzer", analyzer_factory)

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="root_cause",
        )
        assert result["status"] == "ok"
        assert result["cached"] is True
        assert result["analysis"]["primary_cause"] == "cached"
        assert result["incident_number"] == "IR-2"
        analyzer_factory.assert_not_called()
        assert conn.executed == []

    @pytest.mark.asyncio
    async def test_incident_number_matches_resolved_incident_not_prior_state(self, monkeypatch):
        # Regression: agent.py used to fall back to the thread's PREVIOUS
        # huume_ir state for incident_number instead of trusting the
        # result of THIS call — wrong whenever an explicit incident_id
        # differs from what was previously active. run_analysis must
        # report the number for the incident it actually resolved.
        conn = _FakeConn(incident_exists=True, cached_row={"analysis_data": "{}"}, incident_number="IR-9")
        _patch_conn(monkeypatch, conn)

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="root_cause",
        )
        assert result["incident_number"] == "IR-9"

    @pytest.mark.asyncio
    async def test_upsert_uses_on_conflict(self, monkeypatch):
        incident_row = {
            "title": "Autoclave failure", "description": "Stopped mid-cycle.",
            "incident_type": "equipment", "severity": "medium", "location": None,
            "category_data": {}, "witnesses": [],
        }
        conn = _FakeConn(incident_exists=True, cached_row=None, incident_row=incident_row)
        _patch_conn(monkeypatch, conn)
        _patch_log_audit(monkeypatch)

        import app.matcha.services.ir.ir_analysis as ir_analysis

        class _FakeAnalyzer:
            async def analyze_root_cause(self, **kwargs):
                return {"primary_cause": "worn seal", "contributing_factors": [],
                        "prevention_suggestions": [], "reasoning": "x", "generated_at": "now"}

        monkeypatch.setattr(ir_analysis, "get_ir_analyzer", lambda: _FakeAnalyzer())

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="root_cause",
        )
        assert result["status"] == "ok"
        assert result["cached"] is False
        assert result["incident_number"] == "IR-2"
        assert len(conn.executed) == 1
        sql, _args = conn.executed[0]
        assert "ON CONFLICT (incident_id, analysis_type)" in " ".join(sql.split())

    @pytest.mark.asyncio
    async def test_refresh_bypasses_cache(self, monkeypatch):
        # cached_row is present, but refresh=True must skip the probe and
        # recompute — the plan's item 5 fix (no refresh param previously).
        incident_row = {
            "title": "Autoclave failure", "description": "Stopped mid-cycle.",
            "incident_type": "equipment", "severity": "medium", "location": None,
            "category_data": {}, "witnesses": [],
        }
        conn = _FakeConn(
            incident_exists=True,
            cached_row={"analysis_data": '{"primary_cause": "stale"}'},
            incident_row=incident_row,
        )
        _patch_conn(monkeypatch, conn)
        _patch_log_audit(monkeypatch)

        import app.matcha.services.ir.ir_analysis as ir_analysis

        class _FakeAnalyzer:
            async def analyze_root_cause(self, **kwargs):
                return {"primary_cause": "fresh", "contributing_factors": [],
                        "prevention_suggestions": [], "reasoning": "x", "generated_at": "now"}

        monkeypatch.setattr(ir_analysis, "get_ir_analyzer", lambda: _FakeAnalyzer())

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None,
            analysis_type="root_cause", refresh=True,
        )
        assert result["status"] == "ok"
        assert result["cached"] is False
        assert result["analysis"]["primary_cause"] == "fresh"

    @pytest.mark.asyncio
    async def test_missing_incident_row_returns_error_not_typeerror(self, monkeypatch):
        # incident_exists=True (passes _resolve_incident's own existence
        # check) but the SELECT * fetch itself returns None — a delete-mid-
        # turn race. dict(None) must not escape as a bare TypeError.
        conn = _FakeConn(incident_exists=True, cached_row=None, incident_row=None)
        _patch_conn(monkeypatch, conn)

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="root_cause",
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_rate_limit_returns_error_not_raise(self, monkeypatch):
        incident_row = {
            "title": "Autoclave failure", "description": "Stopped mid-cycle.",
            "incident_type": "equipment", "severity": "medium", "location": None,
            "category_data": {}, "witnesses": [],
        }
        conn = _FakeConn(incident_exists=True, cached_row=None, incident_row=incident_row)
        _patch_conn(monkeypatch, conn)

        import app.matcha.services.ir.ir_analysis as ir_analysis

        class _RateLimitedAnalyzer:
            async def analyze_root_cause(self, **kwargs):
                raise RateLimitExceeded("limited", "hourly", 10, 10)

        monkeypatch.setattr(ir_analysis, "get_ir_analyzer", lambda: _RateLimitedAnalyzer())

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="root_cause",
        )
        assert result["status"] == "error"
        assert "rate limit" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_recommendations_triggers_training_mapping(self, monkeypatch):
        incident_row = {
            "title": "Slip near dock", "description": "…", "incident_type": "safety",
            "severity": "medium", "root_cause": None, "company_id": COMPANY_ID, "location_id": None,
        }
        conn = _FakeConn(incident_exists=True, cached_row=None, incident_row=incident_row)
        _patch_conn(monkeypatch, conn)
        _patch_log_audit(monkeypatch)

        import app.matcha.services.ir.ir_analysis as ir_analysis
        import app.matcha.routes.ir_incidents.ai_analysis as ai_analysis

        class _FakeAnalyzer:
            async def generate_recommendations(self, **kwargs):
                return {
                    "recommendations": [], "summary": "x", "generated_at": "now",
                    "training_recommended": True, "training_topics": ["ppe"],
                }

        monkeypatch.setattr(ir_analysis, "get_ir_analyzer", lambda: _FakeAnalyzer())
        auto_map = AsyncMock()
        monkeypatch.setattr(ai_analysis, "_auto_map_training_topics", auto_map)

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="recommendations",
        )
        assert result["status"] == "ok"
        auto_map.assert_awaited_once_with(str(INCIDENT_ID), str(COMPANY_ID))

    @pytest.mark.asyncio
    async def test_recommendations_without_flag_skips_training_mapping(self, monkeypatch):
        incident_row = {
            "title": "Slip near dock", "description": "…", "incident_type": "safety",
            "severity": "medium", "root_cause": None, "company_id": COMPANY_ID, "location_id": None,
        }
        conn = _FakeConn(incident_exists=True, cached_row=None, incident_row=incident_row)
        _patch_conn(monkeypatch, conn)
        _patch_log_audit(monkeypatch)

        import app.matcha.services.ir.ir_analysis as ir_analysis
        import app.matcha.routes.ir_incidents.ai_analysis as ai_analysis

        class _FakeAnalyzer:
            async def generate_recommendations(self, **kwargs):
                return {"recommendations": [], "summary": "x", "generated_at": "now",
                        "training_recommended": False}

        monkeypatch.setattr(ir_analysis, "get_ir_analyzer", lambda: _FakeAnalyzer())
        auto_map = AsyncMock()
        monkeypatch.setattr(ai_analysis, "_auto_map_training_topics", auto_map)

        result = await ir_skill.run_analysis(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, analysis_type="recommendations",
        )
        assert result["status"] == "ok"
        auto_map.assert_not_awaited()


class TestAskCopilotAtomicity:
    @pytest.mark.asyncio
    async def test_failed_guidance_leaves_no_orphaned_user_turn(self, monkeypatch):
        # Regression for the plan's item 6: previously the user turn was
        # persisted before the Gemini call, so a failure left a question
        # with no answer in the incident's Copilot transcript. Now the user
        # turn only reaches the DB inside persist_assistant_round, which
        # must never be called on a guidance failure.
        conn = _FakeConn(incident_exists=True)
        _patch_conn(monkeypatch, conn)

        import app.matcha.services.ir.ir_ai_orchestrator as orch

        async def _load_incident_state(conn, iid, company_id):
            return {"id": str(INCIDENT_ID), "incident_number": "IR-1"}, [], []

        persist_mock = AsyncMock()
        monkeypatch.setattr(orch, "load_incident_state", _load_incident_state)
        monkeypatch.setattr(orch, "persist_assistant_round", persist_mock)

        async def _boom(**kwargs):
            raise RuntimeError("gemini down")

        monkeypatch.setattr(orch, "generate_guidance", _boom)

        result = await ir_skill.ask_copilot(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, question="what next?",
        )
        assert result["status"] == "error"
        persist_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_swallowed_gemini_failure_leaves_no_orphaned_user_turn(self, monkeypatch):
        # generate_guidance itself swallows Gemini timeouts/parse errors into
        # payload={} rather than raising (see ir_ai_orchestrator.py) — the
        # RuntimeError case above never fires for this failure mode.
        # persist_assistant_round would otherwise treat {} as "produced
        # nothing" and persist ONLY the user turn — the exact orphan this
        # class of test exists to prevent.
        conn = _FakeConn(incident_exists=True)
        _patch_conn(monkeypatch, conn)

        import app.matcha.services.ir.ir_ai_orchestrator as orch

        async def _load_incident_state(conn, iid, company_id):
            return {"id": str(INCIDENT_ID), "incident_number": "IR-1"}, [], []

        persist_mock = AsyncMock()
        monkeypatch.setattr(orch, "load_incident_state", _load_incident_state)
        monkeypatch.setattr(orch, "persist_assistant_round", persist_mock)

        async def _empty(**kwargs):
            return {}

        monkeypatch.setattr(orch, "generate_guidance", _empty)

        result = await ir_skill.ask_copilot(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, question="what next?",
        )
        assert result["status"] == "error"
        persist_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_limit_returns_error_not_raise(self, monkeypatch):
        conn = _FakeConn(incident_exists=True)
        _patch_conn(monkeypatch, conn)

        import app.matcha.services.ir.ir_ai_orchestrator as orch

        async def _load_incident_state(conn, iid, company_id):
            return {"id": str(INCIDENT_ID), "incident_number": "IR-1"}, [], []

        monkeypatch.setattr(orch, "load_incident_state", _load_incident_state)
        monkeypatch.setattr(orch, "persist_assistant_round", AsyncMock())

        async def _limited(**kwargs):
            raise RateLimitExceeded("limited", "hourly", 10, 10)

        monkeypatch.setattr(orch, "generate_guidance", _limited)

        result = await ir_skill.ask_copilot(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, question="what next?",
        )
        assert result["status"] == "error"
        assert "rate limit" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_success_persists_user_and_assistant_atomically(self, monkeypatch):
        conn = _FakeConn(incident_exists=True)
        _patch_conn(monkeypatch, conn)
        _patch_log_audit(monkeypatch)

        import app.matcha.services.ir.ir_ai_orchestrator as orch

        async def _load_incident_state(conn, iid, company_id):
            return {"id": str(INCIDENT_ID), "incident_number": "IR-1"}, [], []

        async def _generate_guidance(*, incident, analyses, messages):
            # The question must be visible in the messages passed to the
            # model even though it was never separately persisted first.
            assert any(m.get("role") == "user" and "what next" in m.get("content", "") for m in messages)
            return {"summary": "do X", "open_questions": [], "cards": []}

        persist_mock = AsyncMock()
        monkeypatch.setattr(orch, "load_incident_state", _load_incident_state)
        monkeypatch.setattr(orch, "generate_guidance", _generate_guidance)
        monkeypatch.setattr(orch, "persist_assistant_round", persist_mock)

        result = await ir_skill.ask_copilot(
            company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
            incident_id=str(INCIDENT_ID), state_incident_id=None, question="what next?",
        )
        assert result["status"] == "ok"
        persist_mock.assert_awaited_once()
        _, kwargs = persist_mock.call_args
        assert kwargs["user_message"] == "what next?"
