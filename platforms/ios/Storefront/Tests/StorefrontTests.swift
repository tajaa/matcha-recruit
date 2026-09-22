import XCTest
@testable import Ahnimal

final class StorefrontTests: XCTestCase {
    private let decoder: JSONDecoder = {
        let value = JSONDecoder()
        value.keyDecodingStrategy = .convertFromSnakeCase
        return value
    }()

    func testProductFixtureDecodesCappeShape() throws {
        let data = Data(#"""
        {
          "id":"550e8400-e29b-41d4-a716-446655440000","name":"Soap","description":"Clean",
          "price_cents":1200,"discounted_price_cents":1000,"currency":"USD","image_url":null,
          "inventory":4,"category":"Care","fulfillment":"physical","sort_order":2,
          "option_groups":[{"id":"g","name":"Size","select_type":"single","required":true,
            "options":[{"id":"o","name":"Large","price_delta_cents":200,"inventory":2}]}],
          "subscription_intervals":["month"],"subscription_discount_bps":1000
        }
        """#.utf8)
        let value = try decoder.decode(Product.self, from: data)
        XCTAssertEqual(value.name, "Soap")
        XCTAssertEqual(value.optionGroups.first?.options.first?.priceDeltaCents, 200)
        XCTAssertEqual(value.subscriptionIntervals, ["month"])
    }

    func testOrderQuoteAndShopperFixturesDecode() throws {
        let quote = try decoder.decode(Quote.self, from: Data(#"""
        {
          "lines":[{"product_id":"p","quantity":2,"unit_price_cents":500,"available":true,"title":"Tea"}],
          "subtotal_cents":1000,"tax_cents":80,"shipping_cents":300,"total_cents":1380,"currency":"USD"
        }
        """#.utf8))
        XCTAssertEqual(quote.totalCents, 1380)

        let order = try decoder.decode(Order.self, from: Data(#"""
        {
          "id":"order-id","order_token":"0123456789abcdef0123456789abcdef","status":"paid",
          "subtotal_cents":1000,"tax_cents":80,"shipping_cents":300,"total_cents":1380,"currency":"USD",
          "created_at":"2026-09-19T10:00:00Z","carrier":null,"tracking_number":null,
          "items":[{"product_id":"p","title":"Tea","quantity":2,"unit_price_cents":500,"fulfillment":"physical"}]
        }
        """#.utf8))
        XCTAssertEqual(order.id, "order-id")
        XCTAssertEqual(order.items.first?.title, "Tea")

        let shopper = try decoder.decode(Shopper.self, from: Data(#"""
        {
          "id":"s","site_id":"site","email":"buyer@example.com","name":null,"phone":null,"push_order_updates":true
        }
        """#.utf8))
        XCTAssertTrue(shopper.pushOrderUpdates)
    }

    func testCartIdentityAndSubscriptionMathIncludeOptions() throws {
        let product = try decoder.decode(Product.self, from: Data(#"""
        {
          "id":"p","name":"Soap","description":null,"price_cents":1000,"discounted_price_cents":null,
          "currency":"USD","image_url":null,"inventory":null,"category":null,"fulfillment":"physical","sort_order":0,
          "option_groups":[{"id":"g","name":"Size","select_type":"single","required":true,
            "options":[{"id":"large","name":"Large","price_delta_cents":200,"inventory":null}]}],
          "subscription_intervals":["month"],"subscription_discount_bps":1000
        }
        """#.utf8))
        let recurring = CartLine(productId: "p", quantity: 2, selectedOptionIds: ["large"], interval: "month")
        let oneTime = CartLine(productId: "p", quantity: 2, selectedOptionIds: ["large"], interval: nil)
        XCTAssertNotEqual(recurring.id, oneTime.id)
        XCTAssertEqual(recurring.unitPrice(in: product), 1080)
        XCTAssertEqual(oneTime.unitPrice(in: product), 1200)
    }

    func testDeepLinksValidateSchemeAndPushPayload() {
        XCTAssertEqual(
            DeepLinkHandler.token(from: URL(string: "ahnimal://order/0123456789abcdef0123456789abcdef")!, scheme: "ahnimal"),
            "0123456789abcdef0123456789abcdef"
        )
        XCTAssertNil(DeepLinkHandler.token(from: URL(string: "other://order/0123456789abcdef0123456789abcdef")!, scheme: "ahnimal"))
        XCTAssertEqual(
            DeepLinkHandler.token(from: ["type": "order", "order_token": "0123456789abcdef0123456789abcdef"]),
            "0123456789abcdef0123456789abcdef"
        )
    }

    func testConfigReadsTenantKeys() {
        let value = Config(info: [
            "CappeAPIBase": "https://api.example.test/api/cappe/",
            "CappeSiteSlug": "shop",
            "CappeSiteOrigin": "https://shop.example.test",
            "AppURLScheme": "shopapp",
            "CappeDisplayName": "Shop Name",
            "CappeTagline": "Shop tagline",
        ], environment: [:])
        XCTAssertEqual(value.apiBase.absoluteString, "https://api.example.test/api/cappe")
        XCTAssertEqual(value.sitePath, "/public/sites/shop")
        XCTAssertEqual(value.scheme, "shopapp")
        XCTAssertEqual(value.displayName, "Shop Name")
        XCTAssertEqual(value.tagline, "Shop tagline")
    }

    @MainActor
    func testHostedCheckoutCallbackDistinguishesSuccessAndCancel() {
        XCTAssertEqual(
            CheckoutService.hostedResult(from: URL(string: "ahnimal://order/token?r=success")),
            .success
        )
        XCTAssertEqual(
            CheckoutService.hostedResult(from: URL(string: "ahnimal://order/token?r=cancel")),
            .cancel
        )
        XCTAssertNil(CheckoutService.hostedResult(from: URL(string: "ahnimal://order/token")))
    }

    func testOrderCursorQueryPreservesTimezoneOffsetPlus() {
        let cursor = "2026-09-19T10:00:00+00:00|11111111-1111-1111-1111-111111111111"
        let query = StorefrontURL.queryString([
            URLQueryItem(name: "cursor", value: cursor),
        ])

        XCTAssertTrue(query.contains("%2B00:00"))
        XCTAssertFalse(query.contains("+"))

        let components = URLComponents(string: "https://shop.example.test/orders\(query)")
        XCTAssertEqual(
            components?.queryItems?.first(where: { $0.name == "cursor" })?.value,
            cursor
        )
    }

    @MainActor
    func testOrderLinkSelectsAccountAndBuildsDirectRoute() {
        let router = AppRouter()
        router.openOrder("0123456789abcdef0123456789abcdef")
        XCTAssertEqual(router.selectedTab, .account)
        XCTAssertEqual(router.accountPath, [
            .order("0123456789abcdef0123456789abcdef")
        ])

        router.handleSessionEnded()
        XCTAssertEqual(router.accountPath, [
            .order("0123456789abcdef0123456789abcdef")
        ])
    }
}
