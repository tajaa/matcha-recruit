"""Context-management unit tests for Analysis Pilot chat (workstream A) plus the
new B-workstream deterministic helpers and the D-workstream prompt-prefix
determinism guarantee. Pure — no DB, no Gemini, no app boot."""

import math

from app.matcha.services import analysis_pilot as ap
from app.matcha.services.analysis_packs import base as B


# --- A: per-message clipping -------------------------------------------------

def test_clip_bounds_long_messages():
    long = "x" * (ap._HISTORY_CLIP + 500)
    out = ap._clip(long)
    assert len(out) == ap._HISTORY_CLIP + 1  # +1 for the ellipsis
    assert out.endswith("…")


def test_clip_leaves_short_messages_untouched():
    assert ap._clip("hello") == "hello"
    assert ap._clip("") == ""
    assert ap._clip(None) == ""


# --- A: split_history --------------------------------------------------------

def _um(content, role="user"):
    return {"role": role, "content": content, "metadata": None}


def _summary(content, covers=10):
    return {"role": "system", "content": content, "metadata": {"kind": "summary", "covers": covers}}


def test_split_history_no_summary():
    hist = [_um("q1"), _um("a1", "assistant"), _um("q2")]
    split = ap.split_history(hist)
    assert split["summary"] is None
    assert split["uncompacted_count"] == 3
    assert [m["content"] for m in split["recent"]] == ["q1", "a1", "q2"]


def test_split_history_with_summary_counts_only_after():
    hist = [_um("old1"), _um("old2", "assistant"),
            _summary("SUM covering old turns"),
            _um("new1"), _um("new2", "assistant")]
    split = ap.split_history(hist)
    assert split["summary"] == "SUM covering old turns"
    assert split["uncompacted_count"] == 2
    assert [m["content"] for m in split["recent"]] == ["new1", "new2"]


def test_split_history_picks_latest_summary():
    hist = [_summary("FIRST", covers=5), _um("mid"),
            _summary("SECOND", covers=8), _um("after")]
    split = ap.split_history(hist)
    assert split["summary"] == "SECOND"
    assert [m["content"] for m in split["recent"]] == ["after"]


def test_split_history_tolerates_json_string_metadata():
    import json
    hist = [{"role": "system", "content": "S", "metadata": json.dumps({"kind": "summary"})},
            _um("after")]
    split = ap.split_history(hist)
    assert split["summary"] == "S"
    assert split["uncompacted_count"] == 1


def test_conversation_text_renders_summary_block():
    hist = [_summary("PRIOR STUFF"), _um("latest q")]
    text = ap._conversation_text(hist)
    assert "PRIOR CONVERSATION (compacted summary of older turns):" in text
    assert "PRIOR STUFF" in text
    assert "latest q" in text


def test_conversation_text_no_summary_uses_plain_header():
    text = ap._conversation_text([_um("just this")])
    assert text.startswith("CONVERSATION (oldest first):")
    assert "PRIOR CONVERSATION" not in text


def test_cap_constant_sane():
    assert ap._MAX_SESSION_MESSAGES > ap._COMPACT_TRIGGER > ap._HISTORY_TURNS


# --- D: stable-prefix determinism (cacheability contract) --------------------

def _corpus():
    return {
        "sources": {"ds:1": {"label": "d.csv", "records": [
            {"cid": "metric:1:rev:latest", "summary": "Revenue latest: 100."}]}},
        "index": {"metric:1:rev:latest": {"cid": "metric:1:rev:latest"}},
        "notes": ["d.csv: Column 'Date' used as period axis."],
    }


def test_stable_prefix_identical_across_turns():
    session = {"title": "T", "domain": "general", "goal": "g"}
    corpus = _corpus()
    p1 = ap._stable_prefix(session, corpus, [])
    p2 = ap._stable_prefix(session, corpus, [])
    assert p1 == p2  # byte-identical → context cache stays valid across turns


def test_stable_prefix_excludes_conversation_and_latest():
    session = {"title": "T", "domain": "general", "goal": "g"}
    prefix = ap._stable_prefix(session, _corpus(), [])
    # nothing turn-specific may leak into the cacheable head
    assert "LATEST USER MESSAGE" not in prefix
    assert "CONVERSATION" not in prefix
    # but the notes bug-fix content IS present
    assert "DATA QUALITY NOTES" in prefix


def test_stable_prefix_changes_when_corpus_changes():
    session = {"title": "T", "domain": "general", "goal": "g"}
    base = ap._stable_prefix(session, _corpus(), [])
    c2 = _corpus()
    c2["sources"]["ds:1"]["records"].append(
        {"cid": "metric:1:rev:peak", "summary": "Revenue peak: 200."})
    changed = ap._stable_prefix(session, c2, [])
    assert base != changed  # a data change must bust the cache


# --- C: plan validation gate -------------------------------------------------

def test_validate_plan_drops_uncited_ids():
    index = {"metric:1:rev:latest": {}}
    plan = [{"step": "s", "finding": "f",
             "cited_ids": ["metric:1:rev:latest", "metric:1:FAKE:x"]}]
    clean = ap._validate_plan(plan, index)
    assert clean[0]["cited_ids"] == ["metric:1:rev:latest"]


def test_validate_plan_handles_garbage():
    assert ap._validate_plan(None, {}) == []
    assert ap._validate_plan(["not a dict"], {}) == []


# --- B: new deterministic helpers -------------------------------------------

def test_ols_fit_perfect_line():
    slope, r2 = B.ols_fit([1, 2, 3, 4, 5])
    assert abs(slope - 1.0) < 1e-9
    assert abs(r2 - 1.0) < 1e-9


def test_ols_fit_noise_low_r2():
    slope, r2 = B.ols_fit([5, 1, 6, 2, 5, 1])
    assert r2 < 0.3


def test_ols_fit_too_few_points():
    assert B.ols_fit([1, 2]) == (None, None)


def test_iqr_outliers_flags_spike():
    vals = [10, 11, 9, 10, 11, 10, 9, 200]
    outs = B.iqr_outliers(vals)
    assert (7, 200.0) in outs


def test_iqr_outliers_none_when_flat():
    assert B.iqr_outliers([5, 5, 5, 5, 5, 5]) == []


def test_skewness_symmetric_near_zero():
    sk = B.skewness([1, 2, 3, 4, 5, 4, 3, 2, 1])
    assert abs(sk) < 0.5


def test_excess_kurtosis_defined():
    ku = B.excess_kurtosis([1, 2, 3, 4, 5, 6, 7, 8])
    assert ku is not None


def test_rolling_stdev_returns_pair():
    rets = [0.01 * ((-1) ** i) for i in range(30)]
    latest, full = B.rolling_stdev(rets, 12)
    assert latest is not None and full is not None


def test_max_drawdown_detail_marks_trough_and_recovery():
    # rise, fall to trough, recover above the prior peak
    idx = [1.0, 1.2, 1.5, 1.0, 0.9, 1.6]
    frac, peak_i, trough_i, recovery_i = B.max_drawdown_detail(idx)
    assert peak_i == 2 and trough_i == 4
    assert recovery_i == 5
    assert abs(frac - (1.5 - 0.9) / 1.5) < 1e-9


def test_max_drawdown_detail_no_recovery():
    idx = [1.0, 1.4, 1.0, 0.8]
    frac, peak_i, trough_i, recovery_i = B.max_drawdown_detail(idx)
    assert recovery_i is None
