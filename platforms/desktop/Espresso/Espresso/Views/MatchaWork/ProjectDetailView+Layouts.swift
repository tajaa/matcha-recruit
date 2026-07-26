import SwiftUI
import AppKit
import UniformTypeIdentifiers

extension ProjectDetailView {
    var recruitingLayout: some View {
        HSplitView {
            // Left: Chat panel — drives the recruiting workflow
            if viewModel.activeChatId != nil {
                ChatPanelView(viewModel: chatVM, lightMode: lightMode, selectedModel: selectedModelValue)
                    .frame(minWidth: 320)
            } else {
                VStack(spacing: 12) {
                    Spacer()
                    if let err = viewModel.errorMessage {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 28))
                            .foregroundColor(.red)
                        Text("Couldn't start chat")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(appState.themeText)
                        Text(err)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 24)
                        Button("Retry") {
                            Task {
                                viewModel.errorMessage = nil
                                await viewModel.createChat(title: nil)
                            }
                        }
                        .buttonStyle(.bordered)
                    } else {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .font(.system(size: 28))
                            .foregroundColor(.secondary)
                        Text("Starting chat…")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                }
                .frame(minWidth: 320)
                .background(Color.appBackground)
                .task {
                    if viewModel.activeChatId == nil && viewModel.errorMessage == nil {
                        await viewModel.createChat(title: nil)
                    }
                }
            }

            // Right: Pipeline panel
            RecruitingPipelineView(viewModel: viewModel)
                .frame(minWidth: 300)
        }
        .background(Color.appBackground)
    }

    @ViewBuilder
    var projectLoadingView: some View {
        if let err = viewModel.errorMessage {
            VStack(spacing: 12) {
                Spacer()
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 28))
                    .foregroundColor(.red)
                Text("Couldn't open workspace")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(appState.themeText)
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.appBackground)
        } else {
            // Cold load (no cached data) → shimmer skeleton instead of a late
            // spinner. Warm re-entry skips this entirely (project is non-nil).
            ProjectDetailSkeleton()
                .background(Color.appBackground)
        }
    }

    @ViewBuilder
    var standardLayout: some View {
        if standardMode == .preview {
            MarkdownPreviewView(
                sections: viewModel.project?.sections ?? [],
                title: viewModel.project?.title ?? ""
            )
        } else {
            standardEditLayout
        }
    }

    @ViewBuilder var sidebarProjectHeader: some View {
        if let project = viewModel.project {
            VStack(alignment: .leading, spacing: 2) {
                if let type = project.projectType, type != "general", !type.isEmpty {
                    Text(type.uppercased())
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.secondary)
                        .kerning(0.5)
                }
                Text(project.title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.primary)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            Divider().opacity(0.3)
        }
    }

    var standardEditLayout: some View {
        HSplitView {
            // Sidebar: Sections + Chats
            VStack(spacing: 0) {
                sidebarProjectHeader

                // Sections header
                HStack {
                    Text("Sections")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button {
                        Task { await viewModel.addSection(title: "New Section") }
                    } label: {
                        Image(systemName: "plus").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)

                if let sections = viewModel.project?.sections {
                    ForEach(sections) { section in
                        Button {
                            editingSectionId = section.id
                            viewModel.activeChatId = nil
                        } label: {
                            Text(section.title)
                                .font(.system(size: 12))
                                .foregroundColor(editingSectionId == section.id ? appState.themeText : appState.themeTextSecondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 5)
                                .background(editingSectionId == section.id ? appState.themeAccent.opacity(0.2) : Color.clear)
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button("Delete", role: .destructive) {
                                Task { await viewModel.deleteSection(sectionId: section.id) }
                            }
                        }
                    }
                }

                Divider().opacity(0.3).padding(.vertical, 6)

                // Chats header
                HStack {
                    Text("Chats")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button {
                        Task { await viewModel.createChat(title: nil) }
                    } label: {
                        Image(systemName: "plus").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)

                // Chat list would come from project detail — for now show active chat
                if viewModel.activeChatId != nil {
                    Button {
                        editingSectionId = nil
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "bubble.left").font(.system(size: 10))
                            Text("Chat")
                                .font(.system(size: 12))
                        }
                        .foregroundColor(editingSectionId == nil ? appState.themeText : appState.themeTextSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(editingSectionId == nil ? appState.themeAccent.opacity(0.2) : Color.clear)
                    }
                    .buttonStyle(.plain)
                }

                Spacer()
            }
            .frame(minWidth: 180, maxWidth: 220)
            .background(Color.appBackground)

            // Main content
            if let sectionId = editingSectionId,
               let section = viewModel.project?.sections?.first(where: { $0.id == sectionId }) {
                SectionEditorView(
                    section: section,
                    onSave: { title, content in
                        Task { await viewModel.updateSection(sectionId: sectionId, title: title, content: content) }
                    }
                )
            } else if viewModel.activeChatId != nil {
                HSplitView {
                    ChatPanelView(viewModel: chatVM, lightMode: lightMode, selectedModel: selectedModelValue)
                        .frame(minWidth: 280, idealWidth: 520)
                    if !previewCollapsed && (chatVM.hasPreviewContent || chatVM.isLoadingPDF) {
                        PreviewPanelView(
                            currentState: chatVM.currentState,
                            pdfData: chatVM.pdfData,
                            isLoading: chatVM.isLoadingPDF,
                            taskType: chatVM.thread?.taskType,
                            threadId: chatVM.thread?.id,
                            selectedSlideIndex: Bindable(chatVM).selectedSlideIndex
                        )
                        .frame(minWidth: 320, idealWidth: 420, maxWidth: .infinity)
                    }
                }
            } else {
                ZStack {
                    Color.appBackground.ignoresSafeArea()
                    VStack(spacing: 12) {
                        Image(systemName: "square.grid.2x2").font(.system(size: 36)).foregroundColor(.secondary)
                        Text("Select a section or chat")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .background(Color.appBackground)
    }

    func export(format: String) {
        let pid = viewModel.project?.id ?? "<nil>"
        print("[Export] start format=\(format) project=\(pid)")
        Task { @MainActor in
            let result = await viewModel.exportProject(format: format)
            print("[Export] response format=\(format) bytes=\(result?.count ?? -1) error=\(viewModel.errorMessage ?? "nil")")
            // Defer onto the next runloop tick so the menu/popover has finished
            // dismissing before we present the save panel or alert modal.
            DispatchQueue.main.async {
                guard let data = result, !data.isEmpty else {
                    let msg = viewModel.errorMessage ?? "Export returned no data."
                    print("[Export] \(format) failed: \(msg)")
                    let alert = NSAlert()
                    alert.messageText = "Export failed"
                    alert.informativeText = msg
                    alert.alertStyle = .warning
                    alert.runModal()
                    return
                }
                presentExportSavePanel(data: data, format: format, title: viewModel.project?.title ?? "project")
            }
        }
    }
}
