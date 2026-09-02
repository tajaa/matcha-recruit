import SwiftUI

// MARK: - The columns themselves: layout, cards, inline add
//
// Split out of KanbanBoardView.swift.

extension KanbanBoardView {

    /// Below this container width the board stacks columns vertically (scroll
    /// down) instead of horizontally (swipe left/right) — fewer than ~2 columns
    /// fit horizontally in the side-by-side split pane (minWidth 360).
    private var kanbanCompactWidth: CGFloat { 520 }

    var boardColumns: some View {
        GeometryReader { geo in
            let compact = geo.size.width < kanbanCompactWidth
            if compact {
                ScrollView(.vertical, showsIndicators: false) {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(columnsFor(mode: viewMode), id: \.key) { col in
                            columnView(key: col.key, label: col.label, compact: true)
                        }
                    }
                    .padding(10)
                }
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 8) {
                        ForEach(columnsFor(mode: viewMode), id: \.key) { col in
                            columnView(key: col.key, label: col.label, compact: false)
                        }
                    }
                    .padding(10)
                }
            }
        }
    }

    /// What one column shows right now, derived once per render. Everything here
    /// is cheap by construction: `displayTasks` reads the view model's memoized
    /// grouping and `doneThisWeekIds` is computed on that same pass, because
    /// this body re-evaluates on every frame of a window-resize drag.
    private struct ColumnLayout {
        let ordered: [MWProjectTask]
        let visible: [MWProjectTask]
        let isDoneColumn: Bool
        let hiddenDoneCount: Int
        /// Per-stage deal total (pipeline mode only).
        let stageValue: Double
        let width: CGFloat
    }

    private func layout(forColumn key: String) -> ColumnLayout {
        // `ordered` is already in final display order (done column pre-sorted
        // most-recently-completed).
        let ordered = displayTasks(forColumn: key)
        // Done never mounts the whole pile. It starts with the five most recent
        // cards and reveals five more for each click, regardless of whether the
        // backing scope was loaded eagerly (cumulative) or on demand (weekly).
        let isDoneColumn = !isPipeline && key == "done"
        // Before the all-time slice is fetched, use the server total so the
        // button is still offered when this week's loaded cards are exhausted.
        // Afterward, use the filtered in-memory count so search results do not
        // leave behind a button that cannot reveal another matching card.
        let availableDoneCount = viewModel.doneScope == "all"
            ? ordered.count
            : viewModel.doneTotal
        let hiddenDoneCount = isDoneColumn
            ? max(0, availableDoneCount - doneVisibleCount)
            : 0
        let visible: [MWProjectTask] = isDoneColumn
            ? Array(ordered.prefix(doneVisibleCount))
            : ordered
        // Empty columns shrink so populated columns get the breathing room.
        // Hovering or starting an inline-add expands them back to full. Full
        // width is kept tight (240) so all five columns fit without much
        // horizontal scrolling now that there's a Changes Requested lane.
        // In compact (vertical) mode every column is full pane width — no shrink.
        let isEmpty = ordered.isEmpty
        let expanded = !isEmpty || inlineAddColumn == key || hoveredEmptyColumn == key
        return ColumnLayout(
            ordered: ordered,
            visible: visible,
            isDoneColumn: isDoneColumn,
            hiddenDoneCount: hiddenDoneCount,
            stageValue: ordered.reduce(0.0) { $0 + ($1.dealValue ?? 0) },
            width: expanded ? 240 : 100
        )
    }

    private func columnView(key: String, label: String, compact: Bool) -> some View {
        let l = layout(forColumn: key)
        return VStack(alignment: .leading, spacing: 6) {
            columnHeader(key: key, label: label, layout: l)

            if inlineAddColumn == key {
                inlineAddRow(column: key)
            }

            // Compact (vertical) mode: render the cards inline so the board's
            // single outer vertical ScrollView owns the scrolling — a nested
            // vertical ScrollView with maxHeight:.infinity would have no
            // intrinsic height inside the outer scroll. Regular mode keeps each
            // column independently scrollable to a filled height.
            if compact {
                columnCards(visibleTasks: l.visible, isDoneColumn: l.isDoneColumn, hiddenDoneCount: l.hiddenDoneCount)
            } else {
                ScrollView {
                    columnCards(visibleTasks: l.visible, isDoneColumn: l.isDoneColumn, hiddenDoneCount: l.hiddenDoneCount)
                }
                .frame(maxHeight: .infinity)
            }
        }
        .frame(maxWidth: compact ? .infinity : nil, alignment: .leading)
        .frame(width: compact ? nil : l.width)
        .animation(compact ? nil : .easeOut(duration: 0.15), value: l.width)
        // Flat tinted fill instead of a glassPanel: each column was an
        // NSVisualEffectView (live blur), and sliding 5 of them horizontally
        // recomposites every frame → the left/right scroll jank. A plain fill
        // over the radial background reads nearly the same and scrolls smooth.
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color.cardBackground.opacity(0.40))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Color.borderColor.opacity(0.5), lineWidth: 1)
        )
        .onHover { hovering in
            // Only react when the column is empty — populated columns don't
            // need to expand.
            if l.ordered.isEmpty {
                hoveredEmptyColumn = hovering ? key : (hoveredEmptyColumn == key ? nil : hoveredEmptyColumn)
            }
        }
        .dropDestination(for: String.self) { items, _ in
            guard let taskId = items.first else { return false }
            move(taskId: taskId, to: key)
            return true
        }
    }

    /// Column title, count, per-column affordances, and the add button.
    @ViewBuilder
    private func columnHeader(key: String, label: String, layout l: ColumnLayout) -> some View {
        HStack {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.5)
            Text("\(l.visible.count)")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .padding(.horizontal, 5)
                .padding(.vertical, 1)
                .background(appState.themeText.opacity(0.08))
                .cornerRadius(4)
            if l.isDoneColumn {
                donePolicyMenu
            }
            if isPipeline && l.stageValue > 0 {
                Text(formatDealValue(l.stageValue))
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(appState.themeAccent)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(appState.themeAccent.opacity(0.12))
                    .cornerRadius(4)
            }
            Spacer()
            addButton(key: key)
        }
        .padding(.horizontal, 8)
        .padding(.top, 6)
    }

    @ViewBuilder
    private func addButton(key: String) -> some View {
        if isPipeline {
            // Sales boards: `+` opens a structured New Deal form
            // (value/contact/expected-close) so deals are trackable from
            // creation — not a bare title quick-add.
            Button {
                dealComposeColumn = key
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Add deal")
        } else {
            Menu {
                Button("Blank task") {
                    inlineAddColumn = key
                    inlineAddTitle = ""
                }
                Divider()
                ForEach(KanbanTemplate.allCases) { tpl in
                    Button {
                        composeTemplate = tpl
                        newTaskColumn = key
                    } label: {
                        Label(tpl.displayName, systemImage: tpl.icon)
                    }
                }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Add task — blank or from a template")
        }
    }

    /// Done-column policy switch, parked in that column's header. Flipping it
    /// only changes what the board shows — no card is archived, moved, or
    /// deleted either way.
    private var donePolicyMenu: some View {
        Menu {
            Picker("Done column", selection: $doneWeeklyReset) {
                Text("Resets weekly").tag(true)
                Text("Cumulative").tag(false)
            }
            .pickerStyle(.inline)
        } label: {
            Image(systemName: doneWeeklyReset ? "calendar.badge.clock" : "infinity")
                .font(.system(size: 9))
                .foregroundColor(.secondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help(doneWeeklyReset
              ? "Done shows this week's finishes — earlier work is behind the expander"
              : "Done shows every finished card, newest first")
    }

    /// Move a card, board- or pipeline-wise, and record it as a self-move so the
    /// next board open doesn't re-flag it. Shared by the column drop target and
    /// the card's own move menu, which had this branch written out twice.
    private func move(taskId: String, to column: String) {
        Task {
            if viewMode == .pipeline {
                await viewModel.movePipelineTask(id: taskId, toStage: column)
            } else {
                await viewModel.moveTask(id: taskId, toColumn: column)
                noteSelfMove(taskId, to: column)
            }
        }
    }

    /// Card stack for one column — shared by both layouts. Regular mode wraps
    /// this in its own ScrollView; compact (vertical) mode renders it inline
    /// under the board's single outer vertical ScrollView.
    @ViewBuilder
    private func columnCards(visibleTasks: [MWProjectTask], isDoneColumn: Bool, hiddenDoneCount: Int) -> some View {
        LazyVStack(spacing: 6) {
            ForEach(visibleTasks) { task in
                card(task)
            }
            if isDoneColumn && hiddenDoneCount > 0 {
                showMoreDoneButton()
            }
        }
        .padding(.horizontal, 6)
        .padding(.bottom, 8)
    }

    private func card(_ task: MWProjectTask) -> some View {
        KanbanCardView(
            task: task,
            attachments: viewModel.taskFiles[task.id] ?? [],
            pipelineMode: isPipeline,
            elementName: task.elementName
                ?? viewModel.elements.first(where: { $0.id == task.elementId })?.name,
            pendingCommitCount: viewModel.pendingSuggestionCount(taskId: task.id),
            autoPRRuntimeApprovalInFlight: approvingAutoPRRuntimeTaskIds.contains(task.id),
            onTap: { open(task) },
            onToggle: { Task { await viewModel.toggleTaskComplete(id: task.id) } },
            onMoveColumn: { col in move(taskId: task.id, to: col) },
            onApproveAutoPRRuntime: { approveAutoPRRuntime(for: task) }
        )
        // Glide across columns when the replay clears its overrides.
        .matchedGeometryEffect(id: task.id, in: cardNS)
        .overlay { unreadRing(task) }
        .draggable(task.id)
        .contextMenu { cardContextMenu(task) }
    }

    /// Acknowledge the change → drop the yellow outline and advance this user's
    /// persisted baseline for the card — then open the viewer.
    private func open(_ task: MWProjectTask) {
        acknowledge(task.id)
        viewingTask = task
    }

    private func approveAutoPRRuntime(for task: MWProjectTask) {
        guard let projectId = viewModel.project?.id,
              let progressNote = task.progressNote,
              !approvingAutoPRRuntimeTaskIds.contains(task.id) else { return }
        approvingAutoPRRuntimeTaskIds.insert(task.id)
        Task {
            defer { approvingAutoPRRuntimeTaskIds.remove(task.id) }
            do {
                _ = try await MatchaWorkService.shared.requestAutoPRReconsideration(
                    projectId: projectId,
                    taskId: task.id,
                    body: "--extend-runtime",
                    expectedProgressNote: progressNote
                )
                await viewModel.loadTasks()
            } catch {
                viewModel.errorMessage = error.localizedDescription
            }
        }
    }

    /// Yellow ring marks tickets moved/added OR carrying unviewed updates (a
    /// changes-requested send-back, new round, comment) since this user last
    /// opened them. The column-move diff alone misses a send-back that
    /// round-trips to an already-seen column or lands live after the board
    /// mounted, so also key off the per-user unviewed-updates count. Persists
    /// until the card is opened (acknowledge + the viewer mark everything viewed).
    private func unreadRing(_ task: MWProjectTask) -> some View {
        let ringed = changedIds.contains(task.id)
            || TicketUpdatesStore.shared.unviewedCount(task) > 0
        // Hairline ring + soft outer glow instead of the old 2pt
        // full-saturation stroke — still unmissable in a column scan, no longer
        // shouting over the card content.
        return RoundedRectangle(cornerRadius: 10, style: .continuous)
            .strokeBorder(Color.yellow.opacity(ringed ? 0.75 : 0), lineWidth: 1.5)
            .shadow(color: .yellow.opacity(ringed ? 0.35 : 0), radius: 5)
            .allowsHitTesting(false)
    }

    @ViewBuilder
    private func cardContextMenu(_ task: MWProjectTask) -> some View {
        Button {
            open(task)
        } label: { Label("Open", systemImage: "arrow.up.right.square") }
        Button {
            // Reference this ticket into the project chat (reply-style) and jump
            // to the chat panel so the user can ask about it.
            appState.pendingTicketRef = TicketChatRef(
                id: task.id, title: task.title, column: task.boardColumn)
            appState.pendingProjectPanel = .chat
        } label: { Label("Chat about this ticket", systemImage: "bubble.left.and.text.bubble.right") }
        Button {
            Task { await viewModel.duplicateTask(task) }
        } label: { Label("Duplicate", systemImage: "doc.on.doc") }
        Button(role: .destructive) {
            taskToDelete = task
        } label: { Label("Delete", systemImage: "trash") }
    }

    private func showMoreDoneButton() -> some View {
        Button {
            Task {
                // Weekly mode initially holds only this week's finishes. Fetch
                // the all-time slice before revealing the next batch.
                await viewModel.loadAllDoneTasks()
                doneVisibleCount += 5
            }
        } label: {
            Text("Show more")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 5)
                .background(appState.themeText.opacity(0.05))
                .cornerRadius(5)
        }
        .buttonStyle(.plain)
        .disabled(viewModel.isLoadingTasks)
    }

    // MARK: - Inline add

    private func inlineAddRow(column: String) -> some View {
        HStack(spacing: 6) {
            TextField("New task", text: $inlineAddTitle)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(appState.themeText.opacity(0.06))
                .cornerRadius(5)
                .onSubmit { commitInlineAdd(column: column) }
            Button {
                commitInlineAdd(column: column)
            } label: {
                Image(systemName: "return")
                    .font(.system(size: 9))
                    .foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.return, modifiers: [])
            .disabled(inlineAddTitle.trimmingCharacters(in: .whitespaces).isEmpty)
            Button {
                inlineAddColumn = nil
                inlineAddTitle = ""
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.escape, modifiers: [])
        }
        .padding(.horizontal, 6)
    }

    private func commitInlineAdd(column: String) {
        let trimmed = inlineAddTitle.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        Task {
            if viewMode == .pipeline {
                await viewModel.addTask(title: trimmed, column: "todo", pipelineColumn: column)
            } else {
                await viewModel.addTask(title: trimmed, column: column)
            }
            inlineAddTitle = ""
        }
    }
}
