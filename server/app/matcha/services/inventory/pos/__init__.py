"""POS provider adapters."""

from .square import SquareProvider


def provider_for(name: str):
    if name == "square":
        return SquareProvider()
    raise ValueError(f"POS provider {name!r} is not implemented")
