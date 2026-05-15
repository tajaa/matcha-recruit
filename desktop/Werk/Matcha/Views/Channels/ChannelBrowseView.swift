import SwiftUI
import AppKit

/// Full-pane "Browse Channels" view. Reached by clicking the Channels
/// section header in the sidebar (or the magnifying-glass action). Replaces
/// the modal `DiscoverChannelsSheet` as the primary discovery surface — the
/// sheet stays available for quick access from the channels menu.
///
/// Surfaces public + paid channels from any tenant the user can join,
/// filterable by category. Joining a free channel selects it as the active
/// channel; subscribing to a paid channel opens Stripe Checkout in the
/// browser and reloads on return.
struct ChannelBrowseView: View {
    @Environment(AppState.self) private var appState

    @State private var query = ""
    @State private var paidOnly = false
    @State private var selectedCategory: ChannelCategory? = nil
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var error: String?
    @State private var actionInFlight: String?
    @State private var searchTask: Task<Void, Never>?
    @State private var waitingForCheckoutChannel: ChannelSummary?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            if waitingForCheckoutChannel != nil {
                checkoutBanner
                Divider().opacity(0.2)
            }
            filters
            categoryChips
            Divider().opacity(0.2)
            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.appBackground)
        .task { await load() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            if waitingForCheckoutChannel != nil {
                Task { await reloadAfterCheckout() }
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 10) {
            Button {
                appState.showChannelBrowse = false
                appState.showHome = true
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)
                    .frame(width: 24, height: 24)
                    .background(Color.zinc800)
                    .cornerRadius(5)
            }
            .buttonStyle(.plain)
            .help("Back to Home")

            Image(systemName: "number")
                .font(.system(size: 18, weight: .medium))
                .foregroundColor(.matcha500)
                .frame(width: 32, height: 32)
                .background(Color.zinc800)
                .cornerRadius(7)
            VStack(alignment: .leading, spacing: 2) {
                Text("Browse Channels")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.primary)
                Text("Discover public channels you can join across the workspace")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Spacer()
            Button {
                appState.channelAdminWizardMode = .create
                appState.showChannelAdminWizard = true
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "plus")
                        .font(.system(size: 10, weight: .semibold))
                    Text("New channel")
                        .font(.system(size: 11, weight: .medium))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.matcha500)
                .foregroundColor(.white)
                .cornerRadius(5)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
    }

    private var checkoutBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.up.right.square")
                .font(.system(size: 11))
                .foregroundColor(.matcha500)
            VStack(alignment: .leading, spacing: 1) {
                Text("Complete payment in your browser")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.primary)
                if let ch = waitingForCheckoutChannel {
                    Text("Subscribing to #\(ch.name). The channel will appear in your sidebar once Stripe confirms the payment.")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
            }
            Spacer()
            Button("Dismiss") { waitingForCheckoutChannel = nil }
                .buttonStyle(.plain)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
        .background(Color.matcha500.opacity(0.10))
    }

    // MARK: - Filters

    private var filters: some View {
        HStack(spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                TextField("Search channels…", text: $query)
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
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
    }

    private var categoryChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                chip(label: "All", isActive: selectedCategory == nil) {
                    selectedCategory = nil
                    Task { await load() }
                }
                ForEach(ChannelCategory.allCases) { cat in
                    chip(label: cat.label, isActive: selectedCategory == cat) {
                        selectedCategory = (selectedCategory == cat) ? nil : cat
                        Task { await load() }
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 8)
        }
    }

    private func chip(label: String, isActive: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 11, weight: isActive ? .semibold : .regular))
                .foregroundColor(isActive ? .white : .secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(isActive ? Color.matcha500 : Color.zinc800)
                .cornerRadius(11)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if isLoading {
            VStack {
                Spacer()
                ProgressView().scaleEffect(0.8)
                Spacer()
            }
        } else if let error {
            VStack {
                Spacer()
                Text(error)
                    .font(.system(size: 12))
                    .foregroundColor(.red)
                Spacer()
            }
        } else if channels.isEmpty {
            VStack(spacing: 8) {
                Spacer()
                Image(systemName: "tray")
                    .font(.system(size: 32))
                    .foregroundColor(.secondary)
                Text(emptyTitle)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Text("Try a different category or clear the filters above.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary.opacity(0.6))
                    .multilineTextAlignment(.center)
                Spacer()
            }
            .padding(.horizontal, 24)
        } else {
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 320, maximum: 420), spacing: 10)], spacing: 10) {
                    ForEach(channels) { channel in
                        row(for: channel)
                    }
                }
                .padding(18)
            }
        }
    }

    private var emptyTitle: String {
        if !query.isEmpty {
            return "No channels match \"\(query)\""
        }
        if let cat = selectedCategory {
            return "No channels in \(cat.label) yet"
        }
        return "No public channels yet"
    }

    private func row(for channel: ChannelSummary) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "number")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.matcha500)
                .frame(width: 30, height: 30)
                .background(Color.zinc800)
                .cornerRadius(6)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(channel.name)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.primary)
                        .lineLimit(1)
                    if let cat = channel.category, let parsed = ChannelCategory(rawValue: cat) {
                        Text(parsed.label)
                            .font(.system(size: 9, weight: .medium))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.white.opacity(0.08))
                            .foregroundColor(.secondary)
                            .cornerRadius(3)
                    }
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
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(3)
                        .multilineTextAlignment(.leading)
                }
                Text("\(channel.memberCount) member\(channel.memberCount == 1 ? "" : "s")")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.7))
            }

            Spacer(minLength: 6)

            actionButton(for: channel)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    @ViewBuilder
    private func actionButton(for channel: ChannelSummary) -> some View {
        let inFlight = actionInFlight == channel.id
        if channel.isPaid {
            Button { Task { await subscribe(channel) } } label: {
                HStack(spacing: 4) {
                    if inFlight {
                        ProgressView().scaleEffect(0.5)
                    } else {
                        Image(systemName: "crown")
                            .font(.system(size: 9))
                        Text("Subscribe")
                            .font(.system(size: 11, weight: .medium))
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.matcha500)
                .foregroundColor(.white)
                .cornerRadius(5)
            }
            .buttonStyle(.plain)
            .disabled(inFlight)
        } else {
            Button { Task { await join(channel) } } label: {
                HStack(spacing: 4) {
                    if inFlight {
                        ProgressView().scaleEffect(0.5)
                    } else {
                        Text("Join")
                            .font(.system(size: 11, weight: .medium))
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.zinc800)
                .foregroundColor(.primary)
                .cornerRadius(5)
            }
            .buttonStyle(.plain)
            .disabled(inFlight)
        }
    }

    // MARK: - Data

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
                paidOnly: paidOnly,
                category: selectedCategory?.rawValue
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
            // Refresh sidebar list and switch to the new channel.
            appState.channelsListGeneration &+= 1
            appState.selectedChannelId = channel.id
            appState.showChannelBrowse = false
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
            waitingForCheckoutChannel = channel
        } catch {
            self.error = (error as NSError).localizedDescription
        }
    }

    private func reloadAfterCheckout() async {
        guard let waiting = waitingForCheckoutChannel else { return }
        await load()
        if !channels.contains(where: { $0.id == waiting.id }) {
            appState.channelsListGeneration &+= 1
            appState.selectedChannelId = waiting.id
            appState.showChannelBrowse = false
            waitingForCheckoutChannel = nil
        }
    }
}
