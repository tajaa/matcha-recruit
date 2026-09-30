"""Matcha Drive access model — pure, no DB.

Two spaces, each with a default capability set derived from the actor's
company-scoped Work level (`work_permissions.resolve_work_access`), widened by
per-user folder grants that apply to the granted folder and every descendant.

    general: admin -> everything; operator -> list/read/add/manage;
             reviewer/member -> list + read; guest -> nothing.
    hr:      admin -> everything; everyone else -> nothing.

`clients.is_hr_approver` is deliberately NOT an input here — that column is
documented as notification targeting only, never authorization. HR approvers
get access through an ordinary, visible, revocable `edit` grant on the HR root
that `drive_service.ensure_system_folders` seeds once when the folders are
first created.

Grants are strictly additive: nothing here can take a default away. 'view'
and 'edit' apply to the granted folder and every descendant. 'upload' is a
drop-box (ADD only — no LIST, no READ) for the GRANTED FOLDER ONLY: it is not
inherited, so a drop-box on `HR` doesn't reveal or accept files into
`HR / Investigations / <name>`. GRANT (managing grants) is never conferred by
a grant; only Work `admin` holds it, so a folder 'edit' grantee cannot hand
out access.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Optional
from uuid import UUID


class DriveCap(str, Enum):
    LIST = "list"
    READ = "read"
    ADD = "add"
    MANAGE = "manage"
    GRANT = "grant"


SPACES = ("general", "hr")
GRANT_PERMISSIONS = ("view", "upload", "edit")

_ALL = frozenset(DriveCap)
_READ_ONLY = frozenset({DriveCap.LIST, DriveCap.READ})
_OPERATE = frozenset({DriveCap.LIST, DriveCap.READ, DriveCap.ADD, DriveCap.MANAGE})
_NONE: frozenset[DriveCap] = frozenset()

GRANT_CAPS: dict[str, frozenset[DriveCap]] = {
    "view": _READ_ONLY,
    "upload": frozenset({DriveCap.ADD}),
    "edit": _OPERATE,
}


class DrivePermissionDenied(PermissionError):
    def __init__(self, cap: DriveCap):
        self.cap = cap
        super().__init__(f"Drive permission required: {cap.value}")


@dataclass(frozen=True)
class DriveActor:
    user_id: UUID
    work_level: str  # guest | member | reviewer | operator | admin


def space_default_caps(actor: DriveActor, space: str) -> frozenset[DriveCap]:
    if space not in SPACES:
        raise ValueError(f"Unknown drive space: {space}")
    if actor.work_level == "admin":
        return _ALL
    if space == "hr":
        return _NONE
    if actor.work_level == "operator":
        return _OPERATE
    if actor.work_level in ("reviewer", "member"):
        return _READ_ONLY
    return _NONE


def effective_caps(
    actor: DriveActor, space: str, ancestor_grants: Iterable[Optional[str]] = (),
) -> frozenset[DriveCap]:
    """Space default ∪ the grants on the folder's chain, folder FIRST then its
    ancestors. An 'upload' grant counts only at position 0 (the folder
    itself). Unknown/None grant strings are ignored rather than trusted."""
    caps = set(space_default_caps(actor, space))
    for position, perm in enumerate(ancestor_grants):
        if not perm or (perm == "upload" and position > 0):
            continue
        caps |= GRANT_CAPS.get(perm, _NONE)
    return frozenset(caps)


def visible_in_tree(caps: frozenset[DriveCap]) -> bool:
    """A folder appears in the tree only when it can be listed or is itself a
    drop-box. Inherited upload access is already excluded by effective_caps,
    so an ADD-only folder here is always the one the grant sits on."""
    return DriveCap.LIST in caps or DriveCap.ADD in caps


def folder_caps_map(
    actor: DriveActor,
    folders: Iterable[Mapping],
    grants: Mapping[UUID, str],
) -> dict[UUID, frozenset[DriveCap]]:
    """Caps for every folder at once, from an in-memory folder list
    (`id`, `parent_id`, `space`) and this actor's grants keyed by folder id.
    Used for the tree and for search filtering so one query serves both.
    A parent chain longer than the folder count (a cycle in bad data) stops
    rather than loops."""
    by_id = {f["id"]: f for f in folders}
    limit = len(by_id) + 1
    out: dict[UUID, frozenset[DriveCap]] = {}
    for fid, folder in by_id.items():
        chain: list[Optional[str]] = []
        cur = folder
        steps = 0
        while cur is not None and steps < limit:
            chain.append(grants.get(cur["id"]))
            parent = cur.get("parent_id")
            cur = by_id.get(parent) if parent else None
            steps += 1
        out[fid] = effective_caps(actor, folder["space"], chain)
    return out


def assert_cap(caps: frozenset[DriveCap], cap: DriveCap) -> None:
    if cap not in caps:
        raise DrivePermissionDenied(cap)


def caps_list(caps: frozenset[DriveCap]) -> list[str]:
    """Stable wire order for the client."""
    return [c.value for c in DriveCap if c in caps]
