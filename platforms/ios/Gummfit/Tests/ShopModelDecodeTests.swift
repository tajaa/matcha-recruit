import XCTest
@testable import Gummfit

/// Pins CappeProduct/CappeOrder decode against real server response shapes
/// (server/app/cappe/models/shop.py).
final class ShopModelDecodeTests: XCTestCase {
    func testProductDecodesWithOptionGroups() throws {
        let json = """
        {
          "id": "prod-1", "site_id": "site-1", "name": "Latte", "description": "House blend",
          "price_cents": 450, "currency": "USD", "image_url": null, "sku": null,
          "inventory": null, "low_stock_threshold": null, "status": "active", "sort_order": 0,
          "fulfillment": "physical", "digital_file_url": null, "booking_type_id": null,
          "requires_approval": false, "category": "drinks",
          "option_groups": [
            {"id": "grp-1", "name": "Size", "select_type": "single", "required": true, "sort_order": 0,
             "options": [{"id": "opt-1", "name": "Large", "price_delta_cents": 100, "sort_order": 0, "inventory": null}]}
          ]
        }
        """
        let product = try JSONDecoder().decode(CappeProduct.self, from: Data(json.utf8))
        XCTAssertEqual(product.fulfillment, .physical)
        XCTAssertEqual(product.option_groups.count, 1)
        XCTAssertEqual(product.option_groups[0].options[0].price_delta_cents, 100)
    }

    func testOrderDecodesWithItemsAndShippingAddress() throws {
        let json = """
        {
          "id": "order-1", "site_id": "site-1", "customer_email": "jane@example.com",
          "customer_name": "Jane Doe", "status": "paid", "subtotal_cents": 550, "tax_cents": 0,
          "shipping_cents": 0, "shipping_address": {"name": "Jane Doe", "line1": "1 Main St", "city": "LA", "state": "CA", "postal_code": "90001", "country": "US"},
          "carrier": null, "tracking_number": null, "total_cents": 550, "receipt_number": "R-1",
          "currency": "USD", "payment_ref": null, "note": null, "requires_approval": false,
          "approved_at": null, "decline_reason": null, "created_at": "2026-08-01T00:00:00Z",
          "updated_at": "2026-08-01T00:00:00Z",
          "items": [
            {"id": "item-1", "product_id": "prod-1", "title": "Latte", "unit_price_cents": 450, "quantity": 1,
             "fulfillment": "physical", "selected_options": [{"group": "Size", "name": "Large", "price_delta_cents": 100}],
             "deliverable_url": null, "booking_id": null}
          ]
        }
        """
        let order = try JSONDecoder().decode(CappeOrder.self, from: Data(json.utf8))
        XCTAssertEqual(order.status, .paid)
        XCTAssertEqual(order.shipping_address?.city, "LA")
        XCTAssertEqual(order.items[0].selected_options[0].name, "Large")
    }

    func testUnknownFulfillmentAndOrderStatusFallBackNotThrow() throws {
        XCTAssertEqual(try JSONDecoder().decode(Fulfillment.self, from: Data("\"subscription\"".utf8)), .unknown)
        XCTAssertEqual(try JSONDecoder().decode(OrderStatus.self, from: Data("\"chargeback\"".utf8)), .unknown)
        XCTAssertEqual(try JSONDecoder().decode(DiscountScope.self, from: Data("\"bundle\"".utf8)), .unknown)
    }

    /// `DiscountScope.unknown` used to be re-encoded as the literal string
    /// `"unknown"`, which would 422 the whole discount PUT against the
    /// server's `Literal[...]` field. `CappeDiscountInput` now threads the
    /// raw wire string through so a scope this build doesn't recognize
    /// survives a load→save round trip unchanged.
    func testUnknownDiscountScopeRoundTripsRawValue() throws {
        let json = """
        {"id": "disc-1", "site_id": "site-1", "label": "Flash sale", "percent_off": 20,
         "scope": "flash_sale", "target_id": null, "active": true, "starts_on": null,
         "ends_on": null, "location_id": null, "created_at": "2026-08-01T00:00:00Z"}
        """
        let discount = try JSONDecoder().decode(CappeDiscount.self, from: Data(json.utf8))
        XCTAssertEqual(discount.scope, .unknown)

        let input = CappeDiscountInput(from: discount)
        let encoded = try JSONEncoder().encode(input)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        XCTAssertEqual(obj["scope"] as? String, "flash_sale")
    }

    /// A known scope still round-trips normally, and switching the picker to
    /// a different known scope (simulated by reassigning `.scope`) updates
    /// the encoded value rather than sticking to the original raw string.
    func testKnownDiscountScopeRoundTripsAndIsSettable() throws {
        let json = """
        {"id": "disc-2", "site_id": "site-1", "label": "10% off", "percent_off": 10,
         "scope": "all", "target_id": null, "active": true, "starts_on": null,
         "ends_on": null, "location_id": null, "created_at": "2026-08-01T00:00:00Z"}
        """
        let discount = try JSONDecoder().decode(CappeDiscount.self, from: Data(json.utf8))
        var input = CappeDiscountInput(from: discount)
        XCTAssertEqual(input.scope, .all)

        input.scope = .booking_type
        let encoded = try JSONEncoder().encode(input)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        XCTAssertEqual(obj["scope"] as? String, "booking_type")
    }
}
