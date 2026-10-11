import SwiftUI

/// The thread's controls — title, chips, modes, model, document toggle,
/// Finalize — shared by the window toolbar (main pane) and the in-pane header
/// (a thread beside the main pane or in its own window).
extension ThreadDetailView {

    // MARK: Pieces

    @ViewBuilder
    func titleEditor(_ thread: MWThread, color: Color) -> some View {
        if editingTitle {
            TextField("Thread title", text: $titleDraft)
                .textFieldStyle(.plain)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(color)
                .frame(width: 200)
                .focused($titleFocused)
                .onSubmit { commitTitle() }
                // TextField onCommit only fires on Enter, so a
                // click-out used to discard the draft. Commit
                // on blur so clicking elsewhere saves the edit.
                .onChange(of: titleFocused) { _, focused in
                    if !focused && editingTitle { commitTitle() }
                }
                .onExitCommand {
                    // Escape discards the edit.
                    editingTitle = false
                }

            Button {
                // Explicit cancel — discard draft.
                editingTitle = false
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        } else {
            Text(thread.displayName)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(color)
                .lineLimit(1)
                .onTapGesture { beginRename(thread) }

            Button {
                beginRename(thread)
            } label: {
                Image(systemName: "pencil")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
    }

    func beginRename(_ thread: MWThread) {
        titleDraft = thread.title
        editingTitle = true
        titleFocused = true
    }

    @ViewBuilder
    func threadChips(_ thread: MWThread) -> some View {
        VersionBadge(version: thread.version)
        StatusBadge(status: thread.status)

        if stateInferredType != .chat {
            HStack(spacing: 3) {
                Image(systemName: stateInferredType.icon)
                    .font(.system(size: 9))
                Text(stateInferredType.label.capitalized)
                    .font(.system(size: 10, weight: .medium))
            }
            .foregroundColor(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.white.opacity(0.06))
            .cornerRadius(4)
        }

        if let usageText = viewModel.tokenUsage?.displayText {
            Text(usageText)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.white.opacity(0.06))
                .cornerRadius(4)
        }
    }

    @ViewBuilder
    var modeToggles: some View {
        if isBusinessAccount {
            ModeToggleButton(
                label: "Node",
                icon: "cylinder",
                isOn: viewModel.thread?.nodeMode ?? false,
                onColor: .purple,
                isLoading: viewModel.togglingMode == "node",
                tooltip: "Query employees, policies, handbooks"
            ) {
                Task { await viewModel.toggleMode("node") }
            }

            ModeToggleButton(
                label: "Compliance",
                icon: "shield",
                isOn: viewModel.thread?.complianceMode ?? false,
                onColor: .cyan,
                isLoading: viewModel.togglingMode == "compliance",
                tooltip: "Jurisdiction requirements context"
            ) {
                Task { await viewModel.toggleMode("compliance") }
            }

            ModeToggleButton(
                label: "Payer",
                icon: "stethoscope",
                isOn: viewModel.thread?.payerMode ?? false,
                onColor: Color.matcha500,
                isLoading: viewModel.togglingMode == "payer",
                tooltip: "Medicare NCD/LCD lookups"
            ) {
                Task { await viewModel.toggleMode("payer") }
            }
        }
    }

    /// Model picker. The pro model is a Pro/Business entitlement — locked rows
    /// open the paywall (server clamps the override regardless, so this is
    /// purely honest UI).
    var modelPicker: some View {
        Menu {
            modelMenuItems
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "cpu")
                    .font(.system(size: 10))
                Text(appState.modelOption(for: selectedModelId)?.label ?? "Flash")
                    .font(.system(size: 10, weight: .medium))
            }
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(Capsule().fill(appState.themeText.opacity(0.08)))
            .overlay(Capsule().stroke(appState.themeBorder, lineWidth: 1))
            .foregroundColor(appState.themeTextSecondary)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help("Select AI model")
    }

    var modelMenuItems: some View {
        ForEach(appState.modelOptions) { option in
            let locked = appState.isModelLocked(option)
            Button {
                if locked {
                    appState.presentPaywall(for: "ai_model_pro")
                } else {
                    selectedModelId = option.id
                }
            } label: {
                HStack {
                    Text(locked ? "\(option.label) 🔒" : option.label)
                    if appState.modelOption(for: selectedModelId)?.id == option.id {
                        Image(systemName: "checkmark")
                    }
                }
            }
        }
    }

    /// Preview collapse toggle.
    @ViewBuilder
    var previewToggle: some View {
        if showsAsset {
            Button {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.86)) { previewCollapsed.toggle() }
            } label: {
                Image(systemName: previewCollapsed
                      ? "rectangle.righthalf.inset.filled"
                      : "rectangle.righthalf.inset.filled.arrow.right")
                    .font(.system(size: 13))
                    .foregroundColor(previewCollapsed ? .secondary : .matcha500)
            }
            .help(previewCollapsed ? "Show preview panel" : "Hide preview panel")
        }
    }

    @ViewBuilder
    var finalizeButton: some View {
        if viewModel.thread?.status == "active" {
            Button {
                showFinalizeConfirm = true
            } label: {
                Text("Finalize")
                    .font(.system(size: 13, weight: .medium))
            }
            .buttonStyle(.borderedProminent)
            .tint(Color.matcha600)
        }
    }

    // MARK: In-pane header

    /// The thread's own header when it is not the window's main pane. Wide
    /// panes get every control; narrower ones fold modes, then everything
    /// but the title, into a "…" menu.
    func paneHeader(_ thread: MWThread) -> some View {
        Group {
            if editingTitle {
                // One row while renaming: ViewThatFits measures each candidate,
                // and the title field must exist exactly once.
                HStack(spacing: 8) {
                    titleEditor(thread, color: appState.themeText)
                    Spacer(minLength: 0)
                }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        titleEditor(thread, color: appState.themeText)
                        threadChips(thread)
                        Spacer(minLength: 12)
                        modeToggles
                        modelPicker
                        previewToggle.buttonStyle(.plain)
                        finalizeButton.controlSize(.small)
                    }
                    HStack(spacing: 8) {
                        titleEditor(thread, color: appState.themeText)
                        VersionBadge(version: thread.version)
                        Spacer(minLength: 12)
                        modelPicker
                        previewToggle.buttonStyle(.plain)
                        finalizeButton.controlSize(.small)
                        overflowMenu(thread, modes: true, model: false, document: false, finalize: false)
                    }
                    HStack(spacing: 8) {
                        titleEditor(thread, color: appState.themeText)
                        Spacer(minLength: 8)
                        overflowMenu(thread, modes: true, model: true, document: true, finalize: true)
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity)
        .background(appState.themeBg)
        .overlay(Rectangle().fill(appState.themeBorder).frame(height: 0.5), alignment: .bottom)
    }

    @ViewBuilder
    private func overflowMenu(_ thread: MWThread, modes: Bool, model: Bool,
                              document: Bool, finalize: Bool) -> some View {
        let hasModes = modes && isBusinessAccount
        let hasDocument = document && showsAsset
        let hasFinalize = finalize && thread.status == "active"
        if hasModes || model || hasDocument || hasFinalize {
            Menu {
                if hasModes {
                    Section("Modes") {
                        modeMenuToggle("Node", on: thread.nodeMode, mode: "node")
                        modeMenuToggle("Compliance", on: thread.complianceMode, mode: "compliance")
                        modeMenuToggle("Payer", on: thread.payerMode, mode: "payer")
                    }
                }
                if model {
                    Section("Model") { modelMenuItems }
                }
                if hasDocument {
                    Button(previewCollapsed ? "Show \(assetKind.name.lowercased())" : "Hide \(assetKind.name.lowercased())") {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.86)) { previewCollapsed.toggle() }
                    }
                }
                if hasFinalize {
                    Divider()
                    Button("Finalize…") { showFinalizeConfirm = true }
                }
            } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.system(size: 13))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("More")
        }
    }

    private func modeMenuToggle(_ label: String, on: Bool, mode: String) -> some View {
        Toggle(label, isOn: Binding(
            get: { on },
            set: { _ in Task { await viewModel.toggleMode(mode) } }
        ))
        .disabled(viewModel.togglingMode != nil)
    }
}
