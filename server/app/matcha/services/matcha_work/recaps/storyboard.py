"""Deterministic editing, without model calls or source re-execution."""
import json
from app.matcha.models.matcha_work.recaps import Asset, Event, Fact, Manifest, Scene

CONSEQUENTIAL = frozenset({"unknown", "failed", "partial", "cancelled", "declined", "handoff"})


def build(events: list[dict]) -> Manifest:
    parsed = [(Event.model_validate(e["snapshot"]), e.get("asset")) for e in events]
    if not parsed:
        raise ValueError("no evidence")
    # Always retain a request and final result, and summarize every warning.
    warnings = [event for event, _ in parsed if event.outcome in CONSEQUENTIAL]
    middle = list(enumerate(parsed[1:-1], start=1))
    important = [(i, pair) for i, pair in middle if pair[0].outcome in CONSEQUENTIAL or pair[0].kind == "result"]
    ordinary = [(i, pair) for i, pair in middle if pair[0].outcome not in CONSEQUENTIAL and pair[0].kind != "result"]
    chosen = sorted([*important[:8], *ordinary[:max(0, 8-len(important))]], key=lambda entry: entry[0])
    selected = [parsed[0], *(pair for _, pair in chosen), *([] if len(parsed) == 1 else [parsed[-1]])]
    if warnings:
        if len(selected) > 10:
            selected = [*selected[:9], selected[-1]]
        selected.insert(-1 if len(selected) > 1 else 1, (Event(
            kind="warning", title="Outcomes to review", outcome="partial", occurred_at=warnings[-1].occurred_at,
            facts=[Fact(label=outcome, value=("; ".join(dict.fromkeys(e.title for e in warnings if e.outcome == outcome)))[:260] + " · see transcript")
                   for outcome in sorted({e.outcome for e in warnings})][:6],
        ), None))
    scenes = []
    for index, (event, asset) in enumerate(selected):
        seconds = 4 if index == 0 else (16 if index == len(selected) - 1 else 8)
        scenes.append(Scene(event=event, seconds=seconds, asset=Asset.model_validate(asset) if asset else None))
    transcript = [event for event, _ in parsed]
    while len(transcript) > 256 or len(json.dumps([event.model_dump(mode="json") for event in transcript], ensure_ascii=False).encode()) > 800_000:
        removable = next((i for i, event in enumerate(transcript)
                          if event.outcome not in CONSEQUENTIAL and event.kind not in ("result", "warning")), None)
        if removable is None:
            raise ValueError("consequential_evidence_exceeds_manifest")
        transcript.pop(removable)
    return Manifest(scenes=scenes, transcript=transcript)
