"""The ability registry: what the agent can do, declared as data.

An `Ability` is a pack of `AgentTool`s plus the prompt text, result blocks and
connection requirements that go with them. The runner dispatches by looking a
tool up here, so adding a capability is a new `Ability`, never a new branch in
the loop.

Every tool states its `effect`. That one field is what the rest of the runtime
keys on:

  read    looks something up; no side effect
  draft   writes something the user still has to act on (a saved draft)
  commit  acts outward (sends, books, archives); goes through `policy` first
  ask     ends the run with a question for the user
  finish  the structured result

This module imports nothing but the standard library, so `policy` can depend
on it and stay free of I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Sequence

if TYPE_CHECKING:
    from .context import RunContext, RunState

Effect = Literal["read", "draft", "commit", "ask", "finish"]
EFFECTS: tuple[str, ...] = ("read", "draft", "commit", "ask", "finish")
# `mw_project_agent_steps.kind` values (migration agentrt01).
STEP_KINDS: frozenset[str] = frozenset({
    "read", "finish", "search", "fetch", "image", "draft", "commit", "ask", "browse", "policy",
})


@dataclass(frozen=True)
class Target:
    """Something outside our system a commit tool would reach."""

    kind: Literal["email", "domain"]
    value: str  # lowercased; domains IDNA-encoded
    ref: str | None = None  # the thread or event id it was taken from


@dataclass(frozen=True)
class ToolOutput:
    payload: dict
    provenance: frozenset[str] = frozenset()
    audit: dict | None = None
    label: str | None = None
    status: str = "ok"
    receipt: dict | None = None  # commit tools: what the receipt card shows


@dataclass(frozen=True)
class HostedObservation:
    """What one model response shows a provider-run tool did."""

    steps: tuple[tuple[str, dict, dict], ...] = ()  # (label, args, result)
    provenance: frozenset[str] = frozenset()


ToolHandler = Callable[["RunContext", "RunState", dict, float], Awaitable[ToolOutput]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    effect: Effect
    description: str
    parameters: dict
    step_kind: str
    handler: ToolHandler | None = None
    hosted: dict | None = None  # exactly one of handler / hosted, except finish/ask
    # Hosted tools: read the provider's own calls out of a response.
    observe: Callable[[list[dict]], HostedObservation] | None = None
    hosted_note: Callable[[int], str] | None = None
    include: tuple[str, ...] = ()  # Responses `include` entries the observer needs
    max_calls: int | None = None
    timeout_seconds: float | None = None
    min_seconds_left: float = 0.0
    describe: Callable[[dict], str] | None = None  # step label from the arguments
    audit: Callable[[dict], dict] | None = None  # what of the output the audit row keeps
    exhausted_label: str = "Budget exhausted"
    exhausted_message: str = "Budget used up; finish with what you have."
    timeout_message: str = "That took too long."
    too_late_message: str = "Not enough time left; finish with what you have."
    required_scopes: tuple[str, ...] = ()
    # Commit tools. `resolve` turns the model's arguments into a complete,
    # self-contained action (a bare reply gets its recipient, thread and
    # subject written in), using what the run has seen. Everything after it,
    # the policy, the preview and the handler, reads only the resolved
    # arguments. That is what lets a held action be carried out later by a
    # different run: the frozen arguments need nothing from the run that
    # froze them. All three are pure.
    resolve: Callable[[dict, "RunState"], dict] | None = None
    targets: Callable[[dict, "RunState"], tuple[Target, ...]] | None = None
    preview: Callable[[dict, "RunState"], dict] | None = None
    weight: Callable[[dict], int] | None = None  # how many actions one call is
    ceilings: tuple[tuple[int, int], ...] = ()  # (limit, window_seconds)
    untrusted_output: bool = False
    # Commit tools: hold every call for the person's yes, grounded or not
    # (spending money is never done on the default allow).
    always_confirm: bool = False


@dataclass(frozen=True)
class Ability:
    key: str
    label: str
    tools: tuple[AgentTool, ...]
    prompt_block: Callable[["RunContext"], str]
    connection: Literal["google"] | None = None
    required_scopes: tuple[str, ...] = ()
    entitlement: str | None = None
    env_ready: Callable[[], bool] = field(default=lambda: True)
    private_only: bool = False
    consent_version: str | None = None
    session_factory: Callable[["RunContext"], Any] | None = None
    # Result blocks this ability may put in an agent_result.v2, with the JSON
    # schema the model fills and the gate that rebuilds each from what the run
    # actually saw.
    block_schemas: dict[str, dict] = field(default_factory=dict)
    gate: Callable[[str, Any, "RunState"], tuple[dict | None, list[str]]] | None = None
    # Domains a commit may reach without the user naming them (known booking
    # platforms, for instance).
    trusted_domains: frozenset[str] = frozenset()
    # A per-person allowance the run's situation must carry (`Situation.allowed`),
    # for abilities open to some accounts only.
    allowance: str | None = None
    # Server-authored blocks added to the result when the model left them out:
    # (run state) -> blocks. Each type must be one of `block_schemas`.
    auto_blocks: Callable[["RunState"], list[dict]] | None = None

    @property
    def block_types(self) -> tuple[str, ...]:
        return tuple(self.block_schemas)


class CatalogError(ValueError):
    """The registry itself is wrong. Raised at import/startup, never mid-run."""


def validate_tool(tool: AgentTool) -> None:
    if tool.effect not in EFFECTS:
        raise CatalogError(f"{tool.name}: unknown effect {tool.effect!r}")
    if tool.step_kind not in STEP_KINDS:
        raise CatalogError(f"{tool.name}: unknown step kind {tool.step_kind!r}")
    if tool.effect in ("finish", "ask"):
        if tool.handler is not None or tool.hosted is not None:
            raise CatalogError(f"{tool.name}: a {tool.effect} tool is handled by the runner")
        return
    if (tool.handler is None) == (tool.hosted is None):
        raise CatalogError(f"{tool.name}: a tool is hosted or handled, never both or neither")
    if tool.hosted is not None and tool.effect != "read":
        raise CatalogError(f"{tool.name}: a hosted tool can only read")
    if tool.always_confirm and tool.effect != "commit":
        raise CatalogError(f"{tool.name}: only a commit tool can always confirm")
    if tool.effect == "commit":
        if tool.targets is None:
            raise CatalogError(f"{tool.name}: a commit tool must declare its targets")
        if tool.preview is None:
            raise CatalogError(f"{tool.name}: a commit tool must declare its preview")
    for limit, window in tool.ceilings:
        if limit <= 0 or window <= 0:
            raise CatalogError(f"{tool.name}: ceilings are (limit > 0, window_seconds > 0)")


def validate_catalog(abilities: Sequence[Ability]) -> None:
    """Refuse a catalog the runner could not dispatch unambiguously."""
    keys: set[str] = set()
    names: dict[str, str] = {}
    blocks: dict[str, str] = {}
    for ability in abilities:
        if ability.key in keys:
            raise CatalogError(f"duplicate ability key {ability.key!r}")
        keys.add(ability.key)
        for tool in ability.tools:
            validate_tool(tool)
            if tool.effect in ("finish", "ask"):
                raise CatalogError(f"{tool.name}: {tool.effect} tools belong to the runner, not an ability")
            if tool.name in names:
                raise CatalogError(
                    f"tool {tool.name!r} is declared by both {names[tool.name]!r} and {ability.key!r}"
                )
            names[tool.name] = ability.key
        for block in ability.block_schemas:
            if block in blocks:
                raise CatalogError(
                    f"result block {block!r} is declared by both {blocks[block]!r} and {ability.key!r}"
                )
            blocks[block] = ability.key
        if ability.block_schemas and ability.gate is None:
            raise CatalogError(f"{ability.key}: result blocks need a gate")


def tool_scopes(ability: Ability, tool: AgentTool) -> frozenset[str]:
    return frozenset(ability.required_scopes) | frozenset(tool.required_scopes)


def offered_tools(
    abilities: Sequence[Ability],
    *,
    last_call: bool,
    hosted_left: int,
    granted_scopes: frozenset[str] = frozenset(),
) -> list[AgentTool]:
    """The tools one model call may see: hosted first, then ours.

    A tool whose scopes were not granted is left out entirely, so the model is
    never offered something that can only refuse. Hosted tools drop out once
    their budget is spent and on the last turn, which must finish.
    """
    hosted: list[AgentTool] = []
    handled: list[AgentTool] = []
    for ability in abilities:
        for tool in ability.tools:
            if not tool_scopes(ability, tool) <= granted_scopes:
                continue
            if tool.hosted is not None:
                if hosted_left > 0 and not last_call:
                    hosted.append(tool)
            else:
                handled.append(tool)
    return hosted + handled


def declarations(tools: Sequence[AgentTool]) -> list[dict[str, Any]]:
    """Responses API tool declarations, in the given order."""
    out: list[dict[str, Any]] = []
    for tool in tools:
        if tool.hosted is not None:
            out.append(dict(tool.hosted))
        else:
            out.append({
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            })
    return out
