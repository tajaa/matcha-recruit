"""Flyer design assistant — validated ops over a curated token vocabulary.

Layout:
  catalog.py   the vocabulary (layer fields, fonts, tokens, caps) both the
               prompt and the validators read
  palettes.py  curated colour presets — mirrors public/designer/palettes.json
  layouts.py   curated whole-flyer starting points ("generate ideas")
  ops.py       the op registry: validator + prompt shape + prompt rules per op
  apply.py     the CANONICAL applier (inverted from Cappe — see its docstring)
  turn.py      one Gemini turn, and the ideas generator
"""
from .apply import apply_ops
from .ops import validate_document, validate_ops
from .turn import generate_ideas, run_flyer_turn

__all__ = ["apply_ops", "validate_ops", "validate_document", "run_flyer_turn", "generate_ideas"]
