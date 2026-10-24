"""Live visual systems: normalization, rendering, safe snapshots and owner CAS.
All HTTP persistence is mocked; no live database or migration is used.
"""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.cappe.routes import studio
from app.cappe.services.magazine.studio import identity as I, schema as S, render as R, text_view as T
from tests._helpers.routes import route_client
from tests.cappe.test_cappe_magazine_routes import ACCOUNT, SITE, SITE_ROW, Conn, Ctx, _blog_client, _owner_conn, _returning
from tests.cappe.test_cappe_magazine_routes import invalidated  # noqa: F401
from tests.cappe.test_cappe_studio_routes import paged_row
from tests.cappe.test_cappe_magazine_routes import POST


def identity():
    return json.loads((Path(__file__).parent / "fixtures/studio_identity.json").read_text())


def document():
    doc = S.starter_doc()
    doc["identity"] = identity()
    doc["pages"][1]["parent"] = "pl1"
    doc["threads"][0]["paras"] = [{"style": "ps1", "runs": [{"t": "A caption"}, {"t": " italic", "style": "cs1"}]}]
    return doc


def client_for(monkeypatch, conn):
    monkeypatch.setattr(studio, "get_connection", lambda: Ctx(conn))
    return route_client(studio.router, overrides={studio.require_cappe_account: ACCOUNT})


def test_normalization_keeps_bindings_sparse_and_is_stable():
    doc = S.normalize_doc(document())
    assert S.normalize_doc(json.loads(json.dumps(doc))) == doc
    p = doc["threads"][0]["paras"][0]
    assert p == {"style": "ps1", "runs": [{"t": "A caption"}, {"t": " italic", "style": "cs1"}]}
    shown = I.resolve_paras([p], doc["identity"])[0]
    assert shown["role"] == "caption" and shown["runs"][0]["size"] == 8
    assert shown["runs"][1]["it"] and shown["runs"][0]["color"] == "#ab3322"
    parent = doc["identity"]["parents"][0]
    assert parent["items"][1]["asset_id"] is None and parent["items"][1]["caption"] == ""


def test_explicit_default_overrides_survive_normalization_and_redefinition():
    raw = document(); raw["threads"][0]["paras"][0]["runs"] = [{"t": "local", "it": False, "size": 10.5, "color": "#1a1a1a"}]
    raw["threads"][0]["paras"][0]["align"] = "l"
    raw["identity"]["paragraphs"][0]["para"]["align"] = "r"
    raw["identity"]["paragraphs"][0]["char"]["it"] = True
    doc = S.normalize_doc(raw)
    run = doc["threads"][0]["paras"][0]["runs"][0]
    assert run["size"] == 10.5 and run["it"] is False
    shown = I.resolved_threads(doc)[0]["paras"][0]
    assert shown["align"] == "l" and shown["runs"][0]["color"] == "#1a1a1a"
    doc["identity"]["paragraphs"][0]["char"]["size"] = 24
    assert I.resolved_threads(doc)[0]["paras"][0]["runs"][0]["size"] == 10.5


@pytest.mark.parametrize("change", [
    lambda d: d["threads"][0]["paras"][0].update(style="missing"),
    lambda d: d["threads"][0]["paras"][0]["runs"][0].update(style="missing"),
    lambda d: d["threads"][0]["paras"][0]["runs"][0].update(swatch="missing"),
    lambda d: d["pages"][0].update(parent="missing"),
    lambda d: d["items"][0].update(fill_swatch="missing"),
    lambda d: d["identity"]["paragraphs"].append(deepcopy(d["identity"]["paragraphs"][0])),
    lambda d: d["identity"].update(parents=[{}] * 9),
    lambda d: d["identity"]["paragraphs"][0]["char"].update(font=[]),
])
def test_unknown_duplicate_or_malformed_designs_are_refused(change):
    raw = document(); change(raw)
    with pytest.raises(S.DocError):
        S.normalize_doc(raw)


def test_repeating_a_parent_cannot_bypass_thread_or_text_limits():
    raw = document(); raw["pages"] = [{"id": f"p{k}", "parent": "pl1"} for k in range(1, 202)]
    with pytest.raises(S.DocError, match="parents hold too many"):
        S.normalize_doc(raw)


def test_rendering_follows_styles_palette_parent_numbers_and_page_overrides_without_paywall_leaks():
    doc = S.normalize_doc(document())
    html, _ = R.pages_html(doc, {})
    assert 'font-size:calc(8 * var(--u))' in html and 'color:#ab3322' in html
    assert 'TIDE &amp; LIGHT' in html and '>5</div>' in html and 'Tide &lt;issue&gt;' in html
    doc["identity"]["swatches"][0]["color"] = "#ff0000"
    assert 'color:#ff0000' in R.pages_html(doc, {})[0]
    locked = R.pages_html(doc, {}, locked_from=2)[0].split('data-lyt-lock="2"')[1]
    assert 'TIDE' not in locked and 'lyt-furniture' not in locked
    paid = R.locked_pages(doc, {}, 2)[0]["html"]
    assert 'TIDE &amp; LIGHT' in paid
    doc["pages"][1]["hide_furniture"] = True
    assert 'lyt-furniture' not in R.page_items_html(doc, 1, {})
    assert T.text_blocks(doc)  # semantic roles read the resolved paragraphs


def test_identity_name_and_byte_boundaries():
    raw = identity(); raw["name"] = 'Tide\x00\ud800 📷'
    assert I.normalize_identity(raw)["name"] == 'Tide 📷'
    raw["padding"] = '界' * 90_000
    with pytest.raises(S.DocError, match="too big"):
        I.normalize_identity(raw)


def test_save_is_owner_scoped_locks_before_upsert_and_never_writes_public_metadata(monkeypatch):
    conn = Conn(fetchrow={"SELECT * FROM cappe_sites": SITE_ROW, "FROM cappe_studio_identities": None}, fetchval={"FOR UPDATE": SITE})
    with client_for(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/studio/identity", json={"base_rev": 0, "identity": identity()})
    assert res.status_code == 200, res.text
    args = conn.args_for('INSERT INTO cappe_studio_identities')
    assert args[:2] == (SITE, 1)
    assert json.loads(args[2]) == I.portable_identity(identity())
    assert conn.args_for('FOR UPDATE') == (SITE, ACCOUNT.id)
    assert 'account_id = $2' in conn.sql_for('fetchval')[0]
    assert all('meta_config' not in sql for _, sql, _ in conn.calls)
    assert 'FOR UPDATE' in conn.calls[1][1] and 'INSERT' in conn.calls[-1][1]


@pytest.mark.parametrize("changed_owner", [False, True])
def test_stale_or_owner_changed_identity_saves_never_overwrite(monkeypatch, changed_owner):
    record = {"rev": 2, "identity": I.portable_identity(identity())}
    conn = Conn(fetchrow={"SELECT * FROM cappe_sites": SITE_ROW, "FROM cappe_studio_identities": record}, fetchval={"FOR UPDATE": None if changed_owner else SITE})
    with client_for(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/studio/identity", json={"base_rev": 0, "identity": identity()})
    assert res.status_code == (404 if changed_owner else 409)
    assert not any('INSERT' in sql for _, sql, _ in conn.calls)


@pytest.mark.parametrize("as_json", [True, False])
def test_lost_successful_save_response_replays_the_same_identity(monkeypatch, as_json):
    clean = I.portable_identity(identity())
    record = {"rev": 2, "identity": json.dumps(clean) if as_json else clean}
    conn = Conn(fetchrow={"SELECT * FROM cappe_sites": SITE_ROW, "FROM cappe_studio_identities": record}, fetchval={"FOR UPDATE": SITE})
    with client_for(monkeypatch, conn) as client:
        res = client.put(f"/sites/{SITE}/studio/identity", json={"base_rev": 1, "identity": identity()})
    assert res.status_code == 200 and res.json()["rev"] == 2
    assert not any('INSERT' in sql for _, sql, _ in conn.calls)


@pytest.mark.parametrize("record", [None, {"rev": 2, "identity": I.portable_identity(identity())}])
def test_private_identity_read_is_scoped_and_supports_an_empty_library(monkeypatch, record):
    conn = Conn(fetchrow={"SELECT * FROM cappe_sites": SITE_ROW, "FROM cappe_studio_identities": record})
    with client_for(monkeypatch, conn) as client:
        res = client.get(f"/sites/{SITE}/studio/identity")
    assert res.status_code == 200 and res.json()["rev"] == (2 if record else 0)
    assert conn.args_for('FROM cappe_studio_identities') == (SITE,)
    assert 'account_id = $2' in conn.calls[0][1]


def test_missing_owner_and_invalid_identity_never_write(monkeypatch):
    for found in [False, True]:
        conn = Conn(fetchrow={"SELECT * FROM cappe_sites": SITE_ROW if found else None})
        with client_for(monkeypatch, conn) as client:
            res = client.put(f"/sites/{SITE}/studio/identity", json={"base_rev": 0, "identity": {}})
        assert res.status_code == (422 if found else 404)
        assert not any('INSERT' in sql for _, sql, _ in conn.calls)


def test_new_paged_stories_take_a_private_snapshot_of_the_saved_identity(monkeypatch, invalidated):
    clean = I.portable_identity(identity())
    conn = _owner_conn(fetchrow={"FROM cappe_studio_identities": {"identity": clean}, "INSERT INTO cappe_posts": _returning(None)})
    with _blog_client(monkeypatch, conn) as client:
        res = client.post(f"/sites/{SITE}/posts", json={"title": "A new issue", "format": "pages"})
    assert res.status_code == 201, res.text
    saved = json.loads(conn.args_for('INSERT INTO cappe_posts')[8])["doc"]["identity"]
    assert saved == clean


@pytest.mark.parametrize("action", ["save", "discard", "restore"])
def test_older_clients_cannot_strip_an_existing_identity(monkeypatch, action):
    raw = S.normalize_doc(document())
    row = paged_row(content=json.dumps({"doc": raw}))
    conn = Conn(fetchrow={"SELECT * FROM cappe_sites": SITE_ROW, "FOR UPDATE": row},
                fetchval={"SELECT content FROM cappe_post_revisions": json.dumps({"doc": raw})})
    path = f"/sites/{SITE}/studio/stories/{POST}"
    with client_for(monkeypatch, conn) as client:
        if action == 'save':
            res = client.put(path, json={"base_rev": row['rev'], "doc": S.starter_doc()})
        else:
            suffix = '/discard' if action == 'discard' else f'/revisions/{uuid4()}/restore'
            res = client.post(path + suffix, json={"base_rev": row['rev']})
    assert res.status_code == 409 and res.json()['detail']['code'] == 'studio_upgrade'
    assert not conn.sql_for('execute')


def test_current_clients_declare_identity_support():
    S.normalize_doc(document())
    studio._identity_supported(1, document())
