import SwiftUI
import AppKit

/// Cross-tenant public + paid channel discovery. Personal-account users
/// can find each other's paid channels here — `/channels` only returns
/// channels in your own workspace.
struct DiscoverChannelsSheet: View {
    let onJoined: (String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var paidOnly = false
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var error: String?
    @State private var actionInFlight: String?
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            filters
            Divider().opacity(0.2)
            content
        }
        .frame(width: 520, height: 560)
        .background(Color.appBackground)
        .task { await load() }
    }

    private var header: some View {
        HStack {
            Text("Discover Channels")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.primary)
            Spacer()
            Button("Close") { dismiss() }
                .buttonStyle(.plain)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var filters: some View {
        HStack(spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                TextField("Search public channels…", text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .onChange(of: query) { _, _ in scheduleSearch() }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(Color.zinc800)
            .cornerRadius(6)

            Toggle(isOn: $paidOnly) {
                Text("Paid only")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .toggleStyle(.checkbox)
            .onChange(of: paidOnly) { _, _ in
                Task { await load() }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var content: some View {
        if isLoading {
            VStack {
                Spacer()
                ProgressView().scaleEffect(0.7)
                Spacer()
            }
        } else if let error {
            VStack {
                Spacer()
                Text(error)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                Spacer()
            }
        } else if channels.isEmpty {
            VStack(spacing: 6) {
                Spacer()
                Image(systemName: "tray")
                    .font(.system(size: 28))
                    .foregroundColor(.secondary)
                Text(query.isEmpty
                     ? "No public channels yet."
                     : "No channels match \"\(query)\".")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Text("Public channels created by other users will show up here.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.6))
                    .multilineTextAlignment(.center)
                    .padding(.top, 2)
                Spacer()
            }
            .padding(.horizontal, 24)
        } else {
            ScrollView {
                LazyVStack(spacing: 6) {
                    ForEach(channels) { channel in
                        row(for: channel)
                    }
                }
                .padding(10)
            }
        }
    }

    private func row(for channel: ChannelSummary) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "number")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.matcha500)
                .frame(width: 22, height: 22)
                .background(Color.zinc800)
                .cornerRadius(5)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(channel.name)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.primary)
                    if channel.isPaid, let cents = channel.priceCents {
                        Text("$\(String(format: "%.2f", Double(cents) / 100.0))/mo")
                            .font(.system(size: 9, weight: .medium))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.matcha500.opacity(0.18))
                            .foregroundColor(.matcha500)
                            .cornerRadius(3)
                    }
                }
                if let desc = channel.description, !desc.isEmpty {
                    Text(desc)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                Text("\(channel.memberCount) member\(channel.memberCount == 1 ? "" : "s")")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary.opacity(0.7))
            }

            Spacer()

            actionButton(for: channel)
        }
        .padding(8)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(6)
    }

    @ViewBuilder
    private func actionButton(for channel: ChannelSummary) -> some View {
        let inFlight = actionInFlight == channel.id
        if channel.isPaid {
            Button {
                Task { await subscribe(channel) }
            } label: {
                HStack(spacing: 4) {
                    if inFlight {
                        ProgressView().scaleEffect(0.5)
                    } else {
                        Image(systemName: "crown")
                            .font(.system(size: 9))
                        Text("Subscribe")
                            .font(.system(size: 10, weight: .medium))
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 5)
                .background(Color.matcha500)
                .foregroundColor(.white)
                .cornerRadius(5)
            }
            .buttonStyle(.plain)
            .disabled(inFlight)
        } else {
            Button {
                Task { await join(channel) }
            } label: {
                HStack(spacing: 4) {
                    if inFlight {
                        ProgressView().scaleEffect(0.5)
                    } else {
                        Text("Join")
                            .font(.system(size: 10, weight: .medium))
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.zinc800)
                .foregroundColor(.primary)
                .cornerRadius(5)
            }
            .buttonStyle(.plain)
            .disabled(inFlight)
        }
    }

    private func scheduleSearch() {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 250_000_000)
            if Task.isCancelled { return }
            await load()
        }
    }

    private func load() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            let q = query.trimmingCharacters(in: .whitespaces)
            let list = try await ChannelsService.shared.discoverChannels(
                query: q.isEmpty ? nil : q,
                paidOnly: paidOnly
            )
            channels = list
        } catch {
            self.error = (error as NSError).localizedDescription
        }
    }

    private func join(_ channel: ChannelSummary) async {
        actionInFlight = channel.id
        defer { actionInFlight = nil }
        do {
            try await ChannelsService.shared.joinChannel(id: channel.id)
            onJoined(channel.id)
            dismiss()
        } catch {
            self.error = (error as NSError).localizedDescription
        }
    }

    private func subscribe(_ channel: ChannelSummary) async {
        actionInFlight = channel.id
        defer { actionInFlight = nil }
        do {
            let url = try await ChannelsService.shared.createChannelCheckout(id: channel.id)
            if let nsUrl = URL(string: url) {
                NSWorkspace.shared.open(nsUrl)
            }
            // Don't auto-close — user finishes Stripe Checkout in browser,
            // returns to the app; the activation webhook adds them as a member
            // and the sidebar refresh picks it up on next focus.
        } catch {
            self.error = (error as NSError).localizedDescription
        }
    }
}
