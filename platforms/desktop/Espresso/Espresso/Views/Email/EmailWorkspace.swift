import SwiftUI
import AppKit

/// Full-pane Email hub — the sidebar "Email" row opens it (same nav-only
/// model as the other hubs). Three columns: mailbox (unread + the AI triage
/// buckets), message list, reader. Sorting runs automatically for Lite+ and
/// stays in the app: nothing is labelled, moved or marked read in Gmail.
/// ⌘-click / ⇧-click picks several messages to send to a board together.
struct EmailWorkspace: View {
    @Environment(AppState.self) private var appState
    private let vm = EmailViewModel.shared

    enum Filter: Hashable {
        case all
        case bucket(EmailTriageBucket)
        case unsorted
    }

    /// A Send-to-board request; `.sheet(item:)` needs an identity.
    private struct BoardRequest: Identifiable {
        let id = UUID()
        let emails: [EmailMessage]
    }

    /// The server snapshots at most this many messages onto one card.
    static let maxPerCard = 10

    @AppStorage("email.autoOrganize") private var autoOrganize = true
    @State private var filter: Filter = .all
    @State private var search = ""
    @State private var selection: Set<String> = []
    @State private var anchor: String?
    @State private var scrollTarget: String?
    @State private var railCollapsed = false
    @State private var boardRequest: BoardRequest?
    @State private var boardNote: String?
    @FocusState private var listFocused: Bool

    var body: some View {
        Group {
            if !vm.statusLoaded {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !vm.connected {
                connectState
            } else {
                HSplitView {
                    if railCollapsed {
                        MWHubRailStrip { railCollapsed = false }
                    } else {
                        mailboxRail.frame(minWidth: 180, idealWidth: 200, maxWidth: 250)
                    }
                    messageList.frame(minWidth: 280, idealWidth: 340, maxWidth: 460)
                    readerPane.frame(minWidth: 400, maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .background(ThemeRadialBackground())
        .task {
            await vm.loadStatus()
            adoptRequestedEmail()
            await autoOrganizeIfNeeded()
        }
        .onChange(of: appState.selectedEmailId) { _, _ in adoptRequestedEmail() }
        .onChange(of: vm.emails.map(\.id)) { _, _ in
            Task { await autoOrganizeIfNeeded() }
        }
        .onChange(of: appState.canEmailAI) { _, _ in
            Task { await autoOrganizeIfNeeded() }
        }
        .onChange(of: selection) { _, _ in boardNote = nil }
        .sheet(item: $boardRequest) { request in
            EmailSendToBoardSheet(emails: request.emails) { board in
                boardNote = request.emails.count == 1
                    ? "Email card created on \(board)"
                    : "Card with \(request.emails.count) emails created on \(board)"
            }
        }
    }

    // MARK: - State helpers

    /// `selectedEmailId` is an "open this message" request from outside the
    /// hub. The hub owns selection from then on, so the request is consumed.
    private func adoptRequestedEmail() {
        guard let id = appState.selectedEmailId else { return }
        appState.showEmailHub = true
        selection = [id]
        anchor = id
        if !shown.contains(where: { $0.id == id }) {
            filter = .all
            search = ""
        }
        appState.selectedEmailId = nil
    }

    private func autoOrganizeIfNeeded() async {
        guard autoOrganize, appState.canEmailAI, vm.connected, !vm.emails.isEmpty else { return }
        await vm.organizeNew()
    }

    private var shown: [EmailMessage] {
        let base: [EmailMessage]
        switch filter {
        case .all: base = vm.emails
        case .bucket(let bucket): base = vm.emails.filter { vm.bucket(of: $0.id) == bucket }
        case .unsorted: base = vm.emails.filter { vm.bucket(of: $0.id) == nil }
        }
        let q = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return base }
        return base.filter {
            $0.subject.lowercased().contains(q)
                || $0.fromAddress.lowercased().contains(q)
                || ($0.snippet ?? "").lowercased().contains(q)
        }
    }

    /// Sectioned by bucket in the Unread view once something is sorted; a
    /// bucket view is already a single group.
    private var sections: [EmailGroup] {
        filter == .all ? vm.grouped(shown) : [EmailGroup(bucket: nil, emails: shown)]
    }

    private var showsSectionHeaders: Bool { filter == .all && !vm.triage.isEmpty }

    /// Display order, for ⇧-click ranges and the arrow keys.
    private var orderedIds: [String] { sections.flatMap { $0.emails.map(\.id) } }

    private var selectedEmails: [EmailMessage] {
        let ordered = orderedIds.filter { selection.contains($0) }
        let offList = selection.subtracting(ordered).sorted()
        return (ordered + offList).compactMap { vm.message(id: $0) }
    }

    private var listTitle: String {
        switch filter {
        case .all: return "Unread"
        case .bucket(let bucket): return bucket.label
        case .unsorted: return "Unsorted"
        }
    }

    private func click(_ id: String) {
        listFocused = true
        let mods = NSEvent.modifierFlags
        if mods.contains(.command) {
            if selection.contains(id) { selection.remove(id) } else { selection.insert(id) }
            anchor = id
        } else if mods.contains(.shift), let from = anchor.flatMap({ orderedIds.firstIndex(of: $0) }),
                  let to = orderedIds.firstIndex(of: id) {
            selection = Set(orderedIds[min(from, to)...max(from, to)])
        } else {
            selection = [id]
            anchor = id
        }
    }

    private func move(_ delta: Int) {
        let ids = orderedIds
        guard !ids.isEmpty else { return }
        let current = anchor.flatMap { ids.firstIndex(of: $0) } ?? (delta > 0 ? -1 : ids.count)
        let next = min(max(current + delta, 0), ids.count - 1)
        selection = [ids[next]]
        anchor = ids[next]
        scrollTarget = ids[next]
    }

    private func sendToBoard(_ emails: [EmailMessage]) {
        guard !emails.isEmpty, emails.count <= Self.maxPerCard else { return }
        boardNote = nil
        boardRequest = BoardRequest(emails: emails)
    }

    // MARK: - Mailbox rail

    private var mailboxRail: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Text("Mailbox")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                Button { Task { await vm.loadInbox() } } label: {
                    Image(systemName: "arrow.clockwise").font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .disabled(vm.isLoading)
                .help("Check for new mail")
                Button { railCollapsed = true } label: {
                    Image(systemName: "sidebar.left").font(.system(size: 12))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("Hide mailbox")
            }
            .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 8)

            ScrollView {
                VStack(alignment: .leading, spacing: 1) {
                    railRow("Unread", icon: "tray", count: vm.emails.count, target: .all)
                    railHeading("Sorted by AI")
                    sortedRows
                }
                .padding(.horizontal, 6)
            }
            Spacer(minLength: 0)
            accountFooter
        }
        .frame(maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder
    private var sortedRows: some View {
        if !appState.canEmailAI {
            railAction("Organize with AI", icon: "lock.fill") {
                appState.presentPaywall(for: "email_ai")
            }
        } else if vm.triage.isEmpty && !vm.isTriaging {
            railAction("Organize with AI", icon: "sparkles") {
                Task { await vm.organizeNew() }
            }
            .disabled(vm.emails.isEmpty)
        } else {
            ForEach(EmailTriageBucket.allCases, id: \.self) { bucket in
                railRow(bucket.label, icon: bucket.icon, count: vm.count(of: bucket),
                        target: .bucket(bucket), tint: bucket.tint)
            }
            if vm.unsortedCount > 0 {
                railRow("Unsorted", icon: "questionmark.folder", count: vm.unsortedCount, target: .unsorted)
            }
            if vm.isTriaging {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.mini)
                    Text("Sorting new mail…")
                }
                .font(.system(size: 11))
                .foregroundColor(appState.themeSidebarTextSecondary)
                .padding(.horizontal, 8).padding(.vertical, 5)
            }
        }
    }

    private func railRow(_ title: String, icon: String, count: Int, target: Filter, tint: Color? = nil) -> some View {
        let selected = filter == target
        return Button { filter = target } label: {
            HStack(spacing: 7) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                    .foregroundColor(tint ?? (selected ? appState.themeSidebarAccent : appState.themeSidebarTextSecondary))
                    .frame(width: 15)
                Text(title)
                    .font(.system(size: 12, weight: selected ? .semibold : .regular))
                    .foregroundColor(appState.themeSidebarText.opacity(0.92))
                Spacer(minLength: 0)
                if count > 0 {
                    Text("\(count)")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(appState.themeSidebarTextSecondary)
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 6).fill(selected ? appState.themeSidebarAccent.opacity(0.10) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func railAction(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Image(systemName: icon).font(.system(size: 11)).frame(width: 15)
                Text(title).font(.system(size: 12, weight: .medium))
                Spacer(minLength: 0)
            }
            .foregroundColor(appState.themeAccent)
            .padding(.horizontal, 8).padding(.vertical, 5)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func railHeading(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 9, weight: .semibold))
            .tracking(0.6)
            .foregroundColor(appState.themeSidebarTextSecondary)
            .padding(.horizontal, 8).padding(.top, 12).padding(.bottom, 3)
    }

    private var accountFooter: some View {
        HStack(spacing: 6) {
            Image(systemName: "checkmark.seal")
                .font(.system(size: 10))
                .foregroundColor(appState.themeSidebarAccent)
            Text(vm.email ?? "Gmail connected")
                .font(.system(size: 10.5))
                .foregroundColor(appState.themeSidebarTextSecondary)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer(minLength: 4)
            Menu {
                Toggle("Sort new mail automatically", isOn: $autoOrganize)
                    .disabled(!appState.canEmailAI)
                Button("Re-sort everything") { Task { await vm.reorganize() } }
                    .disabled(!appState.canEmailAI || vm.emails.isEmpty || vm.isTriaging)
                if !vm.triage.isEmpty {
                    Button("Clear groups") {
                        vm.clearTriage()
                        filter = .all
                    }
                }
                Divider()
                Button("Disconnect Gmail", role: .destructive) {
                    Task {
                        await vm.disconnect()
                        selection = []
                        anchor = nil
                    }
                }
            } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeSidebarTextSecondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Mailbox options")
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    // MARK: - Message list

    private var messageList: some View {
        VStack(spacing: 0) {
            VStack(spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                    TextField("Search mail", text: $search)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText)
                    if !search.isEmpty {
                        Button { search = "" } label: {
                            Image(systemName: "xmark.circle.fill").font(.system(size: 11))
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(appState.themeTextSecondary)
                    }
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeCard.opacity(0.6)))

                HStack(spacing: 6) {
                    Text(listTitle)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(appState.themeText)
                        .lineLimit(1)
                    Text("\(shown.count)")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                    Spacer()
                    if vm.isLoading { ProgressView().controlSize(.mini) }
                }
            }
            .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 8)
            Divider().opacity(0.2)

            if vm.isLoading && vm.emails.isEmpty {
                Spacer()
                ProgressView().controlSize(.small)
                Spacer()
            } else if shown.isEmpty {
                listEmptyState
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 1) {
                            ForEach(sections) { group in
                                if showsSectionHeaders {
                                    sectionHeader(group)
                                }
                                ForEach(group.emails) { msg in
                                    EmailListRow(
                                        msg: msg,
                                        info: vm.rowInfo(for: msg),
                                        selected: selection.contains(msg.id),
                                        reason: vm.triage[msg.id]?.reason
                                    )
                                    .id(msg.id)
                                    .onTapGesture { click(msg.id) }
                                    .contextMenu { rowMenu(msg) }
                                }
                            }
                        }
                        .padding(.vertical, 4).padding(.horizontal, 6)
                    }
                    .onChange(of: scrollTarget) { _, id in
                        guard let id else { return }
                        proxy.scrollTo(id)
                    }
                }
                .focusable()
                .focused($listFocused)
                .focusEffectDisabled()
                .onKeyPress(.upArrow) { move(-1); return .handled }
                .onKeyPress(.downArrow) { move(1); return .handled }
            }

            if let err = vm.errorMessage {
                HStack(spacing: 5) {
                    Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9))
                    Text(err).font(.system(size: 10)).lineLimit(2)
                    Spacer(minLength: 0)
                }
                .foregroundColor(.orange)
                .padding(.horizontal, 12).padding(.vertical, 6)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeBg.opacity(0.3))
    }

    @ViewBuilder
    private func rowMenu(_ msg: EmailMessage) -> some View {
        let targets = selection.contains(msg.id) && selection.count > 1 ? selectedEmails : [msg]
        Button(targets.count > 1 ? "Send \(targets.count) emails to board…" : "Send to board…") {
            sendToBoard(targets)
        }
        .disabled(targets.count > Self.maxPerCard)
        Button("Copy sender address") {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(msg.senderAddress, forType: .string)
        }
    }

    private func sectionHeader(_ group: EmailGroup) -> some View {
        HStack(spacing: 5) {
            Image(systemName: group.bucket?.icon ?? "tray")
                .font(.system(size: 9))
                .foregroundColor(group.bucket?.tint ?? appState.themeTextSecondary)
            Text((group.bucket?.label ?? "Unsorted").uppercased())
                .font(.system(size: 9.5, weight: .semibold))
                .tracking(0.5)
            Text("\(group.emails.count)").font(.system(size: 9.5))
            Spacer()
        }
        .foregroundColor(appState.themeTextSecondary)
        .padding(.horizontal, 8).padding(.top, 10).padding(.bottom, 3)
    }

    private var listEmptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: search.isEmpty ? "tray" : "magnifyingglass")
                .font(.system(size: 22))
                .foregroundColor(appState.themeTextSecondary.opacity(0.7))
            Text(search.isEmpty ? (filter == .all ? "No unread mail" : "Nothing here") : "No matches")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(appState.themeTextSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Reader

    @ViewBuilder
    private var readerPane: some View {
        if selection.count == 1, let id = selection.first {
            EmailDetailView(emailId: id)
        } else if selection.count > 1 {
            multiSelectPanel
        } else {
            VStack(spacing: 10) {
                Image(systemName: "envelope.open")
                    .font(.system(size: 30))
                    .foregroundColor(appState.themeTextSecondary.opacity(0.6))
                Text("Select an email to read")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(appState.themeTextSecondary)
                Text("⌘-click or ⇧-click to pick several and send them to a board together.")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary.opacity(0.8))
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var multiSelectPanel: some View {
        let picked = selectedEmails
        return VStack(spacing: 14) {
            Image(systemName: "envelope.badge")
                .font(.system(size: 28))
                .foregroundColor(appState.themeAccent)
            Text("\(picked.count) emails selected")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(appState.themeText)
            VStack(alignment: .leading, spacing: 4) {
                ForEach(picked.prefix(6)) { msg in
                    HStack(spacing: 6) {
                        Text(vm.rowInfo(for: msg).senderName)
                            .font(.system(size: 11, weight: .semibold))
                        Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                            .font(.system(size: 11))
                    }
                    .lineLimit(1)
                    .foregroundColor(appState.themeTextSecondary)
                }
                if picked.count > 6 {
                    Text("and \(picked.count - 6) more")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary.opacity(0.8))
                }
            }
            .frame(maxWidth: 360, alignment: .leading)
            HStack(spacing: 10) {
                Button("Clear selection") {
                    selection = []
                    anchor = nil
                }
                Button {
                    sendToBoard(picked)
                } label: {
                    Label("Send to board", systemImage: "rectangle.stack.badge.plus")
                }
                .buttonStyle(.borderedProminent)
                .disabled(picked.count > Self.maxPerCard)
            }
            if picked.count > Self.maxPerCard {
                Text("A card holds up to \(Self.maxPerCard) emails.")
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
            }
            if let boardNote {
                Label(boardNote, systemImage: "checkmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.green)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Not connected

    private var connectState: some View {
        VStack(spacing: 14) {
            Image(systemName: "envelope.badge.shield.half.filled")
                .font(.system(size: 34))
                .foregroundColor(appState.themeAccent)
            Text("Connect Gmail")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(appState.themeText)
            Text("Read your unread mail, get a quick summary, and draft replies without leaving Espresso. Sorting happens here in the app: nothing in Gmail is labelled, moved, or marked read.")
                .font(.system(size: 12))
                .foregroundColor(appState.themeTextSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 400)
            Button {
                Task { await vm.connect() }
            } label: {
                if vm.isConnecting {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("Waiting for Google…")
                    }
                } else {
                    Text("Connect Gmail")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(vm.isConnecting)
            if let err = vm.errorMessage {
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
            }
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Shared email UI pieces

/// One message in the hub list: avatar, sender, date, subject, preview.
struct EmailListRow: View {
    let msg: EmailMessage
    let info: EmailRowInfo
    let selected: Bool
    var reason: String? = nil
    @Environment(AppState.self) private var appState

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            EmailAvatar(initial: info.initial, tint: info.tint, size: 28)
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(info.senderName)
                        .font(.system(size: 12.5, weight: .semibold))
                        .foregroundColor(appState.themeText)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    Text(info.dateLabel)
                        .font(.system(size: 10.5))
                        .foregroundColor(appState.themeTextSecondary)
                }
                Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText.opacity(0.88))
                    .lineLimit(1)
                if !info.preview.isEmpty {
                    Text(info.preview)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(2)
                }
            }
        }
        .padding(.horizontal, 8).padding(.vertical, 7)
        .background(RoundedRectangle(cornerRadius: 7).fill(selected ? appState.themeAccent.opacity(0.14) : Color.clear))
        .contentShape(Rectangle())
        .help(reason ?? "")
    }
}

/// Sender initial on a color that stays the same for that sender.
struct EmailAvatar: View {
    let initial: String
    let tint: Int
    var size: CGFloat = 28

    static let palette: [Color] = [.blue, .purple, .pink, .orange, .teal, .green, .indigo, .red]

    var body: some View {
        Circle()
            .fill(Self.palette[tint % Self.palette.count].opacity(0.85))
            .frame(width: size, height: size)
            .overlay(
                Text(initial)
                    .font(.system(size: size * 0.44, weight: .semibold))
                    .foregroundColor(.white)
            )
    }
}

struct EmailBucketChip: View {
    let bucket: EmailTriageBucket

    var body: some View {
        Label(bucket.label, systemImage: bucket.icon)
            .font(.system(size: 10, weight: .medium))
            .foregroundColor(bucket.tint)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(Capsule().fill(bucket.tint.opacity(0.14)))
    }
}

extension EmailTriageBucket {
    var tint: Color {
        switch self {
        case .needsReply: return .orange
        case .action: return .blue
        case .fyi: return .gray
        case .newsletter: return .purple
        }
    }
}
