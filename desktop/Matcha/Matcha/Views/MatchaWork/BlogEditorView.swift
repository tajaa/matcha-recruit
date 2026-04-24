import SwiftUI
import AppKit

struct BlogEditorView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    let chatVM: ThreadDetailViewModel
    let lightMode: Bool
    let selectedModel: String?

    @AppStorage("mw-model") private var selectedModelId = "flash"

    @State private var tab: Tab = .write
    @State private var selectedSectionId: String?
    @State private var showExport = false

    enum Tab { case write, preview, publish }

    var body: some View {
        HSplitView {
            leftSidebar
                .frame(minWidth: 200, maxWidth: 240)

            VStack(spacing: 0) {
                tabBar
                Divider().opacity(0.3)
                tabContent
            }
        }
        .background(Color.appBackground)
        .toolbar {
            ToolbarItem(placement: .navigation) {
                if let project = viewModel.project {
                    Text(project.title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
            ToolbarItemGroup(placement: .primaryAction) {
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

                Menu {
                    Button("Markdown + Frontmatter") { exportMd() }
                    Button("Markdown") { exportMd(format: "md") }
                } label: {
                    Image(systemName: "square.and.arrow.up").font(.system(size: 13))
                }
                .help("Export post")
            }
        }
    }

    // MARK: - Left sidebar: sections + chat

    private var leftSidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
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

            let sections = viewModel.project?.sections ?? []
            if sections.isEmpty {
                Text("No sections yet — ask AI to create an outline")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
            } else {
                ForEach(sections) { section in
                    Button {
                        selectedSectionId = section.id
                        tab = .write
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(section.title)
                                .font(.system(size: 12))
                                .foregroundColor(selectedSectionId == section.id ? .white : .secondary)
                                .lineLimit(1)
                            let wc = wordCount(section.content)
                            if wc > 0 {
                                Text("\(wc) words")
                                    .font(.system(size: 9))
                                    .foregroundColor(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(selectedSectionId == section.id ? Color.matcha600.opacity(0.2) : Color.clear)
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

            HStack {
                Text("AI Chat")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 4)

            Button {
                selectedSectionId = nil
                tab = .write
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "bubble.left").font(.system(size: 10))
                    Text("Blog Chat")
                        .font(.system(size: 12))
                }
                .foregroundColor(selectedSectionId == nil && tab == .write ? .white : .secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 12)
                .padding(.vertical, 5)
                .background(selectedSectionId == nil && tab == .write ? Color.matcha600.opacity(0.2) : Color.clear)
            }
            .buttonStyle(.plain)

            Spacer()

            let blog = viewModel.blogData
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    statusPill(blog.status)
                    Text("\(blog.wordCount) words · \(blog.readMinutes) min")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                if !blog.tone.isEmpty {
                    Text("Tone: \(blog.tone)")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .background(Color.appBackground)
    }

    // MARK: - Tab bar

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach([(Tab.write, "Write"), (Tab.preview, "Preview"), (Tab.publish, "Publish")], id: \.1) { t, label in
                Button {
                    tab = t
                    if t == .write && selectedSectionId == nil && viewModel.activeChatId == nil {
                        // leave selection as-is
                    }
                } label: {
                    Text(label)
                        .font(.system(size: 12, weight: tab == t ? .semibold : .regular))
                        .foregroundColor(tab == t ? .white : .secondary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(tab == t ? Color.matcha600.opacity(0.15) : Color.clear)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .background(Color.appBackground)
    }

    // MARK: - Tab content

    @ViewBuilder
    private var tabContent: some View {
        switch tab {
        case .write:
            writeTab
        case .preview:
            MarkdownPreviewView(
                sections: viewModel.project?.sections ?? [],
                title: viewModel.project?.title ?? ""
            )
        case .publish:
            publishTab
        }
    }

    @ViewBuilder
    private var writeTab: some View {
        if let sectionId = selectedSectionId,
           let section = viewModel.project?.sections?.first(where: { $0.id == sectionId }) {
            SectionEditorView(
                section: section,
                onSave: { title, content in
                    Task { await viewModel.updateSection(sectionId: sectionId, title: title, content: content) }
                },
                onAcceptRevision: {
                    Task { await viewModel.acceptSectionRevision(sectionId: sectionId) }
                },
                onRejectRevision: {
                    Task { await viewModel.rejectSectionRevision(sectionId: sectionId) }
                },
                onRestore: { restoredContent in
                    Task { await viewModel.updateSection(sectionId: sectionId, content: restoredContent) }
                },
                projectId: viewModel.project?.id
            )
        } else {
            // Show AI chat panel
            if viewModel.activeChatId != nil {
                ChatPanelView(viewModel: chatVM, lightMode: lightMode, selectedModel: selectedModel)
            } else {
                VStack(spacing: 12) {
                    Spacer()
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("Starting chat…")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .background(Color.appBackground)
                .task {
                    if viewModel.activeChatId == nil {
                        await viewModel.createChat(title: nil)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var publishTab: some View {
        let blog = viewModel.blogData
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Status
                VStack(alignment: .leading, spacing: 6) {
                    Text("Status").font(.system(size: 11, weight: .semibold)).foregroundColor(.secondary)
                    HStack(spacing: 8) {
                        ForEach(["draft", "scheduled", "published"], id: \.self) { s in
                            Button {
                                Task { await viewModel.transitionBlogStatus(to: s) }
                            } label: {
                                Text(s.capitalized)
                                    .font(.system(size: 12))
                                    .foregroundColor(blog.status == s ? .white : .secondary)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 4)
                                    .background(blog.status == s ? Color.matcha600.opacity(0.3) : Color.zinc800)
                                    .cornerRadius(5)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                // Metadata summary
                VStack(alignment: .leading, spacing: 6) {
                    Text("Metadata").font(.system(size: 11, weight: .semibold)).foregroundColor(.secondary)
                    metaRow("Slug", blog.slug.isEmpty ? "(auto)" : blog.slug)
                    metaRow("Tone", blog.tone)
                    metaRow("Audience", blog.audience.isEmpty ? "–" : blog.audience)
                    if !blog.tags.isEmpty {
                        metaRow("Tags", blog.tags.joined(separator: ", "))
                    }
                    metaRow("Word count", "\(blog.wordCount)")
                    metaRow("Read time", "\(blog.readMinutes) min")
                }

                // Excerpt
                VStack(alignment: .leading, spacing: 6) {
                    Text("Excerpt").font(.system(size: 11, weight: .semibold)).foregroundColor(.secondary)
                    Text(blog.excerpt.isEmpty ? "No excerpt — ask AI to generate one" : blog.excerpt)
                        .font(.system(size: 12))
                        .foregroundColor(blog.excerpt.isEmpty ? .secondary : Color(white: 0.85))
                        .italic(blog.excerpt.isEmpty)
                }

                // Author
                if let name = blog.author.name, !name.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Author").font(.system(size: 11, weight: .semibold)).foregroundColor(.secondary)
                        metaRow("Name", name)
                        if let bio = blog.author.bio, !bio.isEmpty {
                            metaRow("Bio", bio)
                        }
                    }
                }
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Color(white: 0.08))
    }

    // MARK: - Helpers

    private func metaRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text(label)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .frame(width: 80, alignment: .leading)
            Text(value)
                .font(.system(size: 12))
                .foregroundColor(Color(white: 0.85))
                .textSelection(.enabled)
        }
    }

    private func statusPill(_ status: String) -> some View {
        let color: Color = status == "published" ? .green : status == "scheduled" ? .orange : .secondary
        return Text(status)
            .font(.system(size: 9, weight: .medium))
            .foregroundColor(color)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .cornerRadius(3)
    }

    private func wordCount(_ text: String?) -> Int {
        guard let t = text, !t.isEmpty else { return 0 }
        return t.split(separator: " ").count
    }

    private func exportMd(format: String = "md_frontmatter") {
        Task {
            guard let data = await viewModel.exportBlogMarkdown() else { return }
            let panel = NSSavePanel()
            panel.nameFieldStringValue = "\(viewModel.project?.title ?? "post").md"
            panel.begin { response in
                guard response == .OK, let url = panel.url else { return }
                try? data.write(to: url)
            }
        }
    }
}
