import SwiftUI

struct ThreadDetailView: View {
    let threadId: String
    /// True in a secondary (aux) window — suppresses shared nav/tab writes.
    var isEmbedded: Bool = false
    @Environment(AppState.self) var appState
    @State var viewModel = ThreadDetailViewModel()
    @State var showVersionHistory = false
    @State var showFinalizeConfirm = false
    @State var showUsageSummary = false
    @State var showAgentPanel = false
    @State var editingTitle = false
    @State var titleDraft = ""
    @FocusState var titleFocused: Bool
    /// The document fills the thread, chat hidden (Esc or the header button exits).
    @State var assetFocused = false
    /// Below `compactWidth` chat and document trade places behind a switch.
    @State var compactTab: CompactTab = .chat
    @State var paneWidth: CGFloat = 1_000
    /// Armed once this thread has loaded, so only a document that appears
    /// during the session reveals itself — not one that was already there.
    @State var revealArmed = false
    /// Compact mode: the document changed while the chat was showing.
    @State var assetUnseen = false

    enum CompactTab { case chat, asset }
    /// Below this the chat (min 280) and the document (min 320) can't sit
    /// side by side with room to read, so they become tabs.
    static let compactWidth: CGFloat = 680

    @MainActor
    init(threadId: String, isEmbedded: Bool = false) {
        self.threadId = threadId
        self.isEmbedded = isEmbedded
        // Main-window tabs share a cached VM so re-opening repaints instantly;
        // embedded panes stay isolated. See ProjectDetailView for rationale.
        _viewModel = State(initialValue: isEmbedded
            ? ThreadDetailViewModel()
            : WorkDetailVMStore.shared.threadVM(threadId))
    }

    func commitTitle() {
        let trimmed = titleDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        editingTitle = false
        guard !trimmed.isEmpty, trimmed != viewModel.thread?.title else { return }
        Task { await viewModel.updateTitle(trimmed) }
    }
    @AppStorage("mw-chat-theme") var lightMode = false
    @AppStorage("mw-model") var selectedModelId = "flash"
    @AppStorage("mw-preview-collapsed") var previewCollapsed = false

    var selectedModelValue: String? {
        appState.modelValue(for: selectedModelId)
    }

    var isBusinessAccount: Bool {
        guard let role = appState.currentUser?.role else { return false }
        return ["client", "admin", "employee"].contains(role)
    }

    var stateInferredType: MWTaskType {
        inferMWTaskType(from: viewModel.currentState)
    }

    // MARK: Layout state

    var showsAsset: Bool { viewModel.hasPreviewContent || viewModel.isLoadingPDF }
    var isCompact: Bool { paneWidth < Self.compactWidth }
    var assetKind: AssetKind { AssetKind(viewModel.currentTaskType) }
    /// Chat and document side by side (the wide layout).
    var showsSideBySide: Bool { showsAsset && !previewCollapsed && !isCompact && !assetFocused }
    /// The document over the chat: focus mode, or the compact switch on it.
    /// The chat stays mounted underneath so its draft and scroll survive.
    var showsAssetOverlay: Bool {
        showsAsset && (assetFocused || (isCompact && !previewCollapsed && compactTab == .asset))
    }
    var showsCompactSwitch: Bool { showsAsset && isCompact && !previewCollapsed && !assetFocused }

    var body: some View {
        withWindowToolbar(threadBody)
            .task(id: threadId) {
                revealArmed = false
                // Re-point at this thread's cached VM (the view is reused across
                // thread→thread switches, so @State still holds the prior thread's).
                if !isEmbedded {
                    let cached = WorkDetailVMStore.shared.threadVM(threadId)
                    if cached !== viewModel { viewModel = cached }
                }
                await viewModel.loadThread(id: threadId)
                revealArmed = true
                if !isEmbedded {
                    appState.setActiveContext(WorkTab(kind: .thread, entityId: threadId,
                                                      title: viewModel.thread?.displayName ?? "Chat"))
                }
            }
            .onChange(of: showsAsset) { had, has in
                // A document was just created: bring it into view.
                guard revealArmed, !had, has else { return }
                withAnimation(.spring(response: 0.45, dampingFraction: 0.85)) {
                    previewCollapsed = false
                    compactTab = .asset
                }
            }
            .onChange(of: viewModel.thread?.version) { old, new in
                guard let old, let new, new > old, isCompact, compactTab == .chat else { return }
                assetUnseen = true
            }
            .onChange(of: compactTab) { _, tab in if tab == .asset { assetUnseen = false } }
            .onChange(of: threadId) { _, _ in
                assetFocused = false
                compactTab = .chat
                assetUnseen = false
            }
            .alert("Finalize Thread?", isPresented: $showFinalizeConfirm) {
                Button("Finalize", role: .destructive) {
                    Task { await viewModel.finalize() }
                }
                Button("Cancel", role: .cancel) { }
            } message: {
                Text("This will lock the thread and remove any watermarks from documents.")
            }
    }

    private var threadBody: some View {
        VStack(spacing: 0) {
            LinearGradient(
                colors: [Color.black.opacity(0.35), Color.clear],
                startPoint: .top,
                endPoint: .bottom
            )
            .frame(height: 6)
            .overlay(
                Rectangle().fill(Color.white.opacity(0.08)).frame(height: 1),
                alignment: .top
            )

            // A pane beside the main one gets its own header: its toolbar
            // items would otherwise merge into the window's, next to the main
            // pane's own title and pickers.
            if isEmbedded, let thread = viewModel.thread {
                paneHeader(thread)
            }

            if viewModel.thread == nil && viewModel.isLoadingThread {
                // Cold load only — warm re-entry keeps prior content (the VM is
                // retained by WorkDetailVMStore) and revalidates silently.
                ChatSkeleton()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                if showsCompactSwitch {
                    compactSwitch
                }
                ZStack {
                    HSplitView {
                        ChatPanelView(viewModel: viewModel, lightMode: lightMode, selectedModel: selectedModelValue)
                            .environment(\.threadAsset, threadAssetContext)
                            .frame(minWidth: 280, idealWidth: 520)

                        if showsSideBySide {
                            assetCanvas
                                .frame(minWidth: 320, idealWidth: 420, maxWidth: .infinity)
                        }
                    }
                    if showsAssetOverlay {
                        assetCanvas
                            .transition(.opacity.combined(with: .scale(scale: 0.985)))
                    }
                }
                // Keep this low: in a bottom split pane the whole view gets as
                // little as ~240pt — a large min here overflows the pane and
                // clips the composer off-screen (the "can't type in the bottom
                // pane" bug). 220 still guarantees the input bar fits.
                .frame(minHeight: 220)
            }
        }
        .background(Color.appBackground)
        .background(
            GeometryReader { geo in
                Color.clear.preference(key: ThreadPaneWidthKey.self, value: geo.size.width)
            }
        )
        .onPreferenceChange(ThreadPaneWidthKey.self) { paneWidth = $0 }
        .preferredColorScheme(lightMode ? .light : .dark)
    }

    // MARK: Asset

    private var assetCanvas: some View {
        PreviewPanelView(
            currentState: viewModel.currentState,
            pdfData: viewModel.pdfData,
            pdfIsCurrent: viewModel.pdfIsCurrent,
            isLoading: viewModel.isLoadingPDF,
            taskType: viewModel.thread?.taskType,
            threadId: viewModel.thread?.id,
            selectedSlideIndex: Bindable(viewModel).selectedSlideIndex,
            context: canvasContext
        )
    }

    private var canvasContext: AssetCanvasContext {
        let thread = viewModel.thread
        let name = thread?.displayName
        return AssetCanvasContext(
            threadId: thread?.id,
            threadTitle: name == "(UNNAMED)" ? nil : name,
            version: thread?.version,
            updatedAt: thread?.updatedAt,
            status: thread?.status,
            versions: viewModel.versions,
            isStreaming: viewModel.isStreaming,
            isFocused: assetFocused,
            onToggleFocus: {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.86)) { assetFocused.toggle() }
            },
            onRevert: { version in Task { await viewModel.revert(to: version) } }
        )
    }

    /// What the chat's asset cards show and open; nil while the thread has no
    /// document, so replies keep the plain "Document updated" line.
    private var threadAssetContext: ThreadAssetContext? {
        guard showsAsset else { return nil }
        return ThreadAssetContext(
            kind: assetKind,
            title: assetKind.title(from: viewModel.currentState),
            versions: viewModel.versions,
            currentVersion: viewModel.thread?.version ?? 0,
            open: { revealAsset() }
        )
    }

    func revealAsset() {
        withAnimation(.spring(response: 0.45, dampingFraction: 0.85)) {
            previewCollapsed = false
            compactTab = .asset
        }
    }

    /// Chat | <document> — the compact layout's switch.
    private var compactSwitch: some View {
        AssetTabSwitch(
            showingAsset: Binding(
                get: { compactTab == .asset },
                set: { compactTab = $0 ? .asset : .chat }
            ),
            kind: assetKind,
            unseen: assetUnseen
        )
    }

    // MARK: Window toolbar (main pane only)

    @ViewBuilder
    private func withWindowToolbar<Content: View>(_ content: Content) -> some View {
        // `isEmbedded` is fixed for a view's lifetime, so the branch never
        // flips under a live view.
        if isEmbedded {
            content
        } else {
            content.toolbar { windowToolbar }
        }
    }

    @ToolbarContentBuilder
    private var windowToolbar: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            if let thread = viewModel.thread {
                HStack(spacing: 8) {
                    titleEditor(thread, color: .white)
                    threadChips(thread)
                }
            }
        }

        ToolbarItemGroup(placement: .primaryAction) {
            modeToggles

            Divider()

            modelPicker

            // Email agent
            Button {
                showAgentPanel.toggle()
            } label: {
                Image(systemName: "envelope")
                    .font(.system(size: 13))
                    .foregroundColor(showAgentPanel ? .matcha500 : nil)
            }
            .help("Email agent")
            .popover(isPresented: $showAgentPanel) {
                AgentPanelView()
                    .frame(width: 560, height: 440)
            }

            // Usage summary
            Button {
                showUsageSummary = true
            } label: {
                Image(systemName: "chart.bar")
                    .font(.system(size: 13))
            }
            .help("Token usage summary")
            .popover(isPresented: $showUsageSummary) {
                UsageSummaryView()
                    .frame(width: 340, height: 360)
            }

            // Light/dark toggle
            Button {
                lightMode.toggle()
            } label: {
                Image(systemName: lightMode ? "moon" : "sun.max")
                    .font(.system(size: 13))
            }
            .help(lightMode ? "Switch to dark mode" : "Switch to light mode")

            previewToggle

            if !viewModel.versions.isEmpty {
                Button {
                    showVersionHistory = true
                } label: {
                    Label("History", systemImage: "clock")
                }
                .popover(isPresented: $showVersionHistory) {
                    VersionHistoryView(
                        versions: viewModel.versions,
                        currentVersion: viewModel.thread?.version ?? 1,
                        onRevert: { version in
                            Task { await viewModel.revert(to: version) }
                            showVersionHistory = false
                        }
                    )
                    .frame(width: 320, height: 400)
                }
            }

            finalizeButton
        }
    }
}

private struct ThreadPaneWidthKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

// MARK: - Mode Toggle Button

struct ModeToggleButton: View {
    @Environment(AppState.self) private var appState

    let label: String
    let icon: String
    let isOn: Bool
    let onColor: Color
    let isLoading: Bool
    let tooltip: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                Text(label)
                    .font(.system(size: 11, weight: .medium))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            // Soft tinted pill matching the current werk design: per-mode hue
            // when on (purple/cyan/green identity), themed-neutral when off.
            .background(
                Capsule().fill(isOn ? onColor.opacity(0.15) : Color.clear)
            )
            .overlay(
                Capsule().stroke(isOn ? onColor.opacity(0.45) : appState.themeBorder, lineWidth: 1)
            )
            .foregroundColor(isOn ? onColor : appState.themeTextSecondary)
            .opacity(isLoading ? 0.5 : 1.0)
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
        .help(tooltip)
    }
}
