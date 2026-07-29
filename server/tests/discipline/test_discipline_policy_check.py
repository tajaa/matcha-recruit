"""discipline_policy_check: reports candidate policy violations, never
adjudicates; citation-gated; never raises.

    cd server && ./venv/bin/python -m pytest tests/discipline/test_discipline_policy_check.py -q
"""

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
        "sources": {}, "full_text": {"handbook:1": "Sharps must be disposed of in a sharps container."},
        "index": {"handbook:1": {"title": "Sharps Handling", "summary": "Sharps policy"}},
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
