import SwiftUI

struct ThreadDetailView: View {
    let threadId: String
    @State private var viewModel = ThreadDetailViewModel()
    @State private var showVersionHistory = false
    @State private var showFinalizeConfirm = false

    var body: some View {
        HSplitView {
            ChatPanelView(viewModel: viewModel)
                .frame(minWidth: 320)

            if viewModel.hasPreviewContent || viewModel.isLoadingPDF {
                PreviewPanelView(
                    currentState: viewModel.currentState,
                    pdfData: viewModel.pdfData,
                    isLoading: viewModel.isLoadingPDF,
                    threadId: viewModel.thread?.id
                )
                .frame(minWidth: 300)
            }
        }
        .background(Color.appBackground)
        .toolbar {
            ToolbarItem(placement: .navigation) {
                if let thread = viewModel.thread {
                    HStack(spacing: 8) {
                        Text(thread.title)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.white)
                        VersionBadge(version: thread.version)
                        StatusBadge(status: thread.status)

                        if let usageText = viewModel.tokenUsage?.displayText {
                            Text(usageText)
                                .font(.system(size: 10, design: .monospaced))
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
