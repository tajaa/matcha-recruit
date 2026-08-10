import Foundation
import Observation

/// A lightweight operational snapshot assembled from the owner APIs that
/// already exist. This keeps a live site's Home tab focused on work needing
/// attention without waiting for a separate analytics endpoint.
@MainActor
@Observable
final class OwnerDashboardViewModel {
    var orders: [CappeOrder] = []
    var bookings: [CappeBooking] = []
    var products: [CappeProduct] = []
    var threads: [CappeThread] = []
    var reviews: [CappeReview] = []
    var isLoading = false

    var openOrders: [CappeOrder] {
        orders.filter { $0.status == .paid || ($0.requires_approval && $0.status == .pending) }
    }

    var upcomingBookings: [CappeBooking] {
        bookings.filter { $0.status == .pending || $0.status == .confirmed }
    }

    var unreadMessages: Int {
        threads.reduce(0) { $0 + $1.owner_unread }
    }

    var lowStockProducts: [CappeProduct] {
        products.filter { product in
            guard let inventory = product.inventory else { return false }
            return inventory <= (product.low_stock_threshold ?? 0)
        }
    }

    var pendingReviews: Int {
        reviews.filter { $0.status == "pending" }.count
    }

    func load(siteId: String) async {
        isLoading = true
        defer { isLoading = false }

        async let loadedOrders = try? OrdersService.shared.list(siteId: siteId)
        async let loadedBookings = try? BookingsService.shared.list(siteId: siteId)
        async let loadedProducts = try? CatalogService.shared.list(siteId: siteId)
        async let loadedThreads = try? MessagesService.shared.listThreads(siteId: siteId)
        async let loadedReviews = try? ReviewsService.shared.list(siteId: siteId)

        orders = await loadedOrders ?? []
        bookings = await loadedBookings ?? []
        products = await loadedProducts ?? []
        threads = await loadedThreads ?? []
        reviews = await loadedReviews ?? []
    }

    func reset() {
        orders = []
        bookings = []
        products = []
        threads = []
        reviews = []
    }
}
