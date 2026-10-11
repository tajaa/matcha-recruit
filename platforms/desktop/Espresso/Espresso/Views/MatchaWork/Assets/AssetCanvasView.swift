import SwiftUI

/// How a preview body sits on the canvas.
enum AssetSurface {
    /// A document on a centered sheet of paper, scrolled by the canvas.
    case paper
    /// A dashboard-like body (its own header, its own scrolling) in a card.
    case panel
    /// A body that lays itself out on the desk (the presentation stage).
    case stage
    /// A body that fills the canvas edge to edge (the PDF view).
    case fullBleed
}

/// The frame every thread document is shown in: a header naming the asset
/// (kind, version, when it changed, draft or final) with its actions, a live
/// bar while the AI is writing, and a themed "desk" the document sits on.
struct AssetCanvasView<Content: View>: View {
    @Environment(AppState.self) private var appState
    let kind: AssetKind
    let title: String
    var context = AssetCanvasContext()
    var surface: AssetSurface = .paper
    var copyText: String? = nil
    var download: AssetAction? = nil
    var openExternally: AssetAction? = nil
    @ViewBuilder let content: () -> Content

    /// The version the "Updated" pill is announcing, while it shows.
    @State private var announcedVersion: Int?
    @State private var glow = false
    @State private var appeared = false
    @State private var copied = false
    @State private var runningAction: String?
    @State private var actionError: String?
    @State private var showHistory = false

    var body: some View {
        VStack(spacing: 0) {
            header
            AssetProgressBar(tint: kind.tint, active: context.isStreaming)
            if let actionError {
                errorBanner(actionError)
            }
            ZStack(alignment: .top) {
                AssetDesk(tint: kind.tint)
                surfaceBody(surface)
                    .opacity(appeared ? 1 : 0)
                    .offset(y: appeared ? 0 : 18)
                if let version = announcedVersion {
                    updatedPill(version)
                        .padding(.top, 12)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .clipped()
        }
        .background(appState.themeBg)
        .background {
            // Esc leaves focus mode. Mounted only while focused so it never
            // takes Esc from anything else on screen.
            if context.isFocused, let toggle = context.onToggleFocus {
                Button("Exit focus", action: toggle)
                    .keyboardShortcut(.escape, modifiers: [])
                    .opacity(0)
                    .frame(width: 0, height: 0)
                    .accessibilityHidden(true)
            }
        }
        .onAppear {
            withAnimation(.spring(response: 0.5, dampingFraction: 0.82)) { appeared = true }
        }
        .onChange(of: context.version) { old, new in
            guard let old, let new, new > old else { return }
            announce(new)
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center, spacing: 11) {
            AssetIconTile(kind: kind, size: 32)
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.espresso(size: 15, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                    .truncationMode(.tail)
                HStack(spacing: 6) {
                    Text(metaLine)
                        .font(.espresso(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(1)
                    statusChip
                }
            }
            .layoutPriority(1)
            Spacer(minLength: 8)
            actionGroup
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .background(appState.themeBg)
    }

    private var metaLine: String {
        var parts = [kind.name]
        if let version = context.version, version > 0 { parts.append("v\(version)") }
        if let edited = AssetTime.edited(context.updatedAt) { parts.append(edited) }
        return parts.joined(separator: " · ")
    }

    @ViewBuilder
    private var statusChip: some View {
        if let status = context.status {
            let finalized = status == "finalized"
            HStack(spacing: 4) {
                if finalized {
                    Image(systemName: "lock.fill").font(.system(size: 7.5, weight: .bold))
                } else {
                    Circle().frame(width: 5, height: 5)
                }
                Text(finalized ? "Final" : (status == "active" ? "Draft" : status.capitalized))
                    .font(.espresso(size: 10, weight: .medium))
            }
            .foregroundColor(finalized ? kind.tint : appState.themeTextSecondary)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(Capsule().fill((finalized ? kind.tint : appState.themeText).opacity(0.1)))
        }
    }

    private var actionGroup: some View {
        HStack(spacing: 0) {
            if let copyText {
                iconButton(copied ? "checkmark" : "doc.on.doc", help: copied ? "Copied" : "Copy as text") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(copyText, forType: .string)
                    withAnimation(.easeOut(duration: 0.15)) { copied = true }
                    Task {
                        try? await Task.sleep(for: .seconds(1.6))
                        await MainActor.run { withAnimation { copied = false } }
                    }
                }
            }
            if let download { actionButton(download) }
            if let openExternally { actionButton(openExternally) }
            if !context.versions.isEmpty, context.onRevert != nil {
                iconButton("clock.arrow.circlepath", help: "Version history") { showHistory.toggle() }
                    .popover(isPresented: $showHistory, arrowEdge: .bottom) {
                        VersionHistoryView(
                            versions: context.versions,
                            currentVersion: context.version ?? 1,
                            onRevert: { version in
                                showHistory = false
                                context.onRevert?(version)
                            }
                        )
                        .frame(width: 320, height: 380)
                    }
            }
            if let toggle = context.onToggleFocus {
                iconButton(
                    context.isFocused ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right",
                    help: context.isFocused ? "Exit focus (Esc)" : "Focus on the document",
                    action: toggle
                )
            }
        }
        .padding(.horizontal, 3)
        .background(Capsule().fill(appState.themeText.opacity(0.05)))
        .overlay(Capsule().strokeBorder(appState.themeBorder, lineWidth: 0.5))
    }

    private func actionButton(_ action: AssetAction) -> some View {
        let running = runningAction == action.label
        return iconButton(action.icon, help: action.label, busy: running) {
            guard runningAction == nil else { return }
            runningAction = action.label
            actionError = nil
            Task { @MainActor in
                do {
                    try await action.run()
                } catch {
                    if !error.isCancellation {
                        actionError = "\(action.label) failed: \(error.localizedDescription)"
                    }
                }
                runningAction = nil
            }
        }
    }

    private func iconButton(_ icon: String, help: String, busy: Bool = false,
                            action: @escaping () -> Void) -> some View {
        AssetHeaderButton(icon: icon, help: help, busy: busy, action: action)
    }

    private func errorBanner(_ text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 10))
            Text(text).font(.espresso(size: 11)).lineLimit(2)
            Spacer()
            Button { actionError = nil } label: {
                Image(systemName: "xmark").font(.system(size: 9, weight: .bold))
            }
            .buttonStyle(.plain)
        }
        .foregroundColor(.orange)
        .padding(.horizontal, 16).padding(.vertical, 6)
        .background(Color.orange.opacity(0.08))
    }

    // MARK: Body

    @ViewBuilder
    private func surfaceBody(_ surface: AssetSurface) -> some View {
        switch surface {
        case .paper:
            ScrollView {
                AssetPaper(tint: kind.tint, glowing: glow, content: content)
                    .padding(.horizontal, 22)
                    .padding(.top, 22)
                    .padding(.bottom, 36)
                    .frame(maxWidth: .infinity)
            }
        case .panel:
            content()
                .background(RoundedRectangle(cornerRadius: 12).fill(appState.themeCard))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(glow ? kind.tint.opacity(0.7) : appState.themeBorder, lineWidth: glow ? 1.5 : 0.5)
                )
                .shadow(color: .black.opacity(appState.isLightFamily ? 0.07 : 0.3), radius: 14, y: 6)
                .padding(14)
        case .stage, .fullBleed:
            content()
        }
    }

    private func updatedPill(_ version: Int) -> some View {
        HStack(spacing: 5) {
            Image(systemName: "sparkles").font(.system(size: 9, weight: .semibold))
            Text("Updated · v\(version)").font(.espresso(size: 11, weight: .semibold))
        }
        .foregroundColor(.white)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Capsule().fill(kind.tint))
        .shadow(color: kind.tint.opacity(0.45), radius: 10, y: 3)
    }

    private func announce(_ version: Int) {
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            announcedVersion = version
            glow = true
        }
        Task {
            try? await Task.sleep(for: .seconds(1.2))
            await MainActor.run { withAnimation(.easeOut(duration: 0.9)) { glow = false } }
            try? await Task.sleep(for: .seconds(1.3))
            await MainActor.run {
                guard announcedVersion == version else { return }
                withAnimation(.easeIn(duration: 0.25)) { announcedVersion = nil }
            }
        }
    }
}

// MARK: - Pieces

/// The asset's glyph on a rounded tile of its tint.
struct AssetIconTile: View {
    let kind: AssetKind
    var size: CGFloat = 30

    var body: some View {
        RoundedRectangle(cornerRadius: size * 0.27, style: .continuous)
            .fill(
                LinearGradient(colors: [kind.tint.opacity(0.95), kind.tint.opacity(0.72)],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
            )
            .overlay(
                RoundedRectangle(cornerRadius: size * 0.27, style: .continuous)
                    .stroke(Color.white.opacity(0.22), lineWidth: 0.5)
            )
            .overlay(
                Image(systemName: kind.icon)
                    .font(.system(size: size * 0.46, weight: .semibold))
                    .foregroundColor(.white)
            )
            .frame(width: size, height: size)
            .shadow(color: kind.tint.opacity(0.35), radius: 6, y: 2)
    }
}

/// One icon button in the header's capsule group.
private struct AssetHeaderButton: View {
    @Environment(AppState.self) private var appState
    let icon: String
    let help: String
    let busy: Bool
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            ZStack {
                if busy {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: icon)
                        .font(.system(size: 11.5, weight: .medium))
                        .foregroundColor(hovering ? appState.themeText : appState.themeTextSecondary)
                }
            }
            .frame(width: 28, height: 24)
            .background(Circle().fill(appState.themeText.opacity(hovering ? 0.08 : 0)).frame(width: 24, height: 24))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .help(help)
        .onHover { hovering = $0 }
    }
}

/// A sheet of paper on the desk: the document's own surface.
struct AssetPaper<Content: View>: View {
    @Environment(AppState.self) private var appState
    let tint: Color
    var glowing = false
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .padding(.horizontal, 30)
            .padding(.vertical, 28)
            .frame(maxWidth: 780, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(appState.themeCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(glowing ? tint.opacity(0.75) : appState.themeBorder, lineWidth: glowing ? 1.5 : 0.5)
            )
            .shadow(color: glowing ? tint.opacity(0.35) : .black.opacity(appState.isLightFamily ? 0.08 : 0.35),
                    radius: glowing ? 22 : 18, y: 8)
    }
}

/// The surface behind a document: the theme background, a soft glow of the
/// asset's tint from the top, and a faint dot grid.
struct AssetDesk: View {
    @Environment(AppState.self) private var appState
    let tint: Color

    var body: some View {
        ZStack {
            appState.themeBg
            RadialGradient(
                colors: [tint.opacity(appState.isLightFamily ? 0.10 : 0.16), .clear],
                center: .top, startRadius: 0, endRadius: 520
            )
            let ink = appState.themeText
            Canvas { context, size in
                let spacing: CGFloat = 18
                let dot = Path(ellipseIn: CGRect(x: 0, y: 0, width: 1.3, height: 1.3))
                var y: CGFloat = spacing / 2
                while y < size.height {
                    var x: CGFloat = spacing / 2
                    while x < size.width {
                        context.fill(dot.offsetBy(dx: x, dy: y), with: .color(ink))
                        x += spacing
                    }
                    y += spacing
                }
            }
            .opacity(appState.isLightFamily ? 0.07 : 0.05)
        }
        .ignoresSafeArea()
    }
}

/// A 2pt bar under the header that sweeps while the AI is writing.
struct AssetProgressBar: View {
    let tint: Color
    let active: Bool
    @State private var phase: CGFloat = -0.4

    var body: some View {
        GeometryReader { geo in
            if active {
                LinearGradient(colors: [tint.opacity(0), tint, tint.opacity(0)],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(width: geo.size.width * 0.4)
                    .offset(x: phase * geo.size.width)
                    .onAppear {
                        phase = -0.4
                        withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: false)) {
                            phase = 1.0
                        }
                    }
            }
        }
        .frame(height: 2)
        .clipped()
        .background(Rectangle().fill(Color.primary.opacity(active ? 0.04 : 0)))
    }
}
