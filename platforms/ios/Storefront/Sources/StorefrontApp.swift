import SwiftUI

@main
struct AhnimalApp: App {
    @UIApplicationDelegateAdaptor(StorefrontAppDelegate.self) private var appDelegate
    @StateObject private var session = SessionStore()
    @StateObject private var catalog = CatalogStore()
    @StateObject private var cart = CartStore()
    @StateObject private var favorites = FavoritesStore()
    @StateObject private var router = AppRouter()

    var body: some Scene {
        WindowGroup {
            StorefrontRootView()
                .environmentObject(session)
                .environmentObject(catalog)
                .environmentObject(cart)
                .environmentObject(favorites)
                .environmentObject(router)
                .task {
                    await catalog.load()
                    await session.reload()
                    if session.shopper != nil { await favorites.reconcileAfterSignIn() }
                    await NotificationService.shared.requestAuthorization()
                    await NotificationService.shared.registerCurrentDevice()
                }
                .onOpenURL { url in
                    if let token = DeepLinkHandler.token(from: url) { router.openOrder(token) }
                }
                .onReceive(NotificationCenter.default.publisher(for: .storeOrderLink)) { note in
                    if let token = note.object as? String { router.openOrder(token) }
                }
                .onReceive(NotificationCenter.default.publisher(for: .storeSessionStarted)) { _ in
                    Task { await favorites.reconcileAfterSignIn() }
                }
        }
    }
}

struct StorefrontRootView: View {
    @EnvironmentObject private var router: AppRouter
    @EnvironmentObject private var cart: CartStore

    var body: some View {
        TabView(selection: $router.selectedTab) {
            NavigationStack { HomeView() }
                .tabItem { Label("Shop", systemImage: "leaf") }
                .tag(AppRouter.Tab.shop)
            NavigationStack { SavedItemsView() }
                .tabItem { Label("Saved", systemImage: "heart") }
                .tag(AppRouter.Tab.saved)
            NavigationStack { CartView() }
                .tabItem { Label("Cart", systemImage: "bag") }
                .badge(cart.count)
                .tag(AppRouter.Tab.cart)
            NavigationStack { AccountHomeView() }
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
                .tag(AppRouter.Tab.account)
        }
        .tint(.green)
    }
}
