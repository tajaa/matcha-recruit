"""discipline_policy_check: reports candidate policy violations, never
adjudicates; citation-gated; never raises.

    cd server && ./venv/bin/python -m pytest tests/discipline/test_discipline_policy_check.py -q
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.matcha.services.discipline import discipline_policy_check as dpc

MOD = "app.matcha.services.discipline.discipline_policy_check"

INCIDENT = {
    "id": "inc-1", "title": "Needlestick", "description": "RDA stuck by contaminated needle.",
    "incident_type": "safety", "severity": "high",
}


def _fake_corpus():
    return {
        # "source": "existing_handbook" mirrors what handbook_pilot.build_corpus
        # actually stamps on every index record — _restrict_to_handbook_and_policy
        # filters on it, so a fixture without it would look like an empty
        # (law/playbook-only) corpus and short-circuit before Gemini is called.
        "sources": {
            "existing_handbook": {"label": "Existing handbook sections", "records": [
                {"cid": "handbook:1", "title": "Sharps Handling", "summary": "Sharps policy", "ref": None},
            ]},
        },
        "full_text": {"handbook:1": "Sharps must be disposed of in a sharps container."},
        "index": {"handbook:1": {"title": "Sharps Handling", "summary": "Sharps policy", "source": "existing_handbook"}},
    }


def _fake_resp(text):
    resp = MagicMock()
    resp.text = text
    return resp


@pytest.fixture
def patch_grounding(monkeypatch):
    hp_mod = MagicMock()
    hp_mod.gather_grounding = AsyncMock(return_value={"raw": True})
    hp_mod.build_corpus = MagicMock(return_value=_fake_corpus())
    monkeypatch.setattr("app.matcha.services.pilots.handbook_pilot.gather_grounding", hp_mod.gather_grounding)
    monkeypatch.setattr("app.matcha.services.pilots.handbook_pilot.build_corpus", hp_mod.build_corpus)
    monkeypatch.setattr(
        "app.matcha.services.pilots.hr_pilot_corpus.render_corpus_block",
        MagicMock(return_value="[handbook:1] Sharps Handling"),
    )
    return hp_mod


class TestCheckIncidentAgainstHandbook:
    @pytest.mark.asyncio
    async def test_reports_never_adjudicates(self, monkeypatch, patch_grounding):
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(return_value=_fake_resp(json.dumps({
            "violations": [{
                "policy_cid": "handbook:1", "policy_title": "Sharps Handling", "relevance": "violated",
                "confidence": 0.9, "reasoning": "Needle not disposed of properly.",
            }],
            "summary": "Likely sharps-handling violation.",
        })))
        # NOTE: validate_citations is deliberately NOT patched here or below. It was,
        # and the fake matched a contract the real function doesn't have ({"cid"} instead
        # of {"point", "cited_ids"}), so both citation tests passed against code that
        # raised KeyError the moment the model returned a violation. The real gate is
        # pure and DB-free — there is nothing to fake.
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        result = await dpc.check_incident_against_handbook(MagicMock(), company_id="c1", incident=INCIDENT)

        assert result["available"] is True
        assert len(result["violations"]) == 1
        v = result["violations"][0]
        assert "level" not in v and "legality" not in v and "discipline_type" not in v
        assert set(v.keys()) == {"policy_cid", "policy_title", "relevance", "confidence", "reasoning", "relevant_excerpt"}

    @pytest.mark.asyncio
    async def test_citation_gate_drops_unknown_ids(self, monkeypatch, patch_grounding):
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(return_value=_fake_resp(json.dumps({
            "violations": [
                {"policy_cid": "handbook:1", "policy_title": "Real", "relevance": "related", "confidence": 0.5, "reasoning": "ok"},
                {"policy_cid": "handbook:bogus", "policy_title": "Hallucinated", "relevance": "violated", "confidence": 0.9, "reasoning": "made up"},
            ],
            "summary": "mixed",
        })))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        result = await dpc.check_incident_against_handbook(MagicMock(), company_id="c1", incident=INCIDENT)

        assert len(result["violations"]) == 1
        assert result["violations"][0]["policy_cid"] == "handbook:1"
        assert "handbook:bogus" in result["dropped_citations"]
        assert result["citations"] == ["handbook:1"]

    @pytest.mark.asyncio
    async def test_evidence_map_matches_validate_citations_contract(self, monkeypatch, patch_grounding):
        """Pins the shape handed to the shared gate. The gate reads item['cited_ids']
        and returns entries keyed on point/cited_ids — a {'cid': ...} map silently
        drops every citation and then KeyErrors on the way out."""
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(return_value=_fake_resp(json.dumps({
            "violations": [{"policy_cid": "handbook:1", "policy_title": "Real",
                            "relevance": "related", "confidence": 0.5, "reasoning": "ok"}],
            "summary": "one",
        })))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        real = dpc.validate_citations
        seen = {}

        def spy(evidence_map, index):
            seen["map"] = evidence_map
            return real(evidence_map, index)   # delegates to the REAL gate

        monkeypatch.setattr(f"{MOD}.validate_citations", spy)

        result = await dpc.check_incident_against_handbook(MagicMock(), company_id="c1", incident=INCIDENT)

        assert seen["map"] == [{"point": "ok", "cited_ids": ["handbook:1"]}]
        assert len(result["violations"]) == 1

    @pytest.mark.asyncio
    async def test_gemini_failure_degrades_available_false(self, monkeypatch, patch_grounding):
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("timeout"))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        result = await dpc.check_incident_against_handbook(MagicMock(), company_id="c1", incident=INCIDENT)

        assert result["available"] is False
        assert result["violations"] == []

    @pytest.mark.asyncio
    async def test_grounding_failure_never_raises(self, monkeypatch):
        monkeypatch.setattr(
            "app.matcha.services.pilots.handbook_pilot.gather_grounding",
            AsyncMock(side_effect=RuntimeError("db down")),
        )
        result = await dpc.check_incident_against_handbook(MagicMock(), company_id="c1", incident=INCIDENT)
        assert result["available"] is False

    @pytest.mark.asyncio
    async def test_empty_corpus_index_skips_gemini_call(self, monkeypatch):
        monkeypatch.setattr(
            "app.matcha.services.pilots.handbook_pilot.gather_grounding",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            "app.matcha.services.pilots.handbook_pilot.build_corpus",
            MagicMock(return_value={"sources": {}, "index": {}, "full_text": {}}),
        )
        genai_call = MagicMock()
        monkeypatch.setattr(f"{MOD}._genai", genai_call)

        result = await dpc.check_incident_against_handbook(MagicMock(), company_id="c1", incident=INCIDENT)

        assert result["available"] is True
        assert result["violations"] == []
        genai_call.assert_not_called()


class TestCidRepair:
    """Found running this against a live tenant: the corpus renders
    `[policy:<uuid>]` and Gemini answered with the bare `<uuid>`. The gate
    correctly dropped both citations, every finding went with them, and the
    incident persisted as `no_matching_policies` — reading as CLEAN while the
    model had in fact identified the two right policies. A silent wrong answer
    on a legal record, so the prefix is repaired rather than left to prompt luck.
    """

    INDEX = {
        "policy:75ff0df2": {"title": "Sharps Handling"},
        "handbook:aaaa1111": {"title": "PPE"},
        "law:ca-sharps": {"title": "CA sharps rule"},
    }

    def test_bare_id_is_repaired_to_its_prefixed_cid(self):
        assert dpc._resolve_cid("75ff0df2", self.INDEX) == "policy:75ff0df2"

    def test_already_correct_cid_is_untouched(self):
        assert dpc._resolve_cid("policy:75ff0df2", self.INDEX) == "policy:75ff0df2"

    def test_unknown_id_is_left_for_the_gate_to_drop(self):
        """The repair must not become a way in for an invented id."""
        assert dpc._resolve_cid("totally-made-up", self.INDEX) == "totally-made-up"

    def test_ambiguous_bare_id_is_refused(self):
        """Same uuid under two namespaces: guessing one would be a citation the
        model never made."""
        index = {"policy:dupe": {}, "handbook:dupe": {}}
        assert dpc._resolve_cid("dupe", index) == "dupe"

    @pytest.mark.asyncio
    async def test_bare_ids_survive_the_full_path(self, monkeypatch, patch_grounding):
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(return_value=_fake_resp(json.dumps({
            "violations": [{
                "policy_cid": "1",  # the corpus record is `handbook:1` — prefix dropped
                "policy_title": "Sharps Handling", "relevance": "violated",
                "confidence": 0.9, "reasoning": "sharps left loose",
            }],
            "summary": "match",
        })))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        result = await dpc.check_incident_against_handbook(MagicMock(), company_id="c1", incident=INCIDENT)

        assert result["citations"] == ["handbook:1"]
        assert result["dropped_citations"] == []
        assert len(result["violations"]) == 1


class TestTitleCleaning:
    """The corpus labels a record "Existing policy — X" for its citation footer.
    That title travels into a disciplinary LETTER and the sweep briefing, where
    it read "POLICY IMPLICATED: Existing policy — Sharps Handling"."""

    def test_strips_the_corpus_provenance_label(self):
        assert dpc._clean_title("Existing policy — Sharps Handling") == "Sharps Handling"
        assert dpc._clean_title("Existing section — PPE") == "PPE"

    def test_leaves_an_ordinary_title_alone(self):
        assert dpc._clean_title("Sharps Handling") == "Sharps Handling"

    def test_does_not_eat_an_em_dash_inside_a_real_title(self):
        title = "Sharps Handling — Bloodborne Pathogen Exposure Control"
        assert dpc._clean_title(title) == title


class TestPersistPolicyCheck:
    @pytest.mark.asyncio
    async def test_preserves_policy_mapping_reader_contract(self):
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value=None)

        result = {
            "violations": [{
                "policy_cid": "handbook:1", "policy_title": "Sharps Handling", "relevance": "violated",
                "confidence": 0.9, "reasoning": "reason", "relevant_excerpt": None,
            }],
            "citations": ["handbook:1"], "dropped_citations": [], "summary": "found one match", "available": True,
        }

        await dpc.persist_policy_check(conn, incident_id="inc-1", result=result)

        assert conn.execute.await_count == 1
        query, incident_id, payload_json = conn.execute.await_args.args
        assert "ir_incident_analysis" in query
        assert "policy_mapping" in query
        payload = json.loads(payload_json)
        for key in ("matches", "summary", "no_matching_policies", "generated_at"):
            assert key in payload
        assert payload["citations"] == ["handbook:1"]
        assert payload["dropped_citations"] == []
        assert payload["checked_by"] == "discipline_policy_check"
        assert payload["matches"][0]["policy_id"] == "handbook:1"

    @pytest.mark.asyncio
    async def test_preserves_prior_statute_fields_when_upserting(self):
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value=json.dumps({
            "statute_matches": [{"requirement_id": "r1"}], "statute_states": ["CA"],
        }))
        conn.execute = AsyncMock(return_value=None)

        await dpc.persist_policy_check(
            conn, incident_id="inc-1",
            result={"violations": [], "citations": [], "dropped_citations": [], "summary": "", "available": True},
        )

        _, _, payload_json = conn.execute.await_args.args
        payload = json.loads(payload_json)
        assert payload["statute_states"] == ["CA"]


def _fake_conn():
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)
    return conn


class TestCheckIncidentsAgainstHandbookBatch:
    """find_discipline_candidates' batch path: one corpus build for the whole
    batch, per-incident failure isolation, and a total-corpus-failure
    fallback — all `check_incident_against_handbook`'s single-incident path
    doesn't need to care about."""

    @pytest.mark.asyncio
    async def test_batch_builds_corpus_once(self, monkeypatch, patch_grounding):
        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(return_value=_fake_resp(json.dumps({
            "violations": [], "summary": "clean",
        })))
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        incidents = [
            {**INCIDENT, "id": "inc-1"}, {**INCIDENT, "id": "inc-2"}, {**INCIDENT, "id": "inc-3"},
        ]
        conn = _fake_conn()
        results = await dpc.check_incidents_against_handbook(conn, company_id="c1", incidents=incidents)

        assert patch_grounding.build_corpus.call_count == 1
        assert set(results.keys()) == {"inc-1", "inc-2", "inc-3"}
        assert genai.aio.models.generate_content.await_count == 3

    @pytest.mark.asyncio
    async def test_batch_one_gemini_failure_degrades_only_that_incident(self, monkeypatch, patch_grounding):
        genai = MagicMock()
        ok_resp = _fake_resp(json.dumps({"violations": [], "summary": "clean"}))
        genai.aio.models.generate_content = AsyncMock(side_effect=[ok_resp, RuntimeError("timeout"), ok_resp])
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        incidents = [
            {**INCIDENT, "id": "inc-1"}, {**INCIDENT, "id": "inc-2"}, {**INCIDENT, "id": "inc-3"},
        ]
        conn = _fake_conn()
        results = await dpc.check_incidents_against_handbook(conn, company_id="c1", incidents=incidents, concurrency=1)

        available = {k: r["available"] for k, r in results.items()}
        assert available == {"inc-1": True, "inc-2": False, "inc-3": True}

    @pytest.mark.asyncio
    async def test_batch_corpus_failure_degrades_all(self, monkeypatch):
        monkeypatch.setattr(
            "app.matcha.services.pilots.handbook_pilot.gather_grounding",
            AsyncMock(side_effect=RuntimeError("db down")),
        )
        incidents = [{**INCIDENT, "id": "inc-1"}, {**INCIDENT, "id": "inc-2"}]
        conn = _fake_conn()

        results = await dpc.check_incidents_against_handbook(conn, company_id="c1", incidents=incidents)

        assert all(r == {"violations": [], "citations": [], "dropped_citations": [], "summary": "", "available": False}
                   for r in results.values())

    @pytest.mark.asyncio
    async def test_only_available_results_are_persisted(self, monkeypatch, patch_grounding):
        genai = MagicMock()
        ok_resp = _fake_resp(json.dumps({"violations": [], "summary": "clean"}))
        genai.aio.models.generate_content = AsyncMock(side_effect=[ok_resp, RuntimeError("boom")])
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        incidents = [{**INCIDENT, "id": "inc-1"}, {**INCIDENT, "id": "inc-2"}]
        conn = _fake_conn()
        await dpc.check_incidents_against_handbook(conn, company_id="c1", incidents=incidents, concurrency=1)

        # persist_policy_check calls conn.execute once per available result —
        # the unavailable incident must not get a row written for it.
        assert conn.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_batch_malformed_confidence_degrades_only_that_incident(self, monkeypatch, patch_grounding):
        """A malformed `confidence` field (untrusted model output — e.g. a
        string instead of a number) used to raise OUTSIDE _check_one's try,
        which asyncio.gather (no return_exceptions) propagated out of the
        whole batch, taking every other incident's already-good result down
        with it. Must degrade only the one incident now."""
        genai = MagicMock()
        ok_resp = _fake_resp(json.dumps({"violations": [], "summary": "clean"}))
        bad_resp = _fake_resp(json.dumps({
            "violations": [{
                "policy_cid": "handbook:1", "policy_title": "Sharps Handling",
                "relevance": "violated", "confidence": "high", "reasoning": "not a number",
            }],
            "summary": "bad",
        }))
        genai.aio.models.generate_content = AsyncMock(side_effect=[ok_resp, bad_resp, ok_resp])
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        incidents = [
            {**INCIDENT, "id": "inc-1"}, {**INCIDENT, "id": "inc-2"}, {**INCIDENT, "id": "inc-3"},
        ]
        conn = _fake_conn()
        results = await dpc.check_incidents_against_handbook(conn, company_id="c1", incidents=incidents, concurrency=1)

        available = {k: r["available"] for k, r in results.items()}
        assert available == {"inc-1": True, "inc-2": False, "inc-3": True}

    @pytest.mark.asyncio
    async def test_budget_seconds_returns_and_persists_partial_batch(self, monkeypatch, patch_grounding):
        """`budget_seconds` must be an INTERNAL deadline: a slow incident past
        the budget is left out of the result (never cancelled mid-persist),
        and whatever already completed is both returned AND persisted — not
        thrown away because the whole call would otherwise look "timed out"
        to an external asyncio.wait_for."""
        call_count = 0

        async def _generate(*, model, contents):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fake_resp(json.dumps({"violations": [], "summary": "clean"}))
            await asyncio.sleep(10)  # never resolves within the test's budget
            return _fake_resp(json.dumps({"violations": [], "summary": "clean"}))

        genai = MagicMock()
        genai.aio.models.generate_content = AsyncMock(side_effect=_generate)
        monkeypatch.setattr(f"{MOD}._genai", MagicMock(return_value=genai))

        incidents = [{**INCIDENT, "id": "inc-1"}, {**INCIDENT, "id": "inc-2"}]
        conn = _fake_conn()

        results = await dpc.check_incidents_against_handbook(
            conn, company_id="c1", incidents=incidents, concurrency=2, budget_seconds=0.05,
        )

        assert results.get("inc-1", {}).get("available") is True
        assert "inc-2" not in results  # budget expired before its task finished
        # Only inc-1's (available) result was persisted — the cutoff didn't
        # discard work that had already completed and been billed.
        assert conn.execute.await_count == 1
