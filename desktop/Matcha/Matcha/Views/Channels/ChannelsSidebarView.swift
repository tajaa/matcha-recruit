import SwiftUI

struct ChannelsSidebarView: View {
    @Environment(AppState.self) private var appState
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var showCreate = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Channels")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)
                Spacer()
                Button {
                    showCreate = true
                } label: {
                    Image(systemName: "plus.circle")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            if isLoading {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if channels.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "number")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("No channels")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                    Button("Create channel") { showCreate = true }
                        .buttonStyle(.borderless)
                        .font(.system(size: 12))
                }
                Spacer()
            } else {
                List(channels, id: \.id) { channel in
                    Button {
                        appState.selectedChannelId = channel.id
                        appState.selectedThreadId = nil
                        appState.selectedProjectId = nil
                        appState.showInbox = false
                        appState.showSkills = false
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: channel.isPaid ? "lock" : "number")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(channel.name)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.white)
                                    .lineLimit(1)
                                if let preview = channel.lastMessagePreview {
                                    Text(preview)
                                        .font(.system(size: 10))
                                        .foregroundColor(.secondary)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                            if channel.unreadCount > 0 {
                                Text("\(channel.unreadCount)")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundColor(.white)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(Color.matcha500)
                                    .clipShape(Capsule())
                            }
                        }
                        .padding(.vertical, 2)
                        .background(
                            appState.selectedChannelId == channel.id
                                ? Color.matcha500.opacity(0.15)
                                : Color.clear
                        )
                    }
                    .buttonStyle(.plain)
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
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
        VStack(alignment: .leading, spacing: 12) {
            Text("Create channel")
                .font(.system(size: 16, weight: .semibold))

            TextField("Name", text: $name)
                .textFieldStyle(.roundedBorder)

            TextField("Description (optional)", text: $description, axis: .vertical)
                .lineLimit(2...4)
                .textFieldStyle(.roundedBorder)

            Picker("Visibility", selection: $visibility) {
                Text("Public").tag("public")
                Text("Private").tag("private")
            }
            .pickerStyle(.segmented)

            if let errorMessage {
                Text(errorMessage).font(.system(size: 11)).foregroundColor(.red)
            }

            HStack {
                Button("Cancel") { dismiss() }
                    .buttonStyle(.bordered)
                Spacer()
                Button {
                    Task { await create() }
                } label: {
                    if isSubmitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Create")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || isSubmitting)
            }
        }
        .padding(20)
        .frame(width: 380)
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
