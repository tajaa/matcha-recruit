import Foundation
import SwiftUI

@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var shopper: Shopper?
    @Published var isWorking = false
    @Published var errorMessage: String?

    private let api: StorefrontAPI

    init(api: StorefrontAPI? = nil) {
        let resolved = api ?? StorefrontAPI.shared
        self.api = resolved
        shopper = resolved.tokens?.shopper
    }

    func requestCode(email: String) async -> Bool {
        isWorking = true
        defer { isWorking = false }
        do {
            let _: Empty = try await api.request(
                api.config.shopperPath + "/auth/start",
                method: "POST",
                body: ["email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()],
                authenticated: false
            )
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func verify(email: String, code: String) async -> Bool {
        isWorking = true
        defer { isWorking = false }
        do {
            let pair: Tokens = try await api.request(
                api.config.shopperPath + "/auth/verify",
                method: "POST",
                body: ["email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), "code": code],
                authenticated: false
            )
            try api.save(pair)
            shopper = pair.shopper
            errorMessage = nil
            NotificationCenter.default.post(name: .storeSessionStarted, object: nil)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func reload() async {
        guard api.tokens != nil else { shopper = nil; return }
        do {
            let value: Shopper = try await api.request(api.config.shopperPath + "/me")
            shopper = value
            if let current = api.tokens {
                try? api.save(Tokens(accessToken: current.accessToken, refreshToken: current.refreshToken, shopper: value))
            }
        } catch let error as APIError where error.status == 401 {
            api.clear()
            shopper = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func update(name: String?, phone: String?, pushOrderUpdates: Bool? = nil) async throws {
        var body: [String: Any] = ["name": name ?? NSNull(), "phone": phone ?? NSNull()]
        if let pushOrderUpdates { body["push_order_updates"] = pushOrderUpdates }
        let value: Shopper = try await api.request(api.config.shopperPath + "/me", method: "PATCH", body: body)
        shopper = value
        if let current = api.tokens {
            try? api.save(Tokens(accessToken: current.accessToken, refreshToken: current.refreshToken, shopper: value))
        }
    }

    func logout() async {
        await NotificationService.shared.unregisterCurrentDevice()
        if api.tokens != nil {
            let _: Empty? = try? await api.request(api.config.shopperPath + "/auth/logout", method: "POST")
        }
        api.clear()
        shopper = nil
    }

    func deleteAccount() async throws {
        let _: Empty = try await api.request(api.config.shopperPath + "/me", method: "DELETE")
        api.clear()
        shopper = nil
    }
}

@MainActor
final class CatalogStore: ObservableObject {
    @Published private(set) var products: [Product] = []
    @Published private(set) var posts: [BlogPost] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            async let fetchedProducts: [Product] = StorefrontAPI.shared.request(
                Config.current.sitePath + "/products", authenticated: false
            )
            async let fetchedPosts: [BlogPost] = StorefrontAPI.shared.request(
                Config.current.sitePath + "/posts", authenticated: false
            )
            products = try await fetchedProducts.sorted { ($0.sortOrder, $0.name) < ($1.sortOrder, $1.name) }
            posts = (try? await fetchedPosts) ?? []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func product(_ id: String) -> Product? { products.first { $0.id == id } }
}

@MainActor
final class CartStore: ObservableObject {
    @Published private(set) var lines: [CartLine] = [] {
        didSet { persist() }
    }

    private let key = "cappe.storefront.cart.v2.\(Config.current.slug)"

    init() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([CartLine].self, from: data)
        else { return }
        lines = decoded.filter { UUID(uuidString: $0.productId) != nil && $0.quantity > 0 }
    }

    var count: Int { lines.reduce(0) { $0 + $1.quantity } }

    func add(product: Product, selectedOptionIds: [String], interval: String?) {
        let candidate = CartLine(
            productId: product.id,
            quantity: 1,
            selectedOptionIds: selectedOptionIds.sorted(),
            interval: interval
        )
        if let index = lines.firstIndex(where: { $0.id == candidate.id }) {
            lines[index].quantity = min(lines[index].quantity + 1, 10_000)
        } else {
            lines.append(candidate)
        }
    }

    func setQuantity(for id: String, quantity: Int) {
        guard let index = lines.firstIndex(where: { $0.id == id }) else { return }
        if quantity <= 0 { lines.remove(at: index) }
        else { lines[index].quantity = min(quantity, 10_000) }
    }

    func remove(_ id: String) { lines.removeAll { $0.id == id } }
    func clear() { lines.removeAll() }

    private func persist() {
        if lines.isEmpty {
            UserDefaults.standard.removeObject(forKey: key)
        } else if let data = try? JSONEncoder().encode(lines) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}

@MainActor
final class FavoritesStore: ObservableObject {
    @Published private(set) var ids: Set<String> = [] {
        didSet { UserDefaults.standard.set(Array(ids), forKey: key) }
    }

    private let key = "cappe.storefront.favorites.v2.\(Config.current.slug)"

    init() {
        ids = Set(UserDefaults.standard.stringArray(forKey: key) ?? [])
    }

    func contains(_ productId: String) -> Bool { ids.contains(productId) }

    func toggle(_ productId: String) async {
        let adding = !ids.contains(productId)
        if adding { ids.insert(productId) } else { ids.remove(productId) }
        guard StorefrontAPI.shared.tokens != nil else { return }
        do {
            let _: Empty = try await StorefrontAPI.shared.request(
                Config.current.shopperPath + "/me/favorites/\(productId)",
                method: adding ? "PUT" : "DELETE"
            )
        } catch {
            if adding { ids.remove(productId) } else { ids.insert(productId) }
        }
    }

    func reconcileAfterSignIn() async {
        guard StorefrontAPI.shared.tokens != nil else { return }
        do {
            let remote: [String] = try await StorefrontAPI.shared.request(Config.current.shopperPath + "/me/favorites")
            let missing = ids.subtracting(remote)
            for id in missing {
                let _: Empty = try await StorefrontAPI.shared.request(
                    Config.current.shopperPath + "/me/favorites/\(id)", method: "PUT"
                )
            }
            ids.formUnion(remote)
        } catch { }
    }
}

@MainActor
final class AppRouter: ObservableObject {
    enum Tab: Hashable { case shop, saved, cart, account }
    @Published var selectedTab: Tab = .shop
    @Published var linkedOrderToken: String?

    func openOrder(_ token: String) {
        linkedOrderToken = token
        selectedTab = .account
    }
}

extension Notification.Name {
    static let storeSessionStarted = Notification.Name("storeSessionStarted")
}
