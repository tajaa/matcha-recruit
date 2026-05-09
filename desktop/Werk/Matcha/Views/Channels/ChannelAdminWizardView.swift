import SwiftUI

enum ChannelAdminWizardMode: Equatable {
    case create
    case manage(channelId: String)

    var isManage: Bool {
        if case .manage = self { return true }
        return false
    }
}

/// Multi-step guide for channel admins. In `.create` mode it walks the user
/// through making a new channel + inviting initial members. In `.manage` mode
/// it shows the current config of an existing channel and lets the admin
/// invite more members.
struct ChannelAdminWizardView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState

    let mode: ChannelAdminWizardMode

    @AppStorage("channel-admin-wizard-shown-v1") private var hasSeenWizard = false

    @State private var step: Int = 1

    // Step 2: create-mode form state
    @State private var name = ""
    @State private var description = ""
    @State private var visibility = "public"
    @State private var isPaid = false
    @State private var priceDollars = "5"
    @State private var creating = false
    @State private var createError: String?

    // Channel created in step 2 (or loaded in `.manage` mode) — drives steps 3 & 4.
    @State private var channel: ChannelDetail?
    @State private var loadingChannel = false
    @State private var loadError: String?

    // Step 3: invite state
    @State private var inviteCount: Int = 0

    private var canCreatePaid: Bool {
        let role = appState.currentUser?.role ?? ""
        return role == "individual" || role == "admin"
    }

    private var skipLabel: String {
        switch step {
        case 1: return "skip wizard"
        case 4: return "close"
        default: return mode.isManage ? "close" : "skip"
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            stepIndicator
            Divider().opacity(0.2)
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            Divider().opacity(0.2)
            footer
        }
        .frame(width: 460, height: 520)
        .background(Color.appBackground)
        .task {
            if case .manage(let id) = mode {
                await loadExisting(id: id)
            }
        }
    }

    // MARK: - Step indicator

    private var stepIndicator: some View {
        HStack(spacing: 6) {
            ForEach(1...4, id: \.self) { i in
                Circle()
                    .fill(i <= step ? Color.matcha500 : Color.white.opacity(0.15))
                    .frame(width: 6, height: 6)
            }
            Spacer()
            Text("step \(step) of 4")
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.4))
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
    }

    // MARK: - Content router

    @ViewBuilder
    private var content: some View {
        switch step {
        case 1: welcomeStep
        case 2: configureStep
        case 3: inviteStep
        default: doneStep
        }
    }

    // MARK: - Step 1: welcome

    private var welcomeStep: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(mode.isManage ? "managing your channel" : "you're a channel admin")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white.opacity(0.95))
                Text(mode.isManage
                     ? "this guide walks through what you control as the owner of this channel."
                     : "channels are spaces where you and invited members talk in real time. as the creator you become the owner. here's what you can do:")
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.6))
                    .fixedSize(horizontal: false, vertical: true)

                VStack(alignment: .leading, spacing: 10) {
                    capability(icon: "lock.shield", title: "set visibility", body: "public channels are discoverable by anyone in the workspace. private channels stay invite-only.")
                    capability(icon: "person.badge.plus", title: "invite members", body: "search by name or email and add people in bulk. members get a notification.")
                    if canCreatePaid {
                        capability(icon: "dollarsign.circle", title: "charge for access", body: "creator channels can be paid — subscribers are billed monthly via stripe. members are warned after 3 days of inactivity before being removed.")
                    }
                    capability(icon: "archivebox", title: "archive when done", body: "owners can archive a channel from the right-click menu in the sidebar. paid subscriptions get cancelled and members notified. cannot be undone.")
                }
            }
            .padding(20)
        }
    }

    private func capability(icon: String, title: String, body: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13))
                .foregroundColor(Color.matcha500)
                .frame(width: 18)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white.opacity(0.85))
                Text(body)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - Step 2: configure / create

    @ViewBuilder
    private var configureStep: some View {
        if mode.isManage {
            manageReview
        } else {
            createForm
        }
    }

    private var createForm: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("create the channel")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white.opacity(0.9))
                Text("name and visibility can be seen by anyone with access. description is optional.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.45))

                VStack(alignment: .leading, spacing: 4) {
                    Text("name").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                    TextField("", text: $name, prompt: Text("general").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.9))
                    Divider()
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("description").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                    TextField("", text: $description, prompt: Text("optional").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.9))
                        .lineLimit(1...3)
                    Divider()
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("visibility").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                    visibilityCard(value: "public", title: "public", body: "anyone in the workspace can find and join")
                    visibilityCard(value: "private", title: "private", body: "invite-only — hidden from sidebar discovery")
                }

                if canCreatePaid {
                    Toggle(isOn: $isPaid) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("paid (subscribers only)")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.white.opacity(0.85))
                            Text("monthly stripe subscription. members removed after inactivity.")
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.45))
                        }
                    }
                    .toggleStyle(.switch)
                    .controlSize(.small)

                    if isPaid {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("price / month (usd)")
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.4))
                            HStack(spacing: 4) {
                                Text("$")
                                    .font(.system(size: 13))
                                    .foregroundColor(.white.opacity(0.5))
                                TextField("", text: $priceDollars, prompt: Text("5").foregroundColor(.white.opacity(0.25)))
                                    .textFieldStyle(.plain)
                                    .font(.system(size: 13))
                                    .foregroundColor(.white.opacity(0.9))
                            }
                            Divider()
                        }
                    }
                }

                if let createError {
                    Text(createError)
                        .font(.system(size: 11))
                        .foregroundColor(.red.opacity(0.8))
                }
            }
            .padding(20)
        }
    }

    private func visibilityCard(value: String, title: String, body: String) -> some View {
        let active = visibility == value
        return Button {
            visibility = value
        } label: {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: active ? "largecircle.fill.circle" : "circle")
                    .foregroundColor(active ? Color.matcha500 : .white.opacity(0.3))
                    .font(.system(size: 14))
                    .padding(.top, 1)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white.opacity(0.85))
                    Text(body)
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.5))
                }
                Spacer()
            }
            .padding(10)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(active ? Color.matcha600.opacity(0.12) : Color.zinc800.opacity(0.4))
            )
        }
        .buttonStyle(.plain)
    }

    private var manageReview: some View {
        Group {
            if loadingChannel {
                VStack { Spacer(); ProgressView(); Spacer() }
            } else if let channel {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("#\(channel.name)")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white.opacity(0.95))
                        if let desc = channel.description, !desc.isEmpty {
                            Text(desc)
                                .font(.system(size: 11))
                                .foregroundColor(.white.opacity(0.55))
                        }
                        configRow(label: "visibility", value: channel.visibility)
                        configRow(label: "members", value: "\(channel.memberCount)")
                        configRow(label: "your role", value: channel.myRole ?? "—")
                        if channel.isPaid, let cents = channel.priceCents {
                            let dollars = Double(cents) / 100.0
                            configRow(label: "price", value: String(format: "$%.2f / mo", dollars))
                        } else {
                            configRow(label: "price", value: "free")
                        }
                        Divider().opacity(0.2)
                        Text("editable from the channel header today")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.4))
                        Text("• click invite (top right) to add more members\n• right-click in the sidebar to archive\n• rename / change visibility coming soon")
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.55))
                    }
                    .padding(20)
                }
            } else if let loadError {
                VStack {
                    Spacer()
                    Text(loadError)
                        .font(.system(size: 11))
                        .foregroundColor(.red.opacity(0.8))
                    Spacer()
                }
            }
        }
    }

    private func configRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.45))
            Spacer()
            Text(value)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.white.opacity(0.85))
        }
    }

    // MARK: - Step 3: invite

    @ViewBuilder
    private var inviteStep: some View {
        if let channel {
            VStack(spacing: 0) {
                Text("invite people to #\(channel.name)")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white.opacity(0.9))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                Divider().opacity(0.2)
                ChannelAdminWizardInvitePicker(channelId: channel.id) { added in
                    inviteCount += added
                }
            }
        } else {
            VStack {
                Spacer()
                Text("no channel selected")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.45))
                Spacer()
            }
        }
    }

    // MARK: - Step 4: done

    private var doneStep: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(Color.matcha500)
                        .font(.system(size: 18))
                    Text(mode.isManage ? "you're all set" : "channel ready")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white.opacity(0.95))
                }
                if let channel {
                    Text("#\(channel.name) · \(channel.memberCount + inviteCount) member\(channel.memberCount + inviteCount == 1 ? "" : "s")")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.55))
                }
                Divider().opacity(0.2)
                Text("next steps")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.55))
                bullet("post a welcome message so members know what this channel is for")
                bullet("pin announcements via the message context menu")
                bullet("invite more people anytime from the channel header")
                bullet("archive (cannot be undone) by right-clicking the channel in the sidebar")
            }
            .padding(20)
        }
    }

    private func bullet(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
                .foregroundColor(.white.opacity(0.4))
            Text(text)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.65))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Footer

    private var footer: some View {
        HStack {
            Button(skipLabel) {
                hasSeenWizard = true
                dismiss()
            }
            .buttonStyle(.plain)
            .font(.system(size: 12))
            .foregroundColor(.white.opacity(0.5))
            .keyboardShortcut(.escape, modifiers: [])

            Spacer()

            if step > 1 && step < 4 {
                Button("back") {
                    step -= 1
                }
                .buttonStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white.opacity(0.6))
                .padding(.horizontal, 6)
            }

            primaryButton
        }
        .padding(14)
    }

    @ViewBuilder
    private var primaryButton: some View {
        switch step {
        case 1:
            Button("get started") { step = 2 }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .controlSize(.small)
        case 2:
            if mode.isManage {
                Button("invite people") { step = 3 }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .controlSize(.small)
                    .disabled(channel == nil)
            } else if channel != nil {
                Button("invite people") { step = 3 }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .controlSize(.small)
            } else {
                Button {
                    Task { await create() }
                } label: {
                    if creating {
                        Text("creating…")
                    } else {
                        Text("create channel")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .controlSize(.small)
                .disabled(creating || name.trimmingCharacters(in: .whitespaces).isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
        case 3:
            Button("next") { step = 4 }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .controlSize(.small)
        default:
            Button("done") {
                hasSeenWizard = true
                if let channel {
                    appState.selectedChannelId = channel.id
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.showInbox = false
                    appState.showSkills = false
                }
                dismiss()
            }
            .buttonStyle(.borderedProminent)
            .tint(Color.matcha600)
            .controlSize(.small)
        }
    }

    // MARK: - Actions

    private func loadExisting(id: String) async {
        loadingChannel = true
        defer { loadingChannel = false }
        do {
            channel = try await ChannelsService.shared.getChannel(id: id)
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func create() async {
        creating = true
        createError = nil
        defer { creating = false }

        var paidConfig: ChannelsService.PaidChannelConfig? = nil
        if isPaid && canCreatePaid {
            guard let dollars = Double(priceDollars.trimmingCharacters(in: .whitespaces)), dollars > 0 else {
                createError = "Enter a valid price"
                return
            }
            let cents = Int((dollars * 100).rounded())
            paidConfig = ChannelsService.PaidChannelConfig(
                priceCents: cents,
                currency: "usd",
                inactivityThresholdDays: nil,
                inactivityWarningDays: 3
            )
        }

        do {
            let created = try await ChannelsService.shared.createChannel(
                name: name.trimmingCharacters(in: .whitespaces),
                description: description.isEmpty ? nil : description,
                visibility: visibility,
                paidConfig: paidConfig
            )
            channel = created
            // Same refresh contract as CreateChannelSheet — bump generation
            // and post the notification so the sidebar shows the new row.
            appState.channelsListGeneration &+= 1
            NotificationCenter.default.post(name: .mwChannelCreated, object: created.id)
            step = 3
        } catch {
            createError = error.localizedDescription
        }
    }
}

/// Embedded version of InviteToChannelSheet's body — same search + multi-select
/// behavior but no surrounding sheet chrome (the wizard supplies that).
private struct ChannelAdminWizardInvitePicker: View {
    let channelId: String
    let onInvited: (Int) -> Void

    @State private var query = ""
    @State private var users: [ChannelsService.InvitableUser] = []
    @State private var selectedIds: Set<String> = []
    @State private var loading = false
    @State private var inviting = false
    @State private var error: String?
    @State private var searchTask: Task<Void, Never>?
    @State private var lastInvitedCount: Int = 0

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                TextField("search by name or email", text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .onChange(of: query) { _, newValue in scheduleSearch(newValue) }
                if loading {
                    ProgressView().controlSize(.small)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Color.zinc800.opacity(0.4))

            Divider().opacity(0.2)

            if users.isEmpty && !loading {
                VStack(spacing: 8) {
                    Image(systemName: "person.crop.circle.badge.questionmark")
                        .font(.system(size: 22))
                        .foregroundColor(.secondary)
                    Text(query.isEmpty ? "type to search workspace people" : "no matching users")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Text("you can also skip this step and invite people later from the channel header.")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.35))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 30)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(20)
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(users) { user in
                            row(user: user, selected: selectedIds.contains(user.id))
                            Divider().opacity(0.1)
                        }
                    }
                }
            }

            Divider().opacity(0.2)

            HStack(spacing: 10) {
                if let err = error {
                    Text(err).font(.system(size: 10)).foregroundColor(.red)
                }
                if lastInvitedCount > 0 {
                    Text("invited \(lastInvitedCount)")
                        .font(.system(size: 10))
                        .foregroundColor(Color.matcha500)
                }
                Spacer()
                Text("\(selectedIds.count) selected")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.45))
                Button {
                    Task { await invite() }
                } label: {
                    if inviting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("invite").font(.system(size: 11, weight: .medium))
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .controlSize(.small)
                .disabled(selectedIds.isEmpty || inviting)
            }
            .padding(12)
        }
        .task { await search("") }
    }

    private func row(user: ChannelsService.InvitableUser, selected: Bool) -> some View {
        Button {
            if selected { selectedIds.remove(user.id) } else { selectedIds.insert(user.id) }
        } label: {
            HStack(spacing: 10) {
                ZStack {
                    Circle().fill(Color.matcha500.opacity(0.4)).frame(width: 26, height: 26)
                    Text(String(user.name.prefix(1)).uppercased())
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(user.name).font(.system(size: 12)).foregroundColor(.white)
                    Text(user.email).font(.system(size: 10)).foregroundColor(.secondary)
                }
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(selected ? Color.matcha500 : .secondary.opacity(0.4))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(selected ? Color.matcha600.opacity(0.06) : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func scheduleSearch(_ q: String) {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(220))
            if Task.isCancelled { return }
            await search(q)
        }
    }

    private func search(_ q: String) async {
        loading = true
        defer { loading = false }
        do {
            users = try await ChannelsService.shared.searchInvitableUsers(query: q, channelId: channelId)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func invite() async {
        inviting = true
        error = nil
        defer { inviting = false }
        do {
            let res = try await ChannelsService.shared.addMembers(
                channelId: channelId,
                userIds: Array(selectedIds)
            )
            let added = res.added?.count ?? selectedIds.count
            lastInvitedCount = added
            onInvited(added)
            selectedIds.removeAll()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
