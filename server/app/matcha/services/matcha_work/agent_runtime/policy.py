"""The gate every outward action passes before it runs.

Pure on purpose: no I/O, no clock, no model. The caller loads whatever the
decision needs (the user's own messages, prior commit counts) and hands it in,
so the same inputs always give the same verdict and the whole thing is testable
without a database.

The default is `allow`: once a person enables an ability the agent acts without
asking. Two things override that default:

  deny     a ceiling was reached, or a private-only tool ran outside the
           person's private conversation
  confirm  the action reaches someone or somewhere the person never named

"Named" is strict. A recipient is grounded when the person typed the address,
when it is their own, or when it sits on a thread or event they pointed at. A
thread the agent merely READ grounds nothing: otherwise anyone who emails the
person becomes a recipient the agent may write to unasked, which is the whole
prompt-injection exfiltration path. A typed address grounds itself only, never
the other people on a thread it appears on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Mapping

from .registry import AgentTool, Target

Verdict = Literal["allow", "confirm", "deny"]

_ADDRESS = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")
_HOST = re.compile(
    r"(?<![@A-Za-z0-9.\-])((?:[A-Za-z0-9¡-￿](?:[A-Za-z0-9¡-￿\-]{0,61}"
    r"[A-Za-z0-9¡-￿])?\.)+[A-Za-z¡-￿]{2,63})(?![A-Za-z0-9\-])"
)
# Registrable domains sit one label below these. Not the full public suffix
# list: a suffix missing here makes the check stricter for nobody and looser
# only for a two-label name under it, which `_registrable` still refuses to
# treat as a parent of anything.
_MULTI_LABEL_SUFFIXES = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk", "net.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au", "id.au",
    "co.nz", "org.nz", "net.nz", "govt.nz", "ac.nz",
    "co.jp", "ne.jp", "or.jp", "ac.jp", "go.jp",
    "co.kr", "or.kr", "co.in", "net.in", "org.in", "gen.in", "firm.in",
    "com.br", "net.br", "org.br", "com.mx", "org.mx", "com.ar", "com.co",
    "com.cn", "net.cn", "org.cn", "com.hk", "com.sg", "com.tw", "com.my",
    "co.za", "org.za", "co.il", "org.il", "com.tr", "com.ua", "co.th",
    "com.ph", "com.vn", "co.id", "com.pk", "com.eg", "com.sa", "com.ng",
    "github.io", "gitlab.io", "herokuapp.com", "vercel.app", "netlify.app",
    "pages.dev", "workers.dev", "web.app", "firebaseapp.com", "appspot.com",
    "cloudfront.net", "amazonaws.com", "azurewebsites.net", "blogspot.com",
})


@dataclass(frozen=True)
class Grounding:
    user_texts: tuple[str, ...] = ()  # only the requester's own messages
    own_addresses: frozenset[str] = frozenset()
    pointed_refs: frozenset[str] = frozenset()
    ref_participants: Mapping[str, frozenset[str]] = field(default_factory=dict)
    trusted_domains: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PolicyContext:
    surface: str
    private_conversation: bool
    grounding: Grounding
    # (tool name, window seconds) -> actions already committed in that window
    counts: Mapping[tuple[str, int], int] = field(default_factory=dict)
    approved: bool = False


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str
    ungrounded: tuple[Target, ...] = ()
    message: str = ""


def encode_host(host: str) -> str | None:
    """Lowercase ASCII (IDNA) form of a hostname, or None when it isn't one."""
    cleaned = (host or "").strip().strip(".").lower()
    if not cleaned or " " in cleaned or "." not in cleaned:
        return None
    try:
        encoded = cleaned.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return None
    labels = encoded.split(".")
    if any(not label or len(label) > 63 for label in labels):
        return None
    return encoded


def normalize_address(address: str) -> str | None:
    text = (address or "").strip().strip("<>").lower()
    if text.count("@") != 1:
        return None
    local, _, domain = text.partition("@")
    host = encode_host(domain)
    if not local or host is None:
        return None
    return f"{local}@{host}"


def extract_addresses(text: str) -> frozenset[str]:
    found = set()
    for match in _ADDRESS.finditer(text or ""):
        normalized = normalize_address(match.group(0))
        if normalized:
            found.add(normalized)
    return frozenset(found)


def extract_domains(text: str) -> frozenset[str]:
    """Hostnames written in the text. The domain half of an address is not one."""
    found = set()
    for match in _HOST.finditer(text or ""):
        host = encode_host(match.group(1))
        if host:
            # "www.shop.example" names shop.example: the bare form covers both.
            found.add(host.removeprefix("www."))
    return frozenset(found)


def _is_public_suffix(host: str) -> bool:
    return "." not in host or host in _MULTI_LABEL_SUFFIXES


def _covers(named: str, host: str) -> bool:
    """`named` is `host` itself or a registrable parent of it."""
    if _is_public_suffix(named):
        return False
    return host == named or host.endswith("." + named)


def is_grounded(target: Target, g: Grounding) -> bool:
    if target.kind == "email":
        address = normalize_address(target.value)
        if address is None:
            return False
        if address in g.own_addresses:
            return True
        for text in g.user_texts:
            if address in extract_addresses(text):
                return True
        for ref in g.pointed_refs:
            if address in g.ref_participants.get(ref, frozenset()):
                return True
        return False
    host = encode_host(target.value)
    if host is None:
        return False
    if any(_covers(trusted, host) for trusted in g.trusted_domains):
        return True
    for text in g.user_texts:
        if any(_covers(named, host) for named in extract_domains(text)):
            return True
    return False


def pointed_refs(user_texts: tuple[str, ...], context_refs: tuple[str, ...] | frozenset[str],
                 ref_participants: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """The refs the person pointed at.

    A ref counts when the trigger message carried it as structured context, or
    when the person's own text holds the ref's id. Reading a thread is not
    pointing at it, and neither is naming someone who happens to be on it: an
    address the person typed grounds that address and nothing else. If it
    pointed at every thread that address appears on, anyone could put
    themselves on a thread with it and become a recipient.
    """
    pointed = {ref for ref in context_refs if ref}
    for ref in ref_participants:
        if ref and len(ref) >= 8 and any(ref in text for text in user_texts):
            pointed.add(ref)
    return frozenset(pointed)


def evaluate_commit(
    ctx: PolicyContext,
    tool: AgentTool,
    args: dict,
    *,
    targets: tuple[Target, ...],
    private_only: bool,
) -> Decision:
    if tool.effect != "commit":
        return Decision("allow", "not_a_commit")
    if private_only and not ctx.private_conversation:
        return Decision(
            "deny", "private_only",
            message="That only works in your private conversation with Espresso.",
        )
    weight = max(1, tool.weight(args)) if tool.weight else 1
    for limit, window in tool.ceilings:
        if ctx.counts.get((tool.name, window), 0) + weight > limit:
            return Decision(
                "deny", "ceiling",
                message=f"That is past the limit of {limit} for {tool.name}. Try again later or do fewer at once.",
            )
    if ctx.approved:
        return Decision("allow", "approved")
    ungrounded = tuple(t for t in targets if not is_grounded(t, ctx.grounding))
    if ungrounded:
        return Decision(
            "confirm", "ungrounded_target", ungrounded=ungrounded,
            message="Waiting for the person to confirm: " + ", ".join(t.value for t in ungrounded),
        )
    return Decision("allow", "grounded" if targets else "no_external_target")
