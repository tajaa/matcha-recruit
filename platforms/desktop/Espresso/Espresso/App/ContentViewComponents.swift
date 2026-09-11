import SwiftUI
import AppKit

// MARK: - Mac Native Visual Effect View

struct VisualEffectView: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    var blendingMode: NSVisualEffectView.BlendingMode = .behindWindow

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}

// MARK: - Glass panels (Liquid Glass on macOS 26, vibrancy material on 14/15)

/// A premium translucent floating surface. On macOS 26+ it renders true
/// Liquid Glass via `glassEffect`; on macOS 14/15 it falls back to a tinted
/// `NSVisualEffectView` material so it still looks frosted today. The theme
/// `tint` (layered over the frost) keeps each theme's identity and preserves
/// text contrast — the old full-window `.ultraThinMaterial` washout is avoided
/// by scoping this to discrete chrome / floating surfaces only.
struct GlassPanelModifier: ViewModifier {
    var cornerRadius: CGFloat = 12
    var material: NSVisualEffectView.Material = .menu
    var blending: NSVisualEffectView.BlendingMode = .withinWindow
    var tint: Color
    var tintOpacity: Double = 0.5
    var stroke: Color = .white.opacity(0.10)
    var shadow: Bool = true

    @ViewBuilder
    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
#if compiler(>=6.2)
        if #available(macOS 26.0, *) {
            content
                .glassEffect(.regular.tint(tint.opacity(min(tintOpacity, 0.35))), in: shape)
        } else {
            fallback(content: content, shape: shape)
        }
#else
        fallback(content: content, shape: shape)
#endif
    }

    private func fallback(content: Content, shape: RoundedRectangle) -> some View {
        content
            .background {
                ZStack {
                    VisualEffectView(material: material, blendingMode: blending)
                    tint.opacity(tintOpacity)
                }
                .clipShape(shape)
            }
            .overlay(shape.stroke(stroke, lineWidth: 1))
            .shadow(color: shadow ? .black.opacity(0.20) : .clear,
                    radius: shadow ? 14 : 0, y: shadow ? 6 : 0)
    }
}

extension View {
    /// Frosted floating panel — see `GlassPanelModifier`.
    func glassPanel(
        cornerRadius: CGFloat = 12,
        material: NSVisualEffectView.Material = .menu,
        blending: NSVisualEffectView.BlendingMode = .withinWindow,
        tint: Color,
        tintOpacity: Double = 0.5,
        stroke: Color = .white.opacity(0.10),
        shadow: Bool = true
    ) -> some View {
        modifier(GlassPanelModifier(
            cornerRadius: cornerRadius, material: material, blending: blending,
            tint: tint, tintOpacity: tintOpacity, stroke: stroke, shadow: shadow))
    }
}

// MARK: - Muted radial background

/// A soft, top-anchored radial grayscale gradient used behind content panes
/// (Home, collab). Center is a hair lighter than the flat theme bg, edges a
/// hair darker — quiet depth, no color. This is the "muted elegance" base the
/// elevated cards float on.
struct ThemeRadialBackground: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        let pair: (Color, Color)
        switch appState.appTheme {
        case "light":     pair = (.grayRadialCenter, .grayRadialEdge)
        case "platinum":  pair = (.platinumRadialCenter, .platinumRadialEdge)
        case "cappuchin": pair = (.cappuchinRadialCenter, .cappuchinRadialEdge)
        case "graphite":  pair = (.graphiteRadialCenter, .graphiteRadialEdge)
        default:          pair = (.darkRadialCenter, .darkRadialEdge)
        }
        return RadialGradient(
            gradient: Gradient(colors: [pair.0, pair.1]),
            center: .top,
            startRadius: 0,
            endRadius: 1100
        )
        .ignoresSafeArea()
    }
}

// MARK: - Espresso brand mark

/// The same generated Espresso mark used by the application bundle, kept
/// consistent across the login screen and navigation instead of substituting
/// the old SF Symbols coffee cup inside the app.
struct EspressoMark: View {
    var size: CGFloat = 64
    var showTile: Bool = true

    var body: some View {
        Image(nsImage: NSApplication.shared.applicationIconImage)
            .resizable()
            .interpolation(.high)
            .scaledToFit()
            .frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: size * 0.22, style: .continuous))
            .shadow(color: .black.opacity(showTile ? 0.12 : 0), radius: size * 0.10, y: 1)
    }
}

// MARK: - Elevated card (depth for light mode; border for dark)

/// Premium card surface. In light mode it floats on soft layered shadows with
/// no harsh border (Linear/Things aesthetic); in dark/cappuchin, where black
/// shadows don't read, it uses a crisp hairline border plus a faint shadow.
/// This is what carries "premium" on macOS 15, where glass can't blur an
/// opaque content pane.
struct ElevatedCardModifier: ViewModifier {
    var cornerRadius: CGFloat = 12
    @Environment(AppState.self) private var appState

    func body(content: Content) -> some View {
        let isLight = appState.isLightFamily
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return content
            .background(shape.fill(Color.cardBackground))
            .overlay(shape.strokeBorder(appState.themeBorder.opacity(isLight ? 0.35 : 0.52), lineWidth: 0.7))
            // Two-layer shadow: a soft ambient spread + a tight contact shadow.
            .shadow(color: .black.opacity(isLight ? 0.07 : 0.0), radius: 8, y: 3)
            .shadow(color: .black.opacity(isLight ? 0.04 : 0.12), radius: 1, y: 1)
    }
}

extension View {
    func elevatedCard(cornerRadius: CGFloat = 12) -> some View {
        modifier(ElevatedCardModifier(cornerRadius: cornerRadius))
    }
}

/// Pinned work tabs, rendered as a sidebar section (moved from the old
/// horizontal strip above the detail pane). Home is permanent in `openTabs`
/// but the sidebar already has a Home row, so it's filtered here. Click a row
/// to switch, "×" to close, header "+" to pin the currently-open item.
struct WorkTabsSidebarSection: View {
    @Environment(AppState.self) private var appState
    @State private var hoveredTabId: String?

    private var pinnedTabs: [WorkTab] {
        appState.openTabs.filter { $0.kind != .home }
    }

    var body: some View {
        // Hidden entirely until there's something to show or pin — keeps the
        // sidebar quiet for users who never touch tabs.
        if !pinnedTabs.isEmpty || appState.canPinActiveTab {
            VStack(spacing: 2) {
                HStack(spacing: 6) {
                    Text("Tabs")
                        .font(.espresso(size: 11))
                        .foregroundColor(appState.themeSidebarTextSecondary)
                    Spacer(minLength: 0)
                    Button { appState.pinActiveTab() } label: {
                        Image(systemName: "plus")
                            .font(.espresso(size: 10))
                            .foregroundColor(appState.themeSidebarTextSecondary)
                            .frame(width: 18, height: 18)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(!appState.canPinActiveTab)
                    .opacity(appState.canPinActiveTab ? 1 : 0.3)
                    .help(pinHelp)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)

                ForEach(pinnedTabs) { tab in
                    tabRow(tab)
                }
            }
            .padding(.bottom, 6)
        }
    }

    private var pinHelp: String {
        if appState.activeTab.kind == .home { return "Home is always open" }
        if appState.openTabs.contains(where: { $0.id == appState.activeTab.id }) { return "Already pinned" }
        if appState.pinnedTabCount >= AppState.maxPinnedTabs { return "Tab limit reached" }
        return "Pin \u{201C}\(appState.activeTab.title)\u{201D} as a tab"
    }

    private func tabRow(_ tab: WorkTab) -> some View {
        let active = appState.activeTab.id == tab.id
        let unseen = appState.tabUnread(tab)
        let hovered = hoveredTabId == tab.id
        return Button { appState.selectTab(tab) } label: {
            HStack(spacing: 8) {
                Image(systemName: tab.icon)
                    .font(.espresso(size: 11))
                    .foregroundColor(active ? appState.themeSidebarAccent : appState.themeSidebarTextSecondary)
                    .frame(width: 16)
                Text(tab.title)
                    .font(.espresso(size: 12, weight: active ? .medium : .regular))
                    .foregroundColor(active ? appState.themeSidebarText : appState.themeSidebarText.opacity(0.7))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
                if unseen > 0 && !hovered {
                    Text(unseen > 10 ? "10+" : "\(unseen)")
                        .font(.espresso(size: 9, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(appState.themeSidebarAccent))
                }
                if hovered {
                    Button { appState.closeTab(tab) } label: {
                        Image(systemName: "xmark")
                            .font(.espresso(size: 9))
                            .foregroundColor(appState.themeSidebarText.opacity(0.5))
                            .frame(width: 16, height: 16)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help("Close tab")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.clear)
            )
            .overlay(alignment: .leading) {
                if active {
                    Capsule().fill(appState.themeSidebarAccent).frame(width: 2, height: 16)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 6)
        .onHover { hoveredTabId = $0 ? tab.id : (hoveredTabId == tab.id ? nil : hoveredTabId) }
        .contextMenu {
            Button("Close tab") { appState.closeTab(tab) }
        }
    }
}

/// "Show N more" row used by sidebar lists that paginate (projects, channels,
/// journals, threads) so the sidebar stays short. Reveals the next batch.
struct SidebarShowMoreButton: View {
    @Environment(AppState.self) private var appState
    let remaining: Int
    let pageSize: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: "chevron.down").font(.espresso(size: 9))
                Text("Show \(min(pageSize, remaining)) more").font(.espresso(size: 10))
                Spacer()
            }
            .foregroundColor(appState.themeSidebarTextSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("\(remaining) more")
    }
}

struct SidebarRowModifier: ViewModifier {
    let isSelected: Bool
    @Environment(AppState.self) private var appState
    @State private var isHovered = false

    func body(content: Content) -> some View {
        let isSidebarDark = appState.isSidebarDark
        content
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isSelected
                          ? appState.themeSidebarAccent.opacity(0.075)
                          : (isHovered ? (isSidebarDark ? Color.white.opacity(0.08) : Color.black.opacity(0.05)) : Color.clear))
                    .padding(.horizontal, 6)
            )
            .onHover { hovering in
                withAnimation(.easeOut(duration: 0.1)) {
                    isHovered = hovering
                }
            }
    }
}

extension View {
    func sidebarRowStyle(isSelected: Bool) -> some View {
        self.modifier(SidebarRowModifier(isSelected: isSelected))
    }
}

private let threadListOutputFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    return formatter
}()

private func formatThreadDate(_ iso: String) -> String {
    guard let date = parseMWDate(iso) else { return iso }
    return threadListOutputFormatter.string(from: date)
}
