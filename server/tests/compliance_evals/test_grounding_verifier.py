"""Grounding tier-2b verifier — pure core (verifier_verdict + input_hash).

No client, no DB: the model-response → verdict mapping and the cache-key hash are
deterministic. The Gemini call itself (verify_rows) is exercised manually against
dev, not here.
"""
from app.core.services.compliance_evals.grounding_verifier import (
    LLM_CONFIRMED, LLM_REFUTED, LLM_UNCLEAR,
    build_refute_prompt, input_hash, verifier_verdict,
)


# ── verifier_verdict ────────────────────────────────────────────────────────

def test_bool_true_confirms():
    assert verifier_verdict({"stated": True}) == LLM_CONFIRMED


def test_bool_false_refutes():
    assert verifier_verdict({"stated": False}) == LLM_REFUTED


def test_string_true_false_yes_no():
    assert verifier_verdict({"stated": "true"}) == LLM_CONFIRMED
    assert verifier_verdict({"stated": "YES"}) == LLM_CONFIRMED
    assert verifier_verdict({"stated": "false"}) == LLM_REFUTED
    assert verifier_verdict({"stated": "no"}) == LLM_REFUTED


def test_string_unclear_is_unclear():
    assert verifier_verdict({"stated": "unclear"}) == LLM_UNCLEAR


def test_malformed_defaults_unclear():
    assert verifier_verdict(None) == LLM_UNCLEAR
    assert verifier_verdict("garbage") == LLM_UNCLEAR
    assert verifier_verdict({}) == LLM_UNCLEAR
    assert verifier_verdict({"stated": 42}) == LLM_UNCLEAR


# ── input_hash ──────────────────────────────────────────────────────────────

def test_hash_stable_for_same_inputs():
    assert input_hash("$15/hr", "the wage is $15") == input_hash("$15/hr", "the wage is $15")


def test_hash_changes_with_value_or_corpus():
    base = input_hash("$15/hr", "body A")
    assert base != input_hash("$16/hr", "body A")   # value changed → re-verify
    assert base != input_hash("$15/hr", "body B")   # corpus changed → re-verify


def test_hash_handles_none():
    # a row with a null value/corpus still hashes (no crash), distinct from empties
    assert input_hash(None, None) == input_hash("", "")  # both empty-string coerced


# ── prompt shape ────────────────────────────────────────────────────────────

def test_prompt_is_refute_framed_and_carries_both_sides():
    p = build_refute_prompt("$15.00 per hour", "The minimum wage is $15.00 per hour.")
    assert "REFUTE" in p
    assert "$15.00 per hour" in p          # claimed value present
    assert "The minimum wage is" in p       # excerpt present
    assert "outside knowledge" in p         # grounding rule present
