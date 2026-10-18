import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.services import stripe_catalog as catalog

REAL_LOAD_PRODUCT = catalog.load_product


class MissingResource(Exception):
    code = "resource_missing"


@pytest.fixture
def setup(monkeypatch):
    settings = SimpleNamespace(stripe_secret_key="sk_test_placeholder", stripe_webhook_secret="whsec_test", app_base_url="https://example.com")
    definitions = {
        "incidents": catalog.CatalogProduct("incidents", "Matcha Incidents", "Incidents", True, (
            catalog.CatalogPrice("matcha_lite", "Standard", 5000, "block", 10),
            catalog.CatalogPrice("matcha_lite_essentials", "Essentials", 4000, "block", 10),
        )),
        "scheduler": catalog.CatalogProduct("scheduler", "Matcha Scheduler", "Scheduling", True, (
            catalog.CatalogPrice("scheduler", "Monthly", 500, "per_location"),
        )),
    }
    state = {}
    remote_products = {}
    remote_prices = {}
    locks = {}
    calls = []
    fail = {"after_price_create": False}

    class Connection:
        held = None

        @asynccontextmanager
        async def transaction(self):
            try:
                yield
            finally:
                if self.held:
                    self.held.release()
                    self.held = None

        async def fetchval(self, sql, key):
            assert "platform_settings" in sql
            return state.get(key)

        async def execute(self, sql, *args):
            if "pg_advisory_xact_lock" in sql:
                self.held = locks.setdefault(args[0], asyncio.Lock())
                await self.held.acquire()
            else:
                assert "INSERT INTO platform_settings" in sql
                state[args[0]] = args[1]

    @asynccontextmanager
    async def connection():
        yield Connection()

    class Product:
        @staticmethod
        def retrieve(product_id, **kwargs):
            if product_id not in remote_products:
                raise MissingResource()
            return remote_products[product_id].copy()

        @staticmethod
        def create(**kwargs):
            product_id = kwargs["id"]
            assert product_id not in remote_products
            calls.append(("product.create", product_id, kwargs.get("idempotency_key")))
            remote_products[product_id] = {k: v for k, v in kwargs.items() if k not in ("api_key", "idempotency_key")}
            return remote_products[product_id].copy()

        @staticmethod
        def modify(product_id, **kwargs):
            remote_products[product_id].update({k: v for k, v in kwargs.items() if k != "api_key"})
            return remote_products[product_id].copy()

    class Price:
        @staticmethod
        def list(lookup_keys, **kwargs):
            return {"data": [r.copy() for r in remote_prices.values() if r["lookup_key"] in lookup_keys]}

        @staticmethod
        def create(**kwargs):
            price_id = f"price_{len(remote_prices) + 1}"
            calls.append(("price.create", price_id, kwargs.get("idempotency_key")))
            remote_prices[price_id] = {
                **{k: v for k, v in kwargs.items() if k not in ("api_key", "idempotency_key")},
                "id": price_id, "active": True, "billing_scheme": "per_unit",
                "recurring": {"interval": "month", "interval_count": 1, "usage_type": "licensed"},
            }
            if fail["after_price_create"]:
                fail["after_price_create"] = False
                raise TimeoutError("Timeout after Stripe created the price")
            return remote_prices[price_id].copy()

        @staticmethod
        def retrieve(price_id, **kwargs):
            if price_id not in remote_prices:
                raise MissingResource()
            return remote_prices[price_id].copy()

        @staticmethod
        def modify(price_id, **kwargs):
            if price_id not in remote_prices:
                raise MissingResource()
            remote_prices[price_id].update({k: v for k, v in kwargs.items() if k != "api_key"})
            return remote_prices[price_id].copy()

    fake_stripe = SimpleNamespace(Account=SimpleNamespace(retrieve=lambda **kwargs: {"id": "acct_matcha"}), Product=Product, Price=Price)
    monkeypatch.setattr(catalog, "stripe", fake_stripe)
    monkeypatch.setattr(catalog, "get_settings", lambda: settings)
    monkeypatch.setattr(catalog, "get_connection", connection)
    monkeypatch.setattr(catalog, "load_product", AsyncMock(side_effect=lambda conn, key: definitions[key]))
    return SimpleNamespace(settings=settings, definitions=definitions, state=state, products=remote_products,
                           prices=remote_prices, calls=calls, fail=fail, stripe=fake_stripe)


@pytest.mark.asyncio
async def test_both_products_have_stable_ids_and_only_three_prices(setup):
    incidents = await catalog.sync_product("incidents")
    scheduler = await catalog.sync_product("scheduler")
    assert incidents["stripe_product_id"] != scheduler["stripe_product_id"]
    assert len(setup.products) == 2 and len(setup.prices) == 3
    assert set(incidents["prices"]) == set(catalog.INCIDENT_PLANS)
    assert await catalog.sync_product("incidents", force=False) == incidents
    await catalog.sync_product("scheduler")
    assert len(setup.products) == 2 and len(setup.prices) == 3
    assert all(call[2] for call in setup.calls)


@pytest.mark.asyncio
async def test_price_changes_create_a_new_price_and_archive_the_old_one(setup):
    original = await catalog.sync_product("scheduler")
    definition = setup.definitions["scheduler"]
    setup.definitions["scheduler"] = replace(definition, prices=(replace(definition.prices[0], amount_cents=900),))
    changed = await catalog.sync_product("scheduler")
    old_id = original["prices"]["scheduler"]["stripe_price_id"]
    new_id = changed["prices"]["scheduler"]["stripe_price_id"]
    assert old_id != new_id
    assert not setup.prices[old_id]["active"]
    assert setup.prices[old_id]["unit_amount"] == 500
    assert setup.prices[new_id]["unit_amount"] == 900
    assert len(setup.products) == 1
    # The fake has no Subscription API: repricing existing subscribers would fail.


@pytest.mark.asyncio
async def test_retry_after_stripe_success_and_timeout_reuses_the_price(setup):
    setup.fail["after_price_create"] = True
    with pytest.raises(catalog.CatalogError, match="Timeout"):
        await catalog.sync_product("scheduler")
    assert json.loads(next(iter(setup.state.values())))["status"] == "error"
    recovered = await catalog.sync_product("scheduler")
    assert recovered["status"] == "synced"
    assert len(setup.products) == len(setup.prices) == 1


@pytest.mark.asyncio
async def test_retry_after_database_failure_recovers_existing_remote_objects(setup, monkeypatch):
    write = catalog._write_state
    monkeypatch.setattr(catalog, "_write_state", AsyncMock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError, match="database unavailable"):
        await catalog.sync_product("scheduler")
    assert not setup.state
    monkeypatch.setattr(catalog, "_write_state", write)
    await catalog.sync_product("scheduler")
    assert len(setup.products) == len(setup.prices) == 1


@pytest.mark.asyncio
async def test_database_failure_does_not_archive_the_last_committed_checkout_price(setup, monkeypatch):
    original = await catalog.sync_product("scheduler")
    old_price = original["prices"]["scheduler"]["stripe_price_id"]
    source = setup.definitions["scheduler"]
    setup.definitions["scheduler"] = replace(source, prices=(replace(source.prices[0], amount_cents=900),))
    write = catalog._write_state
    monkeypatch.setattr(catalog, "_write_state", AsyncMock(side_effect=RuntimeError("Commit failed")))
    with pytest.raises(RuntimeError, match="Commit failed"):
        await catalog.sync_product("scheduler")
    assert setup.prices[old_price]["active"]
    monkeypatch.setattr(catalog, "_write_state", write)
    await catalog.sync_product("scheduler")
    assert not setup.prices[old_price]["active"]
    assert len(setup.prices) == 2


@pytest.mark.asyncio
async def test_price_retirement_never_archives_a_price_reselected_by_a_later_save(setup):
    state = await catalog.sync_product("scheduler")
    context = await catalog.catalog_context()
    price_id = state["prices"]["scheduler"]["stripe_price_id"]
    state["retired_price_ids"] = [price_id]
    setup.state[context.state_key("scheduler")] = json.dumps(state)
    await catalog._archive_retired_prices(context, "scheduler")
    assert setup.prices[price_id]["active"]
    assert json.loads(setup.state[context.state_key("scheduler")])["retired_price_ids"] == []


@pytest.mark.asyncio
async def test_concurrent_syncs_do_not_duplicate_the_catalog(setup):
    results = await asyncio.gather(*(catalog.sync_product("incidents") for _ in range(4)))
    assert len({result["stripe_product_id"] for result in results}) == 1
    assert len(setup.products) == 1 and len(setup.prices) == 2


@pytest.mark.asyncio
async def test_live_and_test_catalogs_are_separate(setup):
    test = await catalog.sync_product("scheduler")
    setup.settings.stripe_secret_key = "sk_live_placeholder"
    live = await catalog.sync_product("scheduler")
    assert not test["livemode"] and live["livemode"]
    assert test["stripe_product_id"] != live["stripe_product_id"]
    assert len(setup.state) == 2


@pytest.mark.asyncio
async def test_beta_products_cannot_be_synced(setup):
    with pytest.raises(catalog.CatalogError, match="Only Matcha"):
        await catalog.sync_product("espresso")
    assert not setup.products and not setup.prices and not setup.state


@pytest.mark.parametrize("product, price, count, locations, total, quantity", [
    ("incidents", "matcha_lite", 21, None, 15000, 3),
    ("incidents", "matcha_lite_essentials", 1, None, 4000, 1),
    ("scheduler", "scheduler", 40, 3, 1500, 3),
])
@pytest.mark.asyncio
async def test_checkout_uses_saved_price_with_the_correct_quantity(setup, product, price, count, locations, total, quantity):
    item = await catalog.checkout_line_item(product, price, headcount=count, locations=locations, amount_cents=total)
    assert item["price"] in setup.prices
    assert item["quantity"] == quantity
    assert setup.prices[item["price"]]["unit_amount"] * quantity == total


@pytest.mark.asyncio
async def test_checkout_refuses_a_stale_total(setup):
    with pytest.raises(catalog.CatalogError, match="Pricing changed"):
        await catalog.checkout_line_item("scheduler", "scheduler", headcount=40, locations=3, amount_cents=1000)


@pytest.mark.parametrize("model, headcount, locations, expected", [
    ("flat", 40, None, 1), ("per_seat", 40, None, 40),
    ("block", 21, None, 3), ("per_location", 40, 2, 2),
])
def test_quantity_matches_existing_pricing_models(model, headcount, locations, expected):
    assert catalog.CatalogPrice("test", "Test", 500, model, 10).quantity(headcount, locations) == expected


@pytest.mark.parametrize("count, locations", [(0, 1), (301, 1), (10, 0), (10, None)])
def test_quantity_refuses_invalid_counts(count, locations):
    with pytest.raises(catalog.CatalogError):
        catalog.CatalogPrice("test", "Test", 500, "per_location").quantity(count, locations)


@pytest.mark.asyncio
async def test_webhooks_retrieve_current_objects_instead_of_replaying_stale_snapshots(setup):
    old = await catalog.sync_product("scheduler")
    source = setup.definitions["scheduler"]
    setup.definitions["scheduler"] = replace(source, prices=(replace(source.prices[0], amount_cents=900),))
    new = await catalog.sync_product("scheduler")
    await catalog.reconcile_catalog_event({"id": old["stripe_product_id"], "name": "An outdated name"}, livemode=False)
    status = await catalog.catalog_status()
    scheduler = next(p for p in status["products"] if p["key"] == "scheduler")
    assert scheduler["status"] == "synced" and scheduler["webhook_verified_at"]
    assert scheduler["prices"][0]["stripe_price_id"] == new["prices"]["scheduler"]["stripe_price_id"]


@pytest.mark.asyncio
async def test_stripe_dashboard_drift_is_visible_and_repairable(setup):
    state = await catalog.sync_product("scheduler")
    price_id = state["prices"]["scheduler"]["stripe_price_id"]
    setup.prices[price_id]["active"] = False
    await catalog.reconcile_catalog_event({"object": "price", "id": price_id, "product": state["stripe_product_id"]}, livemode=False)
    assert json.loads(next(iter(setup.state.values())))["status"] == "out_of_sync"
    await catalog.sync_product("scheduler")
    assert setup.prices[price_id]["active"]
    assert len(setup.prices) == 1


@pytest.mark.asyncio
async def test_wrong_mode_or_connected_account_events_do_not_change_state(setup):
    state = await catalog.sync_product("scheduler")
    saved = setup.state.copy()
    event = {"id": state["stripe_product_id"]}
    await catalog.reconcile_catalog_event(event, livemode=True)
    await catalog.reconcile_catalog_event(event, livemode=False, account="acct_other")
    await catalog.reconcile_catalog_event({"id": "prod_beta"}, livemode=False)
    assert setup.state == saved


@pytest.mark.asyncio
async def test_webhook_configuration_preserves_payment_events_and_only_changes_the_matching_endpoint(setup):
    endpoint = SimpleNamespace(id="we_matcha", url="https://example.com/api/webhooks/stripe", status="enabled", enabled_events=["checkout.session.completed", "invoice.paid"])
    other = SimpleNamespace(id="we_cappe", url="https://example.com/api/cappe/webhook", status="enabled", enabled_events=["*"])
    modified = []
    setup.stripe.WebhookEndpoint = SimpleNamespace(
        list=lambda **kwargs: SimpleNamespace(auto_paging_iter=lambda: iter([other, endpoint])),
        modify=lambda endpoint_id, **kwargs: modified.append((endpoint_id, kwargs)),
    )
    result = await catalog.configure_catalog_webhook()
    assert result["catalog_events_enabled"]
    assert len(modified) == 1 and modified[0][0] == "we_matcha"
    assert set(modified[0][1]["enabled_events"]) == catalog.CATALOG_EVENTS | set(endpoint.enabled_events)
    assert (await catalog.catalog_status())["webhook"]["catalog_events_enabled"]


@pytest.mark.asyncio
async def test_webhook_setup_never_creates_an_endpoint_with_an_unknown_secret(setup):
    setup.stripe.WebhookEndpoint = SimpleNamespace(list=lambda **kwargs: SimpleNamespace(auto_paging_iter=lambda: iter([])))
    with pytest.raises(catalog.CatalogError, match="Expected one enabled"):
        await catalog.configure_catalog_webhook()


@pytest.mark.asyncio
async def test_a_local_price_save_survives_a_stripe_failure(setup, monkeypatch):
    monkeypatch.setattr(catalog, "sync_product", AsyncMock(side_effect=TimeoutError("Stripe unavailable")))
    await catalog.sync_after_save("incidents", changed_by="admin@example.com")


@pytest.mark.asyncio
async def test_incident_sources_preserve_sale_pricing_and_block_limits(setup, monkeypatch):
    pricing = SimpleNamespace(effective_price_per_block_cents=1234, block_size=7, min_headcount=2, max_headcount=200)
    getter = AsyncMock(return_value=pricing)
    monkeypatch.setattr(catalog, "get_matcha_lite_pricing", getter)
    source = await REAL_LOAD_PRODUCT(object(), "incidents")
    assert [call.args[1] for call in getter.await_args_list] == list(catalog.INCIDENT_PLANS)
    assert len(source.prices) == 2
    assert all((price.amount_cents, price.block_size, price.min_headcount, price.max_headcount) == (1234, 7, 2, 200) for price in source.prices)


@pytest.mark.parametrize("status, active", [("published", True), ("archived", True), ("draft", False)])
@pytest.mark.asyncio
async def test_scheduler_source_preserves_published_and_archived_checkout_contracts(setup, monkeypatch, status, active):
    product = SimpleNamespace(is_paid=True, name="Matcha Scheduler", description="Schedule café crews", status=status,
                              pricing_model="per_location", price_cents=500, block_size=None, min_headcount=1, max_headcount=300)
    monkeypatch.setattr(catalog, "get_product_by_slug", AsyncMock(return_value=product))
    source = await REAL_LOAD_PRODUCT(object(), "scheduler")
    assert source.active is active
    assert source.description == "Schedule café crews"
    assert source.prices[0].amount_cents == 500
    assert source.prices[0].pricing_model == "per_location"


@pytest.mark.asyncio
async def test_missing_scheduler_configuration_is_visible_in_admin(setup):
    original = setup.definitions["incidents"]
    async def missing(conn, key):
        if key == "scheduler":
            raise catalog.CatalogError("Set up schedule-comm first")
        return original
    catalog.load_product.side_effect = missing
    status = await catalog.catalog_status()
    assert status["products"][1]["status"] == "not_ready"
    assert "schedule-comm" in status["products"][1]["error"]


@pytest.mark.asyncio
async def test_missing_credentials_show_setup_without_creating_anything(setup):
    setup.settings.stripe_secret_key = None
    status = await catalog.catalog_status()
    assert not status["configured"] and status["account_id"] is None
    assert all(product["status"] == "not_configured" for product in status["products"])
    await catalog.sync_after_save("incidents")
    assert not setup.products


@pytest.mark.asyncio
async def test_a_changed_source_is_shown_as_out_of_sync_before_retry(setup):
    await catalog.sync_product("scheduler")
    source = setup.definitions["scheduler"]
    setup.definitions["scheduler"] = replace(source, prices=(replace(source.prices[0], amount_cents=750),))
    status = await catalog.catalog_status()
    assert status["products"][1]["status"] == "out_of_sync"


@pytest.mark.asyncio
async def test_sync_refuses_a_price_lookup_key_that_points_at_different_terms(setup):
    await catalog.sync_product("scheduler")
    next(iter(setup.prices.values()))["unit_amount"] = 1
    with pytest.raises(catalog.CatalogError, match="no longer matches"):
        await catalog.sync_product("scheduler")


@pytest.mark.asyncio
async def test_checkout_helpers_use_catalog_line_items_without_changing_activation_metadata(monkeypatch):
    from app.core.services import stripe_service
    from unittest.mock import Mock
    from uuid import uuid4

    create = Mock(return_value=SimpleNamespace(id="cs_test", url="https://example.com/checkout"))
    monkeypatch.setattr(stripe_service, "stripe", SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(create=create))))
    service = stripe_service.StripeService.__new__(stripe_service.StripeService)
    service.settings = SimpleNamespace(stripe_success_url="https://example.com/success", stripe_cancel_url="https://example.com/cancel")
    monkeypatch.setattr(service, "_ensure_secret_key", lambda: None)
    for method, extra in (
        ("create_matcha_lite_checkout", {}),
        ("create_custom_product_checkout", {"product_slug": "schedule-comm", "product_name": "Matcha Scheduler", "product_description": "", "location_count": 3}),
        ("create_lite_essentials_upgrade_checkout", {"old_subscription_id": "sub_previous"}),
    ):
        await getattr(service, method)(company_id=uuid4(), headcount=40, amount_cents=1500,
                                      line_item={"price": "price_saved", "quantity": 3}, **extra)
        payload = create.call_args.kwargs
        assert payload["line_items"] == [{"price": "price_saved", "quantity": 3}]
        assert payload["metadata"]["amount_cents"] == "1500"
        assert payload["subscription_data"]["metadata"] == payload["metadata"]


def test_catalog_routes_require_admin_authorization():
    from app.core.dependencies import require_admin
    from app.core.routes.admin.stripe_catalog import router
    from tests._helpers.routes import iter_api_routes

    routes = list(iter_api_routes(router))
    assert len(routes) == 4
    assert all(any(dependency.call is require_admin for dependency in route.dependant.dependencies) for route in routes)


@pytest.mark.asyncio
async def test_admin_sync_endpoint_rejects_beta_without_calling_stripe(monkeypatch):
    from app.core.routes.admin import stripe_catalog as routes
    from fastapi import HTTPException
    sync = AsyncMock()
    monkeypatch.setattr(catalog, "sync_product", sync)
    with pytest.raises(HTTPException) as exc:
        await routes.sync_stripe_catalog_product("espresso", SimpleNamespace(email="admin@example.com"))
    assert exc.value.status_code == 404
    sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_sync_returns_the_updated_catalog(setup):
    from app.core.routes.admin import stripe_catalog as routes
    response = await routes.sync_stripe_catalog_product("scheduler", SimpleNamespace(email="admin@example.com"))
    assert response["products"][1]["status"] == "synced"
    assert json.loads(next(iter(setup.state.values())))["changed_by"] == "admin@example.com"
    assert (await routes.get_stripe_catalog(None))["account_id"] == "acct_matcha"


@pytest.mark.parametrize("kind, status", [("configuration", 400), ("network", 502)])
@pytest.mark.asyncio
async def test_admin_sync_failure_is_actionable_and_does_not_claim_the_price_save_failed(monkeypatch, kind, status):
    from app.core.routes.admin import stripe_catalog as routes
    from fastapi import HTTPException
    error = catalog.CatalogError("Configure Stripe first") if kind == "configuration" else TimeoutError("Stripe timeout")
    monkeypatch.setattr(catalog, "sync_product", AsyncMock(side_effect=error))
    with pytest.raises(HTTPException) as exc:
        await routes.sync_stripe_catalog_product("incidents", SimpleNamespace(email="admin@example.com"))
    assert exc.value.status_code == status
    if status == 502:
        assert "price is saved" in exc.value.detail


@pytest.mark.asyncio
async def test_catalog_status_failure_is_reported_as_unavailable(monkeypatch):
    from app.core.routes.admin import stripe_catalog as routes
    from fastapi import HTTPException
    monkeypatch.setattr(catalog, "catalog_status", AsyncMock(side_effect=TimeoutError("Stripe timeout")))
    with pytest.raises(HTTPException) as exc:
        await routes.get_stripe_catalog(None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_admin_product_details_update_stripe_without_repricing_subscriptions(setup):
    from app.core.models.stripe_catalog import StripeCatalogDetails
    from app.core.routes.admin import stripe_catalog as routes
    await catalog.sync_product("incidents")
    prices = set(setup.prices)
    await routes.update_stripe_catalog_details(
        "incidents", StripeCatalogDetails(name="Matcha Incident Reporting", description="Reports through closure"),
        SimpleNamespace(email="admin@example.com"),
    )
    assert set(setup.prices) == prices
    product = next(iter(setup.products.values()))
    assert product["name"] == "Matcha Incident Reporting" and product["description"] == "Reports through closure"
    status = await catalog.catalog_status()
    assert status["products"][0]["display_name"] == "Matcha Incident Reporting"
    # A later pricing-page save must preserve the explicitly edited checkout copy.
    await catalog.sync_product("incidents")
    assert next(iter(setup.products.values()))["name"] == "Matcha Incident Reporting"


@pytest.mark.asyncio
async def test_catalog_webhook_failures_release_the_event_for_retry(monkeypatch):
    from app.core.routes.billing import stripe_webhook as routes

    event = SimpleNamespace(type="product.updated", id="evt_catalog", livemode=False, account=None,
                            data=SimpleNamespace(object=SimpleNamespace(to_dict=lambda: {"id": "prod_test"})))
    monkeypatch.setattr(routes, "StripeService", lambda: SimpleNamespace(verify_webhook=AsyncMock(return_value=event)))
    monkeypatch.setattr(routes, "_claim_event", AsyncMock(return_value=True))
    release = AsyncMock()
    monkeypatch.setattr(routes, "_release_event", release)
    monkeypatch.setattr(routes, "reconcile_catalog_event", AsyncMock(side_effect=RuntimeError("Temporary failure")))
    request = SimpleNamespace(body=AsyncMock(return_value=b"payload"), headers={"stripe-signature": "sig_test"})
    with pytest.raises(RuntimeError, match="Temporary failure"):
        await routes.stripe_webhook(request)
    release.assert_awaited_once_with("evt_catalog")
