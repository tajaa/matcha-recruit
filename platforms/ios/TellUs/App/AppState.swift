import Foundation
import Observation
import UIKit
import UserNotifications

@MainActor
@Observable
final class AppState {
    enum Phase: Equatable {
        case restoring
        case loggedOut
        case verifyPending(email: String)
        case consumer
        case brand
        /// Brand account whose plan_status != active — server 402s nearly
        /// everything except GET /brand, /billing/*, and board reads.
        case brandWall
    }

    var phase: Phase = .restoring
    var account: TellusAccount?
    /// Non-empty ⇒ this consumer moderates at least one brand's board
    /// (tellus_brand_members row) — drives the conditional Moderate tab.
    var moderatedBrands: [ModeratedBrand] = []
    /// Brands where this account can answer Comms conversations. Consumers
    /// may have more than one business inbox through team membership.
    var inboxBrands: [InboxBrand] = []
    var unreadCount = 0
    var pendingFriendRequests = 0
    /// Set when the user taps a push; RootView presents the destination as a
    /// full-screen cover and SwiftUI nils it back out on dismissal.
    var pendingDeepLink: DeepLinkRoute?
    /// A push tapped before a usable phase exists (restoring/loggedOut/verifyPending/
    /// brandWall) — replayed into `pendingDeepLink` once `route(_:)` reaches
    /// `.consumer`/`.brand`, instead of presenting over the splash/login screen.
    private var deferredDeepLink: DeepLinkRoute?

    private var pollTask: Task<Void, Never>?
    private var pushObserver: NSObjectProtocol?

    init() {
        // Fired by APIClient only after a DEFINITIVE refresh rejection
        // (401/403), never on network blips or decode errors.
        APIClient.shared.onUnauthorized = { [weak self] in
            Task { @MainActor in self?.didLogout(serverSide: false) }
        }
        APIClient.shared.onPaymentRequired = { [weak self] in
            Task { @MainActor in self?.handle402() }
        }
        pushObserver = NotificationCenter.default.addObserver(
            forName: .tellusPushTapped, object: nil, queue: .main
        ) { [weak self] note in
            guard let route = DeepLinkRoute.parse(userInfo: note.userInfo ?? [:]) else { return }
            Task { @MainActor in
                guard let self else { return }
                switch self.phase {
                case .consumer:
                    self.pendingDeepLink = route
                case .brand:
                    if case .friendRequests = route {} else if case .friendProfile = route {} else if case .friendInvite = route {} else { self.pendingDeepLink = route }
                default:
                    self.deferredDeepLink = route
                }
            }
        }
        Task { await restore() }
    }

    func restore() async {
        if let account = await AuthService.shared.restoreSession() {
            route(account)
        } else {
            phase = .loggedOut
        }
    }

    func route(_ account: TellusAccount) {
        self.account = account
        if account.account_type == .brand {
            phase = account.plan_status == .active ? .brand : .brandWall
            moderatedBrands = []
            inboxBrands = []
        } else {
            phase = .consumer
            Task { [weak self] in
                self?.moderatedBrands = (try? await BoardManageService.shared.moderatedBrands()) ?? []
                self?.inboxBrands = (try? await DmService.shared.inboxBrands()) ?? []
            }
        }
        startPolling()
        requestPushPermission()
        if let deferred = deferredDeepLink {
            deferredDeepLink = nil
            pendingDeepLink = deferred
        }
    }

    func didLogin(_ response: TokenResponse) {
        route(response.account)
    }

    /// Ask for notification permission (once per install) and register this
    /// device for remote notifications. `registerForRemoteNotifications`
    /// hands the token back through AppDelegate → PushService, which upserts it
    /// server-side; a re-login also re-fires `PushService.register()` in case
    /// the token was already cached before a session existed.
    private func requestPushPermission() {
        Task {
            guard (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) == true else { return }
            UIApplication.shared.registerForRemoteNotifications()
        }
        Task { await PushService.shared.register() }
    }

    /// Idempotent — a background 401 firing `onUnauthorized` and a manual
    /// logout tap can both land here without double side effects.
    func didLogout(serverSide: Bool = true) {
        guard phase != .loggedOut else { return }
        pollTask?.cancel()
        pollTask = nil
        // Unregister must go out on the wire before the access token is
        // cleared/invalidated below — otherwise the request 401s and the
        // device-token row survives, leaving a shared device receiving the
        // previous account's pushes.
        Task {
            await PushService.shared.unregister()
            if serverSide {
                await AuthService.shared.logout()
            } else {
                APIClient.shared.accessToken = nil
            }
        }
        account = nil
        moderatedBrands = []
        inboxBrands = []
        unreadCount = 0
        pendingFriendRequests = 0
        pendingDeepLink = nil
        deferredDeepLink = nil
        phase = .loggedOut
        // Cross-account media leak: a shared device relaunching into a
        // different account must not see the previous account's cached
        // report-media bytes or URLCache entries.
        MediaByteLoader.shared.reset()
        URLCache.shared.removeAllCachedResponses()
    }

    /// Runtime 402 on a brand-account call — route to the wall. Consumer
    /// moderators hitting a lapsed brand's /board/manage/* get a local alert
    /// instead (see BoardManageViewModel) since their OWN account is fine.
    func handle402() {
        guard account?.account_type == .brand else { return }
        phase = .brandWall
    }

    /// BillingWallView's Refresh button — re-fetches /auth/me and exits the
    /// wall if the plan is active again.
    func refreshWall() async {
        guard let refreshed = try? await AuthService.shared.fetchMe() else { return }
        route(refreshed)
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                if let items = try? await NotificationsService.shared.list(unreadOnly: true, limit: 100) {
                    self?.unreadCount = items.count
                }
                if let count = try? await FriendsService.shared.requestCount() {
                    self?.pendingFriendRequests = count.incoming
                }
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    func pausePolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func resumePolling() {
        // Consistent with route()'s unconditional startPolling(): a walled
        // brand's own GET /notifications still works (require_tellus_account),
        // so don't stop polling for it on backgrounding just to silently
        // never resume.
        guard phase == .consumer || phase == .brand || phase == .brandWall else { return }
        startPolling()
    }
}
