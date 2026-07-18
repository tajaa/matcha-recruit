import SwiftUI

/// The upgrade paywall — Lite vs Pro comparison with Stripe checkout buttons.
/// Raised via `appState.presentPaywall(for:)` from any locked surface;
/// `paywallFeature` selects a contextual headline so the user sees WHY the
/// sheet appeared. Presented by ContentView off `appState.showPaywall`.
struct PaywallSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var isOpeningCheckout = false
    @State private var checkoutError: String?

    /// Contextual headline per locked feature (falls back to the generic one).
    private var headline: String {
        switch appState.paywallFeature {
        case "projects_solo": return "Workspaces need Lite"
        case "projects_collab": return "Collab workspaces need Pro"
        case "journals_full": return "This journal type needs Lite"
        case "email_ai": return "Email AI drafting needs Lite"
        case "go_live": return "Going live needs Pro"
        case "paid_channels": return "Creator monetization needs Pro"
        case "ai_model_pro": return "The Pro AI model needs Pro"
        case "ai_quota": return "You've used your free AI for now"
        default: return "Upgrade Werk"
        }
    }

    private var subheadline: String {
        switch appState.paywallFeature {
        case "ai_quota":
            return "Free includes a taste of the AI. Lite and Pro raise your limit substantially."
        default:
            return "Channels, messaging, and basic journals stay free forever."
        }
    }

    private struct PlanColumn {
        let plan: MWPlan
        let price: String
        let features: [String]
    }

    private let litePlan = PlanColumn(
        plan: .lite,
        price: "$9/mo",
        features: [
            "Solo workspaces — docs, presentations, blogs",
            "All journal types — novel, screenplay, blog",
            "Email AI reply drafting",
            "4× the free AI quota",
        ]
    )

    private let proPlan = PlanColumn(
        plan: .pro,
        price: "$20/mo",
        features: [
            "Everything in Lite",
            "Pro AI model — deeper reasoning",
            "Collab workspaces — kanban, tickets, teams",
            "Go Live video & audio broadcasts",
            "Create paid channels & job postings",
            "20× the free AI quota",
        ]
    )

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            HStack(alignment: .top, spacing: 14) {
                planColumn(litePlan, accented: false)
                planColumn(proPlan, accented: true)
            }
            .padding(18)
            if let err = checkoutError {
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                    .padding(.bottom, 10)
            }
            Text("Subscriptions are billed through Stripe and renew monthly. Cancel anytime.")
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
                .padding(.bottom, 14)
        }
        .frame(width: 560)
        .background(appState.themeBg)
        .onExitCommand { dismiss() }
    }

    private var header: some View {
        VStack(spacing: 6) {
            HStack {
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Close")
            }
            .padding(.horizontal, 14)
            .padding(.top, 12)
            Text(headline)
                .font(.system(size: 19, weight: .bold))
                .foregroundColor(appState.themeText)
            Text(subheadline)
                .font(.system(size: 12))
                .foregroundColor(appState.themeTextSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 30)
                .padding(.bottom, 14)
        }
    }

    @ViewBuilder
    private func planColumn(_ col: PlanColumn, accented: Bool) -> some View {
        let isCurrent = appState.plan == col.plan
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(col.plan.displayName)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(appState.themeText)
                Text(col.price)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(accented ? appState.themeAccent : appState.themeTextSecondary)
                Spacer(minLength: 0)
            }
            VStack(alignment: .leading, spacing: 7) {
                ForEach(col.features, id: \.self) { f in
                    HStack(alignment: .top, spacing: 7) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(accented ? appState.themeAccent : appState.themeTextSecondary)
                            .padding(.top, 2)
                        Text(f)
                            .font(.system(size: 11.5))
                            .foregroundColor(appState.themeText.opacity(0.85))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            Spacer(minLength: 4)
            Button {
                startCheckout(plan: col.plan)
            } label: {
                Text(buttonLabel(for: col.plan, isCurrent: isCurrent))
                    .font(.system(size: 12, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 7)
            }
            .buttonStyle(.borderedProminent)
            .tint(accented ? appState.themeAccent : Color.secondary.opacity(0.6))
            .disabled(isCurrent || isOpeningCheckout || appState.plan == .business
                      || (col.plan == .lite && appState.plan == .pro))
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 280, alignment: .topLeading)
        .background(appState.themeCard)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(accented ? appState.themeAccent.opacity(0.5) : appState.themeBorder, lineWidth: 1)
        )
    }

    private func buttonLabel(for plan: MWPlan, isCurrent: Bool) -> String {
        if isCurrent { return "Current plan" }
        if isOpeningCheckout { return "Opening…" }
        if plan == .lite && appState.plan == .pro { return "Included in Pro" }
        if plan == .pro && appState.plan == .lite { return "Upgrade to Pro" }
        return "Get \(plan.displayName)"
    }

    /// Same flow as ContentView.startUpgrade — Stripe checkout in the browser;
    /// entitlements refresh when the app regains focus (onSceneActive).
    private func startCheckout(plan: MWPlan) {
        guard !isOpeningCheckout else { return }
        isOpeningCheckout = true
        checkoutError = nil
        Task { @MainActor in
            defer { isOpeningCheckout = false }
            do {
                // Derive the web origin from the same base-URL config as every
                // other request (the API base ends in `/api`) instead of pinning
                // prod, so a MATCHA_API_URL override moves the redirect too.
                let webOrigin = APIClient.shared.baseURL.replacingOccurrences(of: "/api", with: "")
                let urlString = try await MatchaWorkService.shared.startPersonalCheckout(
                    successUrl: "\(webOrigin)/work?upgraded=1",
                    cancelUrl: "\(webOrigin)/work?canceled=1",
                    plan: plan.rawValue
                )
                guard let checkoutURL = URL(string: urlString) else {
                    checkoutError = "Invalid checkout URL from server"
                    return
                }
                SafeURL.open(checkoutURL)
                dismiss()
            } catch {
                checkoutError = error.localizedDescription
            }
        }
    }
}
