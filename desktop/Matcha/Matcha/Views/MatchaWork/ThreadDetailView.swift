import SwiftUI

struct ThreadDetailView: View {
    let threadId: String
    @Environment(AppState.self) private var appState
    @State private var viewModel = ThreadDetailViewModel()
    @State private var showVersionHistory = false
    @State private var showFinalizeConfirm = false
    @State private var showUsageSummary = false
    @State private var showAgentPanel = false
    @State private var editingTitle = false
    @State private var titleDraft = ""
    @AppStorage("mw-chat-theme") private var lightMode = false
    @AppStorage("mw-model") private var selectedModelId = "flash"
    @AppStorage("mw-preview-collapsed") private var previewCollapsed = false

    private var selectedModelValue: String? {
        mwModelOptions.first { $0.id == selectedModelId }?.value
    }

    private var isBusinessAccount: Bool {
        guard let role = appState.currentUser?.role else { return false }
        return ["client", "admin", "employee"].contains(role)
    }

    var body: some View {
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

            HSplitView {
                ChatPanelView(viewModel: viewModel, lightMode: lightMode, selectedModel: selectedModelValue)
                    .frame(minWidth: 280, idealWidth: 520)

                if !previewCollapsed && (viewModel.hasPreviewContent || viewModel.isLoadingPDF) {
                    PreviewPanelView(
                        currentState: viewModel.currentState,
                        pdfData: viewModel.pdfData,
                        isLoading: viewModel.isLoadingPDF,
                        taskType: viewModel.thread?.taskType,
                        threadId: viewModel.thread?.id,
                        selectedSlideIndex: Bindable(viewModel).selectedSlideIndex
                    )
                    .frame(minWidth: 320, idealWidth: 420, maxWidth: .infinity)
                }
            }
            .frame(minHeight: 500)
        }
        .background(Color.appBackground)
        .preferredColorScheme(lightMode ? .light : .dark)
        .toolbar {
            ToolbarItem(placement: .navigation) {
                if let thread = viewModel.thread {
                    HStack(spacing: 8) {
                        if editingTitle {
                            TextField("Thread title", text: $titleDraft, onCommit: {
                                let trimmed = titleDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                                guard !trimmed.isEmpty else { editingTitle = false; return }
                                editingTitle = false
                                Task { await viewModel.updateTitle(trimmed) }
                            })
                            .textFieldStyle(.plain)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 200)
                            .onExitCommand { editingTitle = false }

                            Button { editingTitle = false } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                            }
                            .buttonStyle(.plain)
                        } else {
                            Text(thread.title)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.white)
                                .onTapGesture {
                                    titleDraft = thread.title
                                    editingTitle = true
                                }

                            Button {
                                titleDraft = thread.title
                                editingTitle = true
                            } label: {
                                Image(systemName: "pencil")
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                            }
                            .buttonStyle(.plain)
                        }

                        VersionBadge(version: thread.version)
                        StatusBadge(status: thread.status)

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
                }
            }

            ToolbarItemGroup(placement: .primaryAction) {
                // Mode toggles
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

                Divider()

                // Model picker
                Menu {
                    ForEach(mwModelOptions) { option in
                        Button {
                            selectedModelId = option.id
                        } label: {
                            HStack {
                                Text(option.label)
                                if selectedModelId == option.id {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 3) {
                        Image(systemName: "cpu")
                            .font(.system(size: 10))
                        Text(mwModelOptions.first { $0.id == selectedModelId }?.label ?? "Flash")
                            .font(.system(size: 10, weight: .medium))
                    }
                    .padding(.horizontal, 7)
                    .padding(.vertical, 4)
                    .background(Color.zinc800)
                    .cornerRadius(6)
                    .foregroundColor(.secondary)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Select AI model")

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

                // Preview collapse toggle
                if viewModel.hasPreviewContent || viewModel.isLoadingPDF {
                    Button {
                        previewCollapsed.toggle()
                    } label: {
                        Image(systemName: previewCollapsed
                              ? "rectangle.righthalf.inset.filled"
                              : "rectangle.righthalf.inset.filled.arrow.right")
                            .font(.system(size: 13))
                            .foregroundColor(previewCollapsed ? .secondary : .matcha500)
                    }
                    .help(previewCollapsed ? "Show preview panel" : "Hide preview panel")
                }

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
        }
        .task(id: threadId) {
            await viewModel.loadThread(id: threadId)
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
}

// MARK: - Mode Toggle Button

struct ModeToggleButton: View {
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
            .background(isOn ? onColor : Color.zinc800)
            .foregroundColor(isOn ? .white : .secondary)
            .cornerRadius(12)
            .opacity(isLoading ? 0.5 : 1.0)
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
        .help(tooltip)
    }
}
