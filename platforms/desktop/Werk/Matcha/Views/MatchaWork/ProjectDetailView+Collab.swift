import SwiftUI
import AppKit
import UniformTypeIdentifiers

extension ProjectDetailView {
    @ViewBuilder
    var collabPanelAction: some View {
        switch collabPanel {
        case .sections:
            Button {
                Task {
                    await viewModel.addSection(title: "Untitled note")
                    // Jump straight into the freshly-added note (appended last).
                    await MainActor.run { editingSectionId = viewModel.project?.sections?.last?.id }
                }
            } label: {
                Image(systemName: "square.and.pencil").font(.system(size: 13))
            }
            .help("New note")
        case .files:
            Button {
                NotificationCenter.default.post(name: .mwCollabFilesBrowse, object: nil)
            } label: {
                Image(systemName: "folder.badge.plus").font(.system(size: 13))
            }
            .help("Browse for files")
        case .kanban:
            Button {
                Task { await viewModel.loadTasks() }
            } label: {
                Image(systemName: "arrow.clockwise").font(.system(size: 13))
            }
            .help("Refresh tasks")
        default:
            EmptyView()
        }
    }

    var collabTabStrip: some View {
        HStack(spacing: 2) {
            // Full icon+label row needs ~680pt; in a split pane the project can
            // get ~360pt, which used to compress every label into a one-letter-
            // per-line vertical smear. Fall back to icon-only tabs (tooltips
            // carry the labels) when the labeled row doesn't fit.
            ViewThatFits(in: .horizontal) {
                collabTabButtons(iconOnly: false)
                collabTabButtons(iconOnly: true)
            }
            Spacer(minLength: 4)
            collabStatusPill
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
    }

    func collabTabButtons(iconOnly: Bool) -> some View {
        HStack(spacing: 6) {
            // Threads muted in projects for now (kept in the enum so nothing
            // referencing .threads breaks; just not offered as a tab).
            ForEach(CollabRightPanel.allCases.filter { $0 != .threads }) { panel in
                Button {
                    collabPanel = panel
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: panel.icon)
                            .font(.system(size: 11))
                        if !iconOnly {
                            Text(panel.label)
                                .font(.system(size: 11, weight: .medium))
                                .lineLimit(1)
                                .fixedSize()
                        }
                    }
                    .padding(.horizontal, iconOnly ? 7 : 10)
                    .padding(.vertical, 5)
                    .foregroundColor(collabPanel == panel ? appState.themeText : appState.themeText.opacity(0.55))
                    .background(
                        RoundedRectangle(cornerRadius: 5)
                            .fill(collabPanel == panel ? appState.themeAccent.opacity(0.25) : Color.clear)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 5)
                            .stroke(collabPanel == panel ? appState.themeAccent.opacity(0.4) : Color.clear, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
                .keyboardShortcut(panel.shortcutKey, modifiers: .command)
                .help(panel.label)
            }
        }
    }

    @ViewBuilder
    var collabStatusPill: some View {
        let count = viewModel.project?.collaborators?.count ?? 0
        if count > 0 {
            HStack(spacing: 4) {
                Image(systemName: "person.2.fill")
                    .font(.system(size: 9))
                Text("\(count)")
                    .font(.system(size: 10, weight: .medium))
            }
            .foregroundColor(appState.themeText.opacity(0.55))
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(appState.themeCard.opacity(0.6))
            .cornerRadius(10)
        }
    }

    var collabLayout: some View {
        VStack(spacing: 0) {
            collabTabStrip
            Divider().opacity(0.2)

            switch collabPanel {
            case .chat:
                collabChatView
            case .kanban:
                KanbanBoardView(viewModel: viewModel)
            case .props:
                PropsView(viewModel: viewModel)
            case .files:
                ProjectFilesView(viewModel: viewModel)
            case .media:
                ProjectMediaView(viewModel: viewModel)
            case .elements:
                ElementsView(viewModel: viewModel)
            case .sections:
                collabSections
            case .threads:
                collabThreads
            case .overview:
                collabOverview
            case .history:
                WeeklyReplayView(viewModel: viewModel)
            }
        }
        .background(ThemeRadialBackground())
        .onChange(of: viewModel.project?.id) { _, _ in
            // Lazy-create the per-project discussion channel. Cancel any
            // in-flight ensure call so rapid project switches don't stack
            // duplicate "Setting up the collab channel…" loaders.
            ensureChannelTask?.cancel()
            collabDiscussionChannelId = nil
            collabChannelLoadError = nil
            ensureChannelTask = Task { await ensureCollabDiscussionChannel() }
        }
        .task {
            ensureChannelTask?.cancel()
            ensureChannelTask = Task { await ensureCollabDiscussionChannel() }
        }
    }

    @ViewBuilder
    var collabChatView: some View {
        if let channelId = collabDiscussionChannelId {
            ChannelDetailView(channelId: channelId, isEmbedded: true)
        } else if let err = collabChannelLoadError {
            VStack(spacing: 12) {
                Spacer()
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 28))
                    .foregroundColor(.red)
                Text("Couldn't open collab chat")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(appState.themeText)
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                Button("Retry") {
                    collabChannelLoadError = nil
                    Task { await ensureCollabDiscussionChannel() }
                }
                .buttonStyle(.bordered)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.appBackground)
        } else {
            VStack(spacing: 10) {
                Spacer()
                ProgressView().tint(.secondary)
                Text("Setting up the collab channel…")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.appBackground)
        }
    }

    func ensureCollabDiscussionChannel() async {
        guard let pid = viewModel.project?.id,
              viewModel.project?.projectType == "collab" else { return }
        if collabDiscussionChannelId != nil { return }
        do {
            let id = try await MatchaWorkService.shared.ensureProjectDiscussionChannel(projectId: pid)
            await MainActor.run { collabDiscussionChannelId = id }
        } catch {
            await MainActor.run { collabChannelLoadError = error.localizedDescription }
        }
    }

    @ViewBuilder
    var chatLoadingView: some View {
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
                ProgressView().tint(.secondary)
                Text("Starting chat…")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.appBackground)
    }

    var collabSections: some View {
        // Wrap the panel in a presence overlay so remote cursor positions
        // render on top of the same coordinate space we report mouse moves
        // from. Page-scoped server-side, so cursor traffic only fans out
        // between users on the Sections sub-tab.
        ProjectPresenceOverlay(presenceVM: presenceVM, members: presenceVM.members) {
        VStack(spacing: 0) {
            // Inline panel header with a discoverable "New note" button. The
            // toolbar ✎ is easy to miss in the crowded window toolbar, so the
            // list view carries its own affordance. Hidden while editing a
            // section (the editor has its own back/save chrome).
            if editingSectionId == nil {
                HStack {
                    Text("Notes")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button {
                        Task {
                            await viewModel.addSection(title: "Untitled note")
                            await MainActor.run { editingSectionId = viewModel.project?.sections?.last?.id }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "plus")
                            Text("New note")
                        }
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.matcha500)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                Divider().opacity(0.2)
            }
            if let sections = viewModel.project?.sections, !sections.isEmpty {
                if let sid = editingSectionId,
                   let section = sections.first(where: { $0.id == sid }) {
                    SectionEditorView(
                        section: section,
                        onSave: { title, content in
                            Task { await viewModel.updateSection(sectionId: sid, title: title, content: content) }
                        },
                        onBack: { editingSectionId = nil },
                        onEmail: { emailingSection = section },
                        currentUserId: appState.currentUser?.id,
                        onRestore: { restored in
                            // Pass the current title (a null title would blank it
                            // server-side) — restore only rolls back content.
                            Task { await viewModel.updateSection(sectionId: sid, title: section.title, content: restored) }
                        },
                        projectId: viewModel.project?.id,
                        onCaretMove: { anchor, head in
                            presenceVM.reportCaret(sectionId: sid, anchor: anchor, head: head)
                        },
                        lockedByName: presenceVM.lockedSections[sid]?.name,
                        liveContent: presenceVM.liveSections[sid],
                        remoteCaret: watcherCaret(for: sid),
                        onEditStart: { presenceVM.startEditing(sectionId: sid) },
                        onEditEnd: { presenceVM.endEditing(sectionId: sid) },
                        onTakeOver: { presenceVM.takeOver(sectionId: sid) },
                        onContentChange: { title, content in
                            presenceVM.sendSectionContent(sectionId: sid, title: title, content: content)
                        }
                    )
                    .id(sid)
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(sections) { section in
                                let editingMember = remoteEditor(for: section.id)
                                Button { editingSectionId = section.id } label: {
                                    HStack(alignment: .top, spacing: 8) {
                                        VStack(alignment: .leading, spacing: 3) {
                                            Text(section.title).font(.system(size: 12, weight: .medium)).foregroundColor(appState.themeText)
                                            if let c = section.content, !c.isEmpty {
                                                Text(c.prefix(120))
                                                    .font(.system(size: 10))
                                                    .foregroundColor(.secondary)
                                                    .lineLimit(2)
                                            }
                                            if let editor = section.lastEditedByName, !editor.isEmpty {
                                                Text("Last edited by \(editor)")
                                                    .font(.system(size: 9))
                                                    .foregroundColor(.secondary.opacity(0.8))
                                            }
                                        }
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        if let m = editingMember {
                                            // Small colored dot + initial when a remote
                                            // collaborator's caret is in this section.
                                            // Skips in-text caret rendering for v1 — too
                                            // much NSTextView overlay work — but keeps
                                            // the at-a-glance "X is editing here" signal.
                                            HStack(spacing: 3) {
                                                Circle()
                                                    .fill(UserColor.forUserId(m.id))
                                                    .frame(width: 6, height: 6)
                                                Text(m.name).font(.system(size: 9)).foregroundColor(.secondary)
                                            }
                                        }
                                    }
                                    .padding(10)
                                    .background(appState.themeCard.opacity(0.5))
                                    .cornerRadius(6)
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 3)
                            }
                        }
                    }
                }
            } else {
                Spacer()
                Text("No notes yet — click \"New note\" above or use the AI chat.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            }
        }
        }
        .sheet(item: $emailingSection) { section in
            NoteEmailComposer(
                projectId: viewModel.project?.id ?? "",
                section: section,
                collaborators: viewModel.project?.collaborators ?? [],
                onClose: { emailingSection = nil }
            )
        }
    }

    /// Returns the member whose caret is currently in the given section, if
    /// any. Used to render the "X is editing" badge on the section list.
    func remoteEditor(for sectionId: String) -> ProjectWebSocket.PresenceMember? {
        guard let entry = presenceVM.remoteCarets.first(where: { $0.value.sectionId == sectionId }) else {
            return nil
        }
        return presenceVM.members.first { $0.id == entry.key }
    }

    /// The lock holder's caret in this section, for in-text rendering in the
    /// watcher's read-only editor. Only the holder broadcasts a caret, so this
    /// is the single mark a watcher sees.
    func watcherCaret(for sectionId: String) -> RemoteCaretMark? {
        guard let holder = presenceVM.lockedSections[sectionId],
              let c = presenceVM.remoteCarets[holder.userId],
              c.sectionId == sectionId else { return nil }
        return RemoteCaretMark(
            id: holder.userId,
            color: UserColor.forUserId(holder.userId),
            name: holder.name,
            anchor: c.anchor,
            head: c.head
        )
    }

    var collabOverview: some View {
        CollabOverviewView(
            viewModel: viewModel,
            collabPanel: $collabPanel,
            showCollaborators: $showCollaborators,
            onExport: { export(format: $0) }
        )
    }

    var collabThreads: some View {
        CollabThreadsView(
            projectId: projectId,
            collaborators: viewModel.collaborators,
            currentUserId: appState.currentUser?.id,
            lightMode: lightMode,
            selectedModel: selectedModelValue
        )
    }
}
