import Foundation

/// Orders (server/app/cappe/routes/shop.py — Orders section).
final class OrdersService {
    static let shared = OrdersService()
    private init() {}

    func list(siteId: String) async throws -> [CappeOrder] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/orders")
    }

    func get(siteId: String, orderId: String) async throws -> CappeOrder {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/orders/\(orderId)")
    }

    func updateStatus(siteId: String, orderId: String, _ body: CappeOrderStatusUpdate) async throws -> CappeOrder {
        try await APIClient.shared.request(method: "PATCH", path: "/sites/\(siteId)/orders/\(orderId)", body: body)
    }

    func accept(siteId: String, orderId: String) async throws -> CappeOrder {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/orders/\(orderId)/accept")
    }

    func decline(siteId: String, orderId: String, reason: String? = nil) async throws -> CappeOrder {
        try await APIClient.shared.request(
            method: "POST", path: "/sites/\(siteId)/orders/\(orderId)/decline",
            body: CappeApprovalDecline(reason: reason)
        )
    }

    func attachDeliverable(siteId: String, orderId: String, itemId: String, url: String) async throws -> CappeOrderItem {
        try await APIClient.shared.request(
            method: "PATCH", path: "/sites/\(siteId)/orders/\(orderId)/items/\(itemId)",
            body: CappeDeliverableUpdate(deliverable_url: url)
        )
    }

    /// Raw PDF bytes, not JSON — goes through `requestData`, not `request<T>`.
    func receiptPDF(siteId: String, orderId: String) async throws -> Data {
        try await APIClient.shared.requestData(method: "GET", path: "/sites/\(siteId)/orders/\(orderId)/receipt.pdf")
    }
}
