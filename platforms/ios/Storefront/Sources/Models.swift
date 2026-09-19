import Foundation

struct ProductOption: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let priceDeltaCents: Int
    let inventory: Int?
}

struct OptionGroup: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let selectType: String
    let required: Bool
    let options: [ProductOption]
}

struct Product: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let description: String?
    let priceCents: Int
    let discountedPriceCents: Int?
    let currency: String
    let imageUrl: String?
    let inventory: Int?
    let category: String?
    let fulfillment: String
    let sortOrder: Int
    let optionGroups: [OptionGroup]
    let subscriptionIntervals: [String]
    let subscriptionDiscountBps: Int

    var displayPriceCents: Int { discountedPriceCents ?? priceCents }
    var imageURL: URL? { imageUrl.flatMap(URL.init(string:)) }
}

struct Shopper: Codable, Identifiable {
    let id: String
    let siteId: String
    let email: String
    var name: String?
    var phone: String?
    var pushOrderUpdates: Bool
}

struct Tokens: Codable {
    let accessToken: String
    let refreshToken: String
    let shopper: Shopper
}

struct CartLine: Codable, Identifiable, Equatable {
    var productId: String
    var quantity: Int
    var selectedOptionIds: [String]
    var interval: String?

    var id: String {
        productId + ":" + selectedOptionIds.sorted().joined(separator: ",") + ":" + (interval ?? "once")
    }

    var requestObject: [String: Any] {
        [
            "product_id": productId,
            "quantity": quantity,
            "selected_option_ids": selectedOptionIds,
        ]
    }

    func unitPrice(in product: Product) -> Int {
        let selected = Set(selectedOptionIds)
        let delta = product.optionGroups
            .flatMap(\.options)
            .filter { selected.contains($0.id) }
            .reduce(0) { $0 + $1.priceDeltaCents }
        let oneTime = max(0, product.displayPriceCents + delta)
        guard interval != nil else { return oneTime }
        return oneTime * (10_000 - product.subscriptionDiscountBps) / 10_000
    }
}

struct QuoteLine: Decodable {
    let productId: String
    let quantity: Int
    let unitPriceCents: Int
    let available: Bool
    let title: String?
}

struct Quote: Decodable {
    let lines: [QuoteLine]
    let subtotalCents: Int
    let taxCents: Int
    let shippingCents: Int
    let totalCents: Int
    let currency: String
}

struct OrderItem: Decodable, Identifiable {
    var id: String { (productId ?? title) + ":" + String(unitPriceCents) + ":" + String(quantity) }
    let productId: String?
    let title: String
    let quantity: Int
    let unitPriceCents: Int
    let fulfillment: String?
    let downloadUrl: String?
    let deliverableUrl: String?
}

struct Order: Decodable, Identifiable {
    private let rawId: String?
    let orderId: String?
    let orderToken: String?
    let status: String
    let subtotalCents: Int?
    let taxCents: Int?
    let shippingCents: Int?
    let totalCents: Int?
    let currency: String
    let createdAt: String?
    let carrier: String?
    let trackingNumber: String?
    let items: [OrderItem]

    var id: String { rawId ?? orderId ?? orderToken ?? UUID().uuidString }

    private enum CodingKeys: String, CodingKey {
        case rawId = "id"
        case orderId, orderToken, status, subtotalCents, taxCents, shippingCents
        case totalCents, currency, createdAt, carrier, trackingNumber, items
    }
}

struct OrderPage: Decodable {
    let orders: [Order]
    let nextCursor: String?
}

struct Checkout: Decodable {
    let checkoutUrl: String?
    let orderToken: String
    let subscriptionId: String?
}

struct Subscription: Decodable, Identifiable {
    let id: String
    let status: String
    let interval: String
    let totalCents: Int
    let currency: String
    let cancelAtPeriodEnd: Bool
    let currentPeriodEnd: String?
    let items: [OrderItem]
}

struct Address: Codable, Identifiable {
    var id: String?
    var label: String?
    var name: String = ""
    var line1: String = ""
    var line2: String?
    var city: String = ""
    var region: String?
    var postalCode: String = ""
    var country: String = "US"
    var phone: String?
    var isDefault: Bool = false

    var requestObject: [String: Any] {
        [
            "label": label ?? NSNull(),
            "name": name,
            "line1": line1,
            "line2": line2 ?? NSNull(),
            "city": city,
            "region": region ?? NSNull(),
            "postal_code": postalCode,
            "country": country,
            "phone": phone ?? NSNull(),
            "is_default": isDefault,
        ]
    }
}

struct BlogPost: Decodable, Identifiable {
    let id: String
    let title: String
    let slug: String
    let excerpt: String?
    let body: String?
    let coverImageUrl: String?
}

struct Empty: Decodable {}

struct APIError: LocalizedError {
    let status: Int
    let message: String
    var errorDescription: String? { message }
}

func money(_ cents: Int, _ currency: String = "USD") -> String {
    (Double(cents) / 100).formatted(.currency(code: currency))
}
