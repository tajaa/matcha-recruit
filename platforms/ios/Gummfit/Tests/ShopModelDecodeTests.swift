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
}
