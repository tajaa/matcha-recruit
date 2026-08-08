import Foundation
import Observation

@MainActor
@Observable
final class OrderDetailViewModel: LoadableVM {
    var order: CappeOrder?
    var isLoading = false
    var isActing = false
    var error: String?

    func load(siteId: String, orderId: String) async {
        await withLoad {
            self.order = try await OrdersService.shared.get(siteId: siteId, orderId: orderId)
        }
    }

    /// Mirrors the server's `CappeOrderStatusUpdate.model_validator`
    /// (server/app/cappe/models/shop.py:216-223) — at least one of the three
    /// fields must be present, so a bad request never leaves the device.
    /// `carrier`/`trackingNumber` are `Clearable` (see that type's doc
    /// comment): `.unset` means the field is genuinely absent from the PATCH.
    nonisolated static func isValidStatusUpdate(status: String?, carrier: Clearable<String>, trackingNumber: Clearable<String>) -> Bool {
        status != nil || carrier.isPresent || trackingNumber.isPresent
    }

    @discardableResult
    func updateStatus(siteId: String, status: String? = nil, carrier: Clearable<String> = .unset, trackingNumber: Clearable<String> = .unset) async -> Bool {
        guard let orderId = order?.id else { return false }
        guard Self.isValidStatusUpdate(status: status, carrier: carrier, trackingNumber: trackingNumber) else { return false }
        isActing = true
        error = nil
        defer { isActing = false }
        do {
            order = try await OrdersService.shared.updateStatus(
                siteId: siteId, orderId: orderId,
                CappeOrderStatusUpdate(status: status, carrier: carrier, tracking_number: trackingNumber)
            )
            return true
        } catch {
            if error.isCancellation { return false }
            self.error = error.localizedDescription
            return false
        }
    }

    func accept(siteId: String) async {
        guard let orderId = order?.id else { return }
        isActing = true
        error = nil
        defer { isActing = false }
        do {
            order = try await OrdersService.shared.accept(siteId: siteId, orderId: orderId)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func decline(siteId: String, reason: String?) async {
        guard let orderId = order?.id else { return }
        isActing = true
        error = nil
        defer { isActing = false }
        do {
            order = try await OrdersService.shared.decline(siteId: siteId, orderId: orderId, reason: reason)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func attachDeliverable(siteId: String, itemId: String, url: String) async {
        guard let orderId = order?.id else { return }
        isActing = true
        error = nil
        defer { isActing = false }
        do {
            let item = try await OrdersService.shared.attachDeliverable(siteId: siteId, orderId: orderId, itemId: itemId, url: url)
            if let idx = order?.items.firstIndex(where: { $0.id == itemId }) {
                order?.items[idx] = item
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    /// Downloads the receipt PDF and writes it to a temp file for QuickLook —
    /// `QLPreviewController` needs a file URL, not raw `Data`.
    func downloadReceiptFileURL(siteId: String) async -> URL? {
        guard let orderId = order?.id else { return nil }
        do {
            let data = try await OrdersService.shared.receiptPDF(siteId: siteId, orderId: orderId)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(orderId)-receipt.pdf")
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
            return nil
        }
    }
}
