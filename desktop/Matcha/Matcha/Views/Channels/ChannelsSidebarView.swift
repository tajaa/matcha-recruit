import SwiftUI

struct ChannelsSidebarView: View {
    @Environment(AppState.self) private var appState
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var showCreate = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()

            if isLoading {
                Spacer()
                Text("loading")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                Spacer()
            } else if channels.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Text("no channels")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.4))
                    Button {
                        showCreate = true
                    } label: {
                        Text("create")
                            .font(.system(size: 11))
                            .foregroundColor(Color.matcha500)
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(channels, id: \.id) { channel in
                            row(for: channel)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .background(Color.appBackground)
        .task {
            await load()
        }
        .sheet(isPresented: $showCreate) {
            CreateChannelSheet { newChannel in
                Task {
                    await load()
                    appState.selectedChannelId = newChannel.id
                }
            }
        }
    }

    private var header: some View {
        HStack(spacing: 0) {
            Text("CHANNELS")
                .font(.system(size: 10, weight: .medium))
                .tracking(0.8)
                .foregroundColor(.white.opacity(0.4))
            Spacer()
            Button {
                showCreate = true
            } label: {
                Text("+")
                    .font(.system(size: 14, weight: .regular))
                    .foregroundColor(.white.opacity(0.4))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private func row(for channel: ChannelSummary) -> some View {
        let selected = appState.selectedChannelId == channel.id
        return Button {
            appState.selectedChannelId = channel.id
            appState.selectedThreadId = nil
            appState.selectedProjectId = nil
            appState.showInbox = false
            appState.showSkills = false
        } label: {
            HStack(alignment: .top, spacing: 0) {
                Rectangle()
                    .fill(selected ? Color.matcha500 : Color.clear)
                    .frame(width: 2)
                HStack(alignment: .top, spacing: 6) {
                    Text("#")
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.4))
                        .frame(width: 12, alignment: .leading)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(channel.name)
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(selected ? 1.0 : 0.85))
                            .lineLimit(1)
                        if let preview = channel.lastMessagePreview, !preview.isEmpty {
                            Text(preview)
                                .font(.system(size: 11))
                                .foregroundColor(.white.opacity(0.4))
                                .lineLimit(1)
                        }
                    }
                    Spacer(minLength: 4)
                    if channel.unreadCount > 0 {
                        Text("•")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(Color.matcha500)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func load() async {
        do {
            let list = try await ChannelsService.shared.listChannels()
            channels = list.sorted {
                ($0.lastMessageAt ?? "") > ($1.lastMessageAt ?? "")
            }
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
}

private struct CreateChannelSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onCreated: (ChannelDetail) -> Void

    @State private var name = ""
    @State private var description = ""
    @State private var visibility = "public"
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("create channel")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))

            VStack(alignment: .leading, spacing: 4) {
                Text("name")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                TextField("", text: $name, prompt: Text("general").foregroundColor(.white.opacity(0.25)))
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.9))
                Divider()
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("description")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                TextField("", text: $description, prompt: Text("optional").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.9))
                    .lineLimit(1...3)
                Divider()
            }

            HStack(spacing: 16) {
                visibilityButton(label: "public")
                visibilityButton(label: "private")
                Spacer()
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.red.opacity(0.8))
            }

            HStack {
                Button {
                    dismiss()
                } label: {
                    Text("cancel")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    Task { await create() }
                } label: {
                    if isSubmitting {
                        Text("creating…")
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.4))
                    } else {
                        Text("create")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(
                                name.trimmingCharacters(in: .whitespaces).isEmpty
                                    ? .white.opacity(0.25)
                                    : Color.matcha500
                            )
                    }
                }
                .buttonStyle(.plain)
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || isSubmitting)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(20)
        .frame(width: 360)
        .background(Color.appBackground)
    }

    private func visibilityButton(label: String) -> some View {
        let active = visibility == label
        return Button {
            visibility = label
        } label: {
            VStack(spacing: 2) {
                Text(label)
                    .font(.system(size: 11))
                    .foregroundColor(active ? Color.matcha500 : .white.opacity(0.5))
                Rectangle()
                    .fill(active ? Color.matcha500 : Color.clear)
                    .frame(height: 1)
            }
        }
        .buttonStyle(.plain)
    }

    private func create() async {
        isSubmitting = true
        errorMessage = nil
        do {
            let channel = try await ChannelsService.shared.createChannel(
                name: name.trimmingCharacters(in: .whitespaces),
                description: description.isEmpty ? nil : description,
                visibility: visibility
            )
            onCreated(channel)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            isSubmitting = false
        }
    }
}
