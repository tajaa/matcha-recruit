import SwiftUI

/// The skippable how-it-works wizard every Espresso feature gets: what it is,
/// how to use it, and what to expect. Pages come from `FeatureGuide.catalog`.
/// Shown once per person the first time they open the feature
/// (`.featureGuideOnFirstVisit`), and again from the feature's "?" button
/// (`FeatureGuideButton`), the sidebar row's context menu or Help ▸ Feature
/// Guides (those two set `AppState.featureGuide`; ContentView presents it).
/// Themed (works in light / cappuchin / dark).
struct FeatureGuideSheet: View {
    @Environment(AppState.self) private var appState
    let guide: FeatureGuide
    var onClose: () -> Void

    @State private var step = 0

    private var page: FeatureGuide.Page { guide.pages[step] }
    private var isLast: Bool { step == guide.pages.count - 1 }

    var body: some View {
        VStack(spacing: 0) {
            // Header: which feature, progress dots, skip
            HStack(spacing: 10) {
                Text(guide.name.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .foregroundColor(appState.themeTextSecondary)
                HStack(spacing: 5) {
                    ForEach(0..<guide.pages.count, id: \.self) { i in
                        Circle()
                            .fill(i == step ? appState.themeAccent : appState.themeText.opacity(0.18))
                            .frame(width: 6, height: 6)
                    }
                }
                Spacer()
                Button("Skip") { onClose() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .opacity(isLast ? 0 : 1)
                    .disabled(isLast)
            }
            .padding(.horizontal, 20).padding(.top, 16)

            Spacer(minLength: 12)

            VStack(spacing: 12) {
                Image(systemName: page.icon)
                    .font(.system(size: 32))
                    .foregroundColor(appState.themeAccent)
                    .frame(height: 38)
                Text(page.stage.label)
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.5)
                    .foregroundColor(appState.themeAccent)
                Text(page.title)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .multilineTextAlignment(.center)
                if !page.body.isEmpty {
                    Text(page.body)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText.opacity(0.75))
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: 400)
                }
                if !page.points.isEmpty {
                    VStack(alignment: .leading, spacing: 7) {
                        ForEach(Array(page.points.enumerated()), id: \.offset) { i, point in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                if page.stage == .howTo {
                                    Text("\(i + 1)")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundColor(appState.themeOnAccent)
                                        .frame(width: 16, height: 16)
                                        .background(Circle().fill(appState.themeAccent))
                                } else {
                                    Image(systemName: "checkmark")
                                        .font(.system(size: 9, weight: .bold))
                                        .foregroundColor(appState.themeAccent)
                                        .frame(width: 16)
                                }
                                Text(point)
                                    .font(.system(size: 12))
                                    .foregroundColor(appState.themeText.opacity(0.85))
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .frame(maxWidth: 420, alignment: .leading)
                    .padding(.top, 4)
                }
            }
            .padding(.horizontal, 28)

            Spacer(minLength: 12)

            // Footer: Back / Next or Got it
            HStack {
                Button("Back") { withAnimation { step -= 1 } }
                    .buttonStyle(.plain).font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
                    .opacity(step == 0 ? 0 : 1)
                    .disabled(step == 0)
                Spacer()
                Button {
                    if isLast { onClose() } else { withAnimation { step += 1 } }
                } label: {
                    Text(isLast ? "Got it" : "Next")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(appState.themeOnAccent)
                        .padding(.horizontal, 18).padding(.vertical, 7)
                        .background(appState.themeAccent)
                        .cornerRadius(7)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 20).padding(.bottom, 16)
        }
        .frame(width: 520, height: 440)
        .background(appState.themeBg)
    }
}

extension FeatureGuideSheet {
    /// The guide as a presented sheet: marked seen however it closes (Got it,
    /// Skip, Esc), so it opens on its own only once.
    @MainActor
    static func presented(_ id: FeatureGuideID, appState: AppState,
                          close: @escaping () -> Void) -> some View {
        FeatureGuideSheet(guide: FeatureGuide.guide(for: id), onClose: close)
            .environment(appState)
            .onDisappear { appState.featureGuideClosed(id) }
    }
}

/// The small "?" a feature puts in its header to reopen its guide. It presents
/// the guide itself, so it works inside sheets too (an agent card's viewer).
struct FeatureGuideButton: View {
    @Environment(AppState.self) private var appState
    let id: FeatureGuideID
    var size: CGFloat = 12
    @State private var showing = false

    var body: some View {
        Button { showing = true } label: {
            Image(systemName: "questionmark.circle")
                .font(.system(size: size))
                .foregroundColor(.secondary)
        }
        .buttonStyle(.plain)
        .help("\(FeatureGuide.guide(for: id).name) guide")
        .sheet(isPresented: $showing) {
            FeatureGuideSheet.presented(id, appState: appState) { showing = false }
        }
    }
}

extension View {
    /// Show the feature's guide the first time this person opens it (and
    /// `when` holds). Side panes never raise it (the main pane owns the
    /// window), and a quick pass through the sidebar doesn't either: the view
    /// has to stay up a moment.
    func featureGuideOnFirstVisit(_ id: FeatureGuideID, when enabled: Bool = true) -> some View {
        modifier(FeatureGuideFirstVisit(id: id, enabled: enabled))
    }
}

private struct FeatureGuideFirstVisit: ViewModifier {
    @Environment(AppState.self) private var appState
    @Environment(\.workPane) private var workPane
    let id: FeatureGuideID
    let enabled: Bool
    @State private var showing = false

    private struct Trigger: Equatable {
        let userId: String?
        let enabled: Bool
    }

    func body(content: Content) -> some View {
        content
            .task(id: Trigger(userId: appState.currentUser?.id, enabled: enabled)) {
                guard enabled, !workPane.isSide, let userId = appState.currentUser?.id,
                      !FeatureGuideSeen.isSeen(id, userId: userId) else { return }
                try? await Task.sleep(for: .milliseconds(400))
                guard !Task.isCancelled, appState.featureGuide == nil,
                      appState.autoFeatureGuide == nil, !appState.showPaywall else { return }
                appState.autoFeatureGuide = id
                showing = true
            }
            .sheet(isPresented: $showing) {
                FeatureGuideSheet.presented(id, appState: appState) { showing = false }
            }
    }
}

extension AppState {
    /// Open a feature's guide from the sidebar menu or Help ▸ Feature Guides.
    /// ContentView presents it.
    func showFeatureGuide(_ id: FeatureGuideID) {
        featureGuide = id
    }

    /// The guide closed, however it closed: never open it on its own again.
    func featureGuideClosed(_ id: FeatureGuideID) {
        if let userId = currentUser?.id { FeatureGuideSeen.markSeen(id, userId: userId) }
        if featureGuide == id { featureGuide = nil }
        if autoFeatureGuide == id { autoFeatureGuide = nil }
    }

    /// The guides this person has a way into, for Help ▸ Feature Guides.
    var availableFeatureGuides: [FeatureGuideID] {
        FeatureGuideID.allCases.filter { id in
            switch id {
            case .assistant: return assistantEnabled
            case .jobSearch: return jobSearchEnabled
            default: return true
            }
        }
    }
}
