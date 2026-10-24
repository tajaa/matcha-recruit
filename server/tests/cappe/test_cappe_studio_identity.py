"""Live visual systems: normalization, rendering, safe snapshots and owner CAS.
All HTTP persistence is mocked; no live database or migration is used.
"""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.cappe.routes import studio
from app.cappe.services.magazine.studio import bank as B, identity as I, schema as S, render as R, text_view as T
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


@pytest.mark.parametrize('composed', [True, False])
def test_repeating_empty_composed_lines_cannot_amplify_rendering_work(composed):
    raw = document(); raw['items'] = []; raw['threads'] = []
    parent = raw['identity']['parents'][0]
    parent['threads'][0]['paras'] = [{'runs': [{'t': ''}]}] * (1 if composed else 8000)
    if composed:
        parent['threads'][0]['comp'] = {'lines': [[0, 0, 0, 0, 0, 0, 0, 0]] * 8000}
    raw['pages'] = [{'id': f'p{k}', 'parent': 'pl1'} for k in range(4)]
    with pytest.raises(S.DocError, match='too many composed lines'):
        S.normalize_doc(raw)


def test_parent_capture_preserves_semantic_text_and_repeated_instances_respect_hidden_frames_and_paywalls():
    raw = document(); raw['items'] = []; raw['threads'] = []
    raw['pages'] = [{'id': 'p1', 'parent': 'pl1'}, {'id': 'p2', 'parent': 'pl1'}]
    raw['identity']['parents'][0]['threads'][0]['paras'] = [{'style': 'ps1', 'runs': [{'t': 'Visible article words.'}]}]
    doc = S.normalize_doc(raw)
    blocks = T.text_blocks(doc, paywall=2)
    wall = next(k for k, b in enumerate(blocks) if b['type'] == 'paywall')
    assert 'Visible article words.' in json.dumps(blocks[:wall])
    assert 'Visible article words.' in json.dumps(blocks[wall + 1:])
    doc['identity']['parents'][0]['items'][0]['hidden'] = True
    assert all('Visible article words.' not in json.dumps(b) for b in T.text_blocks(doc))


@pytest.mark.asyncio
async def test_graphic_lookup_includes_unused_parent_definitions_at_the_local_frame_limit():
    shas = [f'{n:064x}' for n in range(S.L.MAX_ITEMS + 1)]
    items = [{'kind': 'graphic', 'src': sha} for sha in shas]
    raw = {'items': items[:-1], 'identity': {'parents': [{'items': items[-1:]}]}}
    conn = Conn(fetch={'FROM cappe_studio_bank': [{'sha': s, 'mono': True, 'fit': 'contain'} for s in shas]})
    found = await B.doc_graphics(conn, raw)
    assert conn.args_for('FROM cappe_studio_bank')[0] == shas
    assert len(found) == len(shas) and shas[-1] in found


@pytest.mark.parametrize('body', [{'base_rev': 0, 'identity': '\ud800'}, {'base_rev': '\udfff', 'identity': {}}, {'identity': {'bad': '\ud800'}}])
def test_malformed_unicode_request_values_return_422_without_database_access(monkeypatch, body):
    conn = Conn()
    with client_for(monkeypatch, conn) as client:
        response = client.put(f'/sites/{SITE}/studio/identity', content=json.dumps(body), headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert conn.calls == []


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


def test_a_collection_keeps_how_identity_styled_pages_look_without_naming_the_identity():
    # A collection goes into other stories, whose identities don't have these
    # styles or swatches: a reference to one they lack would make them unsavable.
    from app.cappe.services.magazine.studio.collections import collection_doc
    raw = document()
    raw["pages"][1].pop("parent")  # the Studio makes parent frames the page's own first
    raw["items"].append({"id": "r9", "kind": "rect", "page": raw["pages"][0]["id"], "x": 0, "y": 0, "w": 10, "h": 10,
                         "fill": "#000000", "fill_swatch": "sw1"})
    out = collection_doc(raw)
    assert "identity" not in out
    text = json.dumps(out)
    assert '"style"' not in text and '"swatch"' not in text and "fill_swatch" not in text and '"parent"' not in text
    run = out["threads"][0]["paras"][0]["runs"][0]
    assert run["size"] == 8 and run["color"] == "#ab3322"
    assert out["threads"][0]["paras"][0]["runs"][1]["it"] is True
    assert next(i for i in out["items"] if i["id"] == "r9")["fill"] == "#ab3322"
    # It goes into a story with no identity and saves there.
    assert S.normalize_doc({**S.starter_doc(), "items": out["items"], "threads": out["threads"],
                            "pages": out["pages"]})["threads"]
