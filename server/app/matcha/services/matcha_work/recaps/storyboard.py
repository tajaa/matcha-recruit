"""Deterministic editing, without model calls or source re-execution."""
from app.matcha.models.matcha_work.recaps import Asset, Event, Fact, Manifest, Scene

CONSEQUENTIAL = frozenset({"unknown", "failed", "partial", "cancelled", "declined"})


def build(events: list[dict]) -> Manifest:
    parsed = [(Event.model_validate(e["snapshot"]), e.get("asset")) for e in events]
    if not parsed:
        raise ValueError("no evidence")
    # Always retain a request and final result, and summarize every warning.
    warnings = [event for event, _ in parsed if event.outcome in CONSEQUENTIAL]
    middle = [(event, asset) for event, asset in parsed[1:-1] if event.outcome not in CONSEQUENTIAL]
    selected = [parsed[0], *middle[:9], *([] if len(parsed) == 1 else [parsed[-1]])]
    if warnings:
        if len(selected) > 10:
            selected = [*selected[:9], selected[-1]]
        selected.insert(-1 if len(selected) > 1 else 1, (Event(
            kind="warning", title="Outcomes to review", outcome="partial", occurred_at=warnings[-1].occurred_at,
            facts=[Fact(label=outcome, value=str(sum(e.outcome == outcome for e in warnings)))
                   for outcome in sorted({e.outcome for e in warnings})][:6],
        ), None))
    scenes = []
    for index, (event, asset) in enumerate(selected):
        seconds = 4 if index == 0 else (16 if index == len(selected) - 1 else 8)
        scenes.append(Scene(event=event, seconds=seconds, asset=Asset.model_validate(asset) if asset else None))
    return Manifest(scenes=scenes)
