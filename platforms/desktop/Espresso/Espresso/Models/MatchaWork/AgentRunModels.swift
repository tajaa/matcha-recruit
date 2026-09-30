import Foundation

// Agent cards (`mw_tasks.category == "agent"`): the server's web agent answers
// the card with a structured result per review round.
// Backend: server/app/matcha/routes/matcha_work/agent_cards.py +
// services/matcha_work/agent_card/schema.py (`agent_result.v1`).

struct MWAgentLink: Decodable, Hashable {
    let retailer: String
    let url: String
    let price: Double?
}

struct MWAgentReview: Decodable, Hashable {
    let quote: String
    let sourceName: String
    let url: String
    let sentiment: String

    enum CodingKeys: String, CodingKey {
        case quote, url, sentiment
        case sourceName = "source_name"
    }
}

struct MWAgentImage: Decodable, Hashable {
    let url: String
    let pageUrl: String
    let alt: String

    enum CodingKeys: String, CodingKey {
        case url, alt
        case pageUrl = "page_url"
    }
}

struct MWAgentPrice: Decodable, Hashable {
    let amount: Double
    let currency: String
    let sourceUrl: String

    enum CodingKeys: String, CodingKey {
        case amount, currency
        case sourceUrl = "source_url"
    }
}

struct MWAgentRating: Decodable, Hashable {
    let value: Double
    let scale: Double
    let count: Int?
    let sourceUrl: String

    enum CodingKeys: String, CodingKey {
        case value, scale, count
        case sourceUrl = "source_url"
    }
}

struct MWAgentPick: Decodable, Hashable {
    let name: String
    let brand: String
    let why: [String]
    let price: MWAgentPrice?
    let rating: MWAgentRating?
    let reviews: [MWAgentReview]
    let images: [MWAgentImage]
    let buyLinks: [MWAgentLink]

    enum CodingKeys: String, CodingKey {
        case name, brand, why, price, rating, reviews, images
        case buyLinks = "buy_links"
    }
}

struct MWAgentCriterion: Decodable, Hashable {
    let name: String
    let why: String
}

struct MWAgentSection: Decodable, Hashable {
    let heading: String
    let bodyMd: String

    enum CodingKeys: String, CodingKey {
        case heading
        case bodyMd = "body_md"
    }
}

struct MWAgentSource: Decodable, Hashable {
    let title: String
    let url: String
}

struct MWAgentResult: Decodable, Hashable {
    let headline: String
    let summary: String
    let answerType: String
    let criteria: [MWAgentCriterion]
    let topPick: MWAgentPick?
    let alternatives: [MWAgentPick]
    let sections: [MWAgentSection]
    let caveats: [String]
    let sources: [MWAgentSource]
    let confidence: String
    let changesFromPrevious: String?
    /// A flight search's chosen offers (answer_type "flights").
    let flights: MWAgentFlights?

    enum CodingKeys: String, CodingKey {
        case headline, summary, criteria, alternatives, sections, caveats, sources, confidence, flights
        case answerType = "answer_type"
        case topPick = "top_pick"
        case changesFromPrevious = "changes_from_previous"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        headline = try c.decode(String.self, forKey: .headline)
        summary = try c.decode(String.self, forKey: .summary)
        answerType = try c.decode(String.self, forKey: .answerType)
        criteria = try c.decode([MWAgentCriterion].self, forKey: .criteria)
        topPick = try c.decodeIfPresent(MWAgentPick.self, forKey: .topPick)
        alternatives = try c.decode([MWAgentPick].self, forKey: .alternatives)
        sections = try c.decode([MWAgentSection].self, forKey: .sections)
        caveats = try c.decode([String].self, forKey: .caveats)
        sources = try c.decode([MWAgentSource].self, forKey: .sources)
        confidence = try c.decode(String.self, forKey: .confidence)
        changesFromPrevious = try c.decodeIfPresent(String.self, forKey: .changesFromPrevious)
        // Lenient: an odd flights block never costs the rest of the result.
        flights = try? c.decodeIfPresent(MWAgentFlights.self, forKey: .flights)
    }
}

// MARK: - Flights (server: agent_card/flights.py)
// Every field except label/why is the server's own Duffel search data.

struct MWFlightSegment: Decodable, Hashable {
    let carrier: String
    let flightNumber: String
    let origin: String
    let destination: String
    let departingAt: String
    let arrivingAt: String

    enum CodingKeys: String, CodingKey {
        case carrier, origin, destination
        case flightNumber = "flight_number"
        case departingAt = "departing_at"
        case arrivingAt = "arriving_at"
    }
}

struct MWFlightSlice: Decodable, Hashable {
    let origin: String
    let destination: String
    /// The airport's local wall-clock time, no offset: "2026-11-12T07:05:00".
    let departingAt: String
    let arrivingAt: String
    let durationMinutes: Int?
    let stops: Int
    let segments: [MWFlightSegment]

    enum CodingKeys: String, CodingKey {
        case origin, destination, stops, segments
        case departingAt = "departing_at"
        case arrivingAt = "arriving_at"
        case durationMinutes = "duration_minutes"
    }
}

struct MWFlightOption: Decodable, Hashable, Identifiable {
    struct Bags: Decodable, Hashable {
        let checked: Int
        let carryOn: Int
        enum CodingKeys: String, CodingKey { case checked; case carryOn = "carry_on" }
    }
    struct Conditions: Decodable, Hashable {
        let refundable: Bool?
        let changeable: Bool?
    }

    let id: String
    let label: String?
    let why: [String]
    /// "single", or "separate" for a round trip priced as two one-way tickets.
    let ticketing: String
    let totalAmount: String
    let currency: String
    let trueTotalAmount: String?
    let bagNote: String?
    let carriers: [String]
    let slices: [MWFlightSlice]
    let bagsIncluded: Bags
    let conditions: Conditions
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case id, label, why, ticketing, currency, carriers, slices, conditions, warnings
        case totalAmount = "total_amount"
        case trueTotalAmount = "true_total_amount"
        case bagNote = "bag_note"
        case bagsIncluded = "bags_included"
    }
}

struct MWAgentFlights: Decodable, Hashable {
    struct Privacy: Decodable, Hashable {
        let via: String
        let sent: [String]
        let notSent: [String]
        enum CodingKeys: String, CodingKey { case via, sent; case notSent = "not_sent" }
    }

    let querySummary: String
    let options: [MWFlightOption]
    let searchedAt: String?
    /// Duffel sandbox fares: not real prices.
    let testData: Bool
    let privacy: Privacy?

    enum CodingKeys: String, CodingKey {
        case options, privacy
        case querySummary = "query_summary"
        case searchedAt = "searched_at"
        case testData = "test_data"
    }
}

/// Flight times are airport-local wall-clock strings; they're read as text,
/// never through Date and the viewer's time zone.
enum FlightFormat {
    private static let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    private static let weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    private static func parts(_ iso: String) -> (y: Int, m: Int, d: Int, h: Int?, min: Int?)? {
        let chars = Array(iso)
        guard chars.count >= 10, let y = Int(String(chars[0..<4])), let m = Int(String(chars[5..<7])),
              let d = Int(String(chars[8..<10])), (1...12).contains(m) else { return nil }
        if chars.count >= 16, let h = Int(String(chars[11..<13])), let mi = Int(String(chars[14..<16])) {
            return (y, m, d, h, mi)
        }
        return (y, m, d, nil, nil)
    }

    /// "2026-11-12T13:40:00" → "1:40pm"
    static func clock(_ iso: String) -> String {
        guard let p = parts(iso), let h = p.h, let mi = p.min else { return "" }
        return "\(h % 12 == 0 ? 12 : h % 12):\(String(format: "%02d", mi))\(h < 12 ? "am" : "pm")"
    }

    private static func dayNumber(_ p: (y: Int, m: Int, d: Int, h: Int?, min: Int?)) -> Int? {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        guard let date = utc.date(from: DateComponents(year: p.y, month: p.m, day: p.d)) else { return nil }
        return Int(date.timeIntervalSince1970 / 86_400)
    }

    /// "2026-11-12T07:05:00" → "Thu, Nov 12"
    static func day(_ iso: String) -> String {
        guard let p = parts(iso), let n = dayNumber(p) else { return "" }
        // 1970-01-01 was a Thursday.
        return "\(weekdays[((n % 7) + 7 + 4) % 7]), \(months[p.m - 1]) \(p.d)"
    }

    /// Calendar days from departure to arrival: the "+1" on a red-eye.
    static func dayOffset(_ departing: String, _ arriving: String) -> Int {
        guard let a = parts(departing).flatMap(dayNumber), let b = parts(arriving).flatMap(dayNumber) else { return 0 }
        return b - a
    }

    static func duration(_ minutes: Int?) -> String {
        guard let minutes else { return "" }
        let h = minutes / 60, m = minutes % 60
        return h > 0 ? (m > 0 ? "\(h)h \(m)m" : "\(h)h") : "\(m)m"
    }

    static func stops(_ n: Int) -> String {
        n == 0 ? "Nonstop" : "\(n) stop\(n == 1 ? "" : "s")"
    }

    static func fare(_ amount: String?, _ currency: String) -> String {
        guard let amount, let value = Double(amount) else { return amount ?? "" }
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currency.isEmpty ? "USD" : currency
        return formatter.string(from: NSNumber(value: value)) ?? "\(amount) \(currency)"
    }
}

struct MWAgentRunStep: Decodable, Hashable {
    let seq: Int
    let kind: String
    let label: String
    let status: String
}

struct MWAgentRun: Decodable, Identifiable, Hashable {
    let id: String
    let round: Int
    let status: String
    let result: MWAgentResult?
    let error: String?
    let searchCalls: Int
    let steps: [MWAgentRunStep]

    enum CodingKeys: String, CodingKey {
        case id, round, status, result, error, steps
        case searchCalls = "search_calls"
    }

    var isLive: Bool { status == "queued" || status == "running" }
}

/// A purchase approved in the project chat ("want me to buy it?" → which
/// card). v1 is a handoff: nothing was charged; checkout happens at the link.
struct MWAgentPurchase: Decodable, Identifiable, Hashable {
    let id: String
    let itemName: String
    let retailer: String?
    let checkoutUrl: String
    let amount: Double?
    let currency: String?
    let cardLast4: String
    /// handoff / cancelled, or test_charged / test_failed when a Stripe
    /// TEST-mode charge ran (no real money).
    let status: String
    let chargeError: String?

    enum CodingKeys: String, CodingKey {
        case id, retailer, amount, currency, status
        case itemName = "item_name"
        case checkoutUrl = "checkout_url"
        case cardLast4 = "card_last4"
        case chargeError = "charge_error"
    }
}

struct MWAgentRunsResponse: Decodable {
    let runs: [MWAgentRun]
    /// The caller's own purchase handoffs for this card. Optional so an older
    /// server without purchases still decodes.
    let purchases: [MWAgentPurchase]?
}

/// A saved card for agent purchases. Only brand, last 4, expiry and a label
/// ever come back from the server; the number is never returned.
struct MWPaymentCard: Decodable, Identifiable, Hashable {
    let id: String
    let label: String
    let brand: String
    let last4: String
    let expMonth: Int
    let expYear: Int
    /// nil: bills to the shipping address. Optional so an older server decodes.
    let billingAddress: MWPostalAddress?

    enum CodingKeys: String, CodingKey {
        case id, label, brand, last4
        case expMonth = "exp_month"
        case expYear = "exp_year"
        case billingAddress = "billing_address"
    }

    var brandName: String {
        switch brand {
        case "visa": return "Visa"
        case "mastercard": return "Mastercard"
        case "amex": return "Amex"
        case "discover": return "Discover"
        default: return "Card"
        }
    }
}

struct MWPaymentCardsState: Decodable {
    let enabled: Bool
    let configured: Bool
    let cards: [MWPaymentCard]
}

/// A postal address: shipping, or a card's own billing address (server:
/// services/matcha_work/shipping_addresses.py validates it). Field names
/// match the JSON, so no coding keys.
struct MWPostalAddress: Codable, Hashable {
    var name = ""
    var line1 = ""
    var line2 = ""
    var city = ""
    /// State / province; required for US.
    var region = ""
    var postal_code = ""
    /// Two-letter country code.
    var country = "US"
    var phone = ""

    /// "Haley Smith, 1 Main St, Oakland, CA 94607, US": how the confirmation card shows it.
    var oneLine: String {
        let locality = [region, postal_code].filter { !$0.isEmpty }.joined(separator: " ")
        return [name, line1, line2, city, locality, country].filter { !$0.isEmpty }.joined(separator: ", ")
    }

    var isUS: Bool { country.trimmingCharacters(in: .whitespaces).uppercased() == "US" }
}

/// Where the Espresso assistant ships a purchase. Up to five, one default.
struct MWShippingAddress: Decodable, Identifiable, Hashable {
    let id: String
    let isDefault: Bool
    let address: MWPostalAddress

    enum CodingKeys: String, CodingKey {
        case id
        case isDefault = "is_default"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        isDefault = (try? c.decode(Bool.self, forKey: .isDefault)) ?? false
        address = try MWPostalAddress(from: decoder)
    }
}

struct MWShippingAddressesState: Decodable {
    let enabled: Bool
    let addresses: [MWShippingAddress]
}

struct MWAgentRunQueued: Decodable {
    let runId: String
    let round: Int
    let status: String

    enum CodingKeys: String, CodingKey {
        case round, status
        case runId = "run_id"
    }
}

extension MatchaWorkService {
    /// Every agent pass on the card, newest first, plus your purchase handoffs.
    func agentRuns(projectId: String, taskId: String) async throws -> MWAgentRunsResponse {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/agent-runs"
        )
    }

    // Saved payment cards (server: routes/matcha_work/payment_cards.py). The
    // number is sent once and encrypted server-side; there is no CVV field.

    func paymentCards() async throws -> MWPaymentCardsState {
        try await client.request(method: "GET", path: "\(basePath)/payment-cards")
    }

    /// `billing` nil: the card bills to the shipping address.
    func addPaymentCard(number: String, expMonth: Int, expYear: Int, label: String,
                        billing: MWPostalAddress? = nil) async throws -> MWPaymentCard {
        struct Body: Encodable {
            let number: String
            let exp_month: Int
            let exp_year: Int
            let label: String
            let billing_address: MWPostalAddress?
        }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/payment-cards",
            body: Body(number: number, exp_month: expMonth, exp_year: expYear, label: label,
                       billing_address: billing)
        )
    }

    /// Give a saved card its own billing address, or nil to bill to the shipping address.
    func setCardBillingAddress(id: String, billing: MWPostalAddress?) async throws -> MWPaymentCard {
        struct Body: Encodable {
            let billing: MWPostalAddress?

            func encode(to encoder: Encoder) throws {
                enum Keys: String, CodingKey { case billing_address }
                var c = encoder.container(keyedBy: Keys.self)
                try c.encode(billing, forKey: .billing_address)  // null clears it
            }
        }
        return try await client.request(
            method: "PUT", path: "\(basePath)/payment-cards/\(id)/billing-address", body: Body(billing: billing)
        )
    }

    // Shipping addresses for assistant purchases (server: payment_cards.py).

    func shippingAddresses() async throws -> MWShippingAddressesState {
        try await client.request(method: "GET", path: "\(basePath)/shipping-addresses")
    }

    private struct AddressBody: Encodable {
        let address: MWPostalAddress
        let isDefault: Bool

        func encode(to encoder: Encoder) throws {
            try address.encode(to: encoder)
            enum Keys: String, CodingKey { case is_default }
            var c = encoder.container(keyedBy: Keys.self)
            try c.encode(isDefault, forKey: .is_default)
        }
    }

    func addShippingAddress(_ address: MWPostalAddress, isDefault: Bool = false) async throws -> MWShippingAddress {
        try await client.request(
            method: "POST", path: "\(basePath)/shipping-addresses",
            body: AddressBody(address: address, isDefault: isDefault)
        )
    }

    func updateShippingAddress(id: String, _ address: MWPostalAddress, isDefault: Bool = false) async throws -> MWShippingAddress {
        try await client.request(
            method: "PUT", path: "\(basePath)/shipping-addresses/\(id)",
            body: AddressBody(address: address, isDefault: isDefault)
        )
    }

    func deleteShippingAddress(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/shipping-addresses/\(id)")
    }

    func deletePaymentCard(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/payment-cards/\(id)")
    }

    /// "Run again" after a failed pass (or a manual move back to To do).
    func rerunAgent(projectId: String, taskId: String) async throws -> MWAgentRunQueued {
        struct Empty: Encodable {}
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/agent-runs",
            body: Empty()
        )
    }
}

extension APIError {
    /// The server's `detail` (a string, or an object's `message`) as one line.
    var serverDetail: String? {
        guard case let .httpError(_, message) = self,
              let data = message.data(using: .utf8),
              let response = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if let detail = response["detail"] as? String { return detail }
        return (response["detail"] as? [String: Any])?["message"] as? String
    }

    /// The monthly agent-run cap (429 `agent_run_limit`) as one readable line.
    var agentRunLimitMessage: String? {
        guard case let .httpError(code, message) = self, code == 429,
              let data = message.data(using: .utf8),
              let response = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let detail = response["detail"] as? [String: Any],
              detail["code"] as? String == "agent_run_limit" else {
            return nil
        }
        let limit = detail["limit"] as? Int ?? 0
        return "You've used all \(limit) agent runs this month."
    }
}
