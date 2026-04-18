import SwiftUI

private let threadListOutputFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    return formatter
}()

private func formatThreadDate(_ iso: String) -> String {
    guard let date = parseMWDate(iso) else { return iso }
    return threadListOutputFormatter.string(from: date)
}

struct ThreadListView: View {
    @Environment(AppState.self) private var appState
    @Bindable var viewModel: ThreadListViewModel
    var showHeader: Bool = true
    @State private var isCreating = false
    @State private var threadToDelete: MWThread?
    @State private var showDeleteConfirm = false

    let filterOptions = [
        (label: "All", value: Optional<String>.none),
        (label: "Active", value: Optional<String>.some("active")),
        (label: "Finalized", value: Optional<String>.some("finalized")),
        (label: "Archived", value: Optional<String>.some("archived"))
    ]

    var body: some View {
        @Bindable var appState = appState

        VStack(spacing: 0) {
            if showHeader {
                // Header
                HStack {
                    Text("Matcha Work")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.secondary)

                    // Online users
                    if !appState.onlineUsers.isEmpty {
                        HStack(spacing: -4) {
                            ForEach(appState.onlineUsers.prefix(5)) { user in
                                Circle()
                                    .fill(Color.matcha500)
                                    .frame(width: 18, height: 18)
                                    .overlay(
                                        Text(String(user.name.prefix(1)).uppercased())
                                            .font(.system(size: 8, weight: .bold))
                                            .foregroundColor(.white)
                                    )
                                    .overlay(
                                        Circle().stroke(Color.appBackground, lineWidth: 1.5)
                                    )
                                    .help(user.name)
                            }
                            if appState.onlineUsers.count > 5 {
                                Circle()
                                    .fill(Color.zinc800)
                                    .frame(width: 18, height: 18)
                                    .overlay(
                                        Text("+\(appState.onlineUsers.count - 5)")
                                            .font(.system(size: 7, weight: .bold))
                                            .foregroundColor(.secondary)
                                    )
                                    .overlay(
                                        Circle().stroke(Color.appBackground, lineWidth: 1.5)
                                    )
                            }
                        }
                    }

                    Spacer()
                    Button {
                        createNewThread()
                    } label: {
                        if isCreating {
                            ProgressView()
                                .controlSize(.mini)
                                .frame(width: 24, height: 24)
                        } else {
                            Image(systemName: "plus")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                                .frame(width: 24, height: 24)
                                .background(Color.zinc800)
                                .cornerRadius(6)
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(isCreating)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)

                Divider().opacity(0.3)
            }

            // Filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(filterOptions, id: \.label) { option in
                        Button {
                            viewModel.filterStatus = option.value
                            Task { await viewModel.loadThreads() }
                        } label: {
                            Text(option.label)
                                .font(.system(size: 11, weight: .medium))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(viewModel.filterStatus == option.value ? Color.matcha600 : Color.zinc800)
                                .foregroundColor(viewModel.filterStatus == option.value ? .white : .secondary)
                                .cornerRadius(5)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }

            Divider().opacity(0.3)

            // Thread list
            if viewModel.isLoading {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if viewModel.filteredThreads.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "bubble.left")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text("No threads yet")
                        .foregroundColor(.secondary)
                        .font(.system(size: 13))
                }
                Spacer()
            } else {
                List(viewModel.filteredThreads, selection: $appState.selectedThreadId) { thread in
                    ThreadRowView(thread: thread, onDelete: {
                        threadToDelete = thread
                        showDeleteConfirm = true
                    })
                    .tag(thread.id)
                    .contextMenu {
                        Button(thread.isPinned ? "Unpin" : "Pin") {
                            Task { await viewModel.togglePin(thread: thread) }
                        }
                        if thread.status != "archived" {
                            Button("Archive") {
                                Task { await viewModel.archiveThread(thread: thread) }
                            }
                        }
                        Divider()
                        Button("Delete", role: .destructive) {
                            threadToDelete = thread
                            showDeleteConfirm = true
                        }
                    }
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
                .background(Color.appBackground)
            }
        }
        .background(Color.appBackground)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                Divider().opacity(0.3)
                Button {
                    appState.selectedThreadId = nil
                    appState.showSkills = true
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "bolt.fill")
                            .font(.system(size: 12))
                            .foregroundColor(appState.showSkills ? .matcha500 : .secondary)
                        Text("Skills")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(appState.showSkills ? .white : .secondary)
                        Spacer()
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(appState.showSkills ? Color.matcha600.opacity(0.15) : Color.clear)
                }
                .buttonStyle(.plain)
            }
        }
        .task { await viewModel.loadThreads() }
        .onReceive(NotificationCenter.default.publisher(for: .mwCreateNewThread)) { _ in
            createNewThread()
        }
        .confirmationDialog("Delete thread?", isPresented: $showDeleteConfirm) {
            Button("Delete", role: .destructive) {
                if let thread = threadToDelete {
                    if appState.selectedThreadId == thread.id {
                        appState.selectedThreadId = nil
                    }
                    Task { await viewModel.deleteThread(thread: thread) }
                }
            }
        } message: {
            Text("This cannot be undone.")
        }
    }

    private func createNewThread() {
        guard !isCreating else { return }
        isCreating = true
        let dateStr = Date().formatted(date: .abbreviated, time: .omitted)
        Task {
            if let thread = await viewModel.createThread(
                title: "New Chat \(dateStr)",
                initialMessage: nil
            ) {
                await MainActor.run {
                    appState.selectedThreadId = thread.id
                    appState.showSkills = false
                }
            }
            isCreating = false
        }
    }
}

extension Notification.Name {
    static let mwCreateNewThread = Notification.Name("mwCreateNewThread")
    static let mwProjectDataChanged = Notification.Name("mwProjectDataChanged")
}

struct ThreadRowView: View {
    let thread: MWThread
    let onDelete: () -> Void
    @State private var isHovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top) {
                Text(thread.title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Spacer()
                if isHovered {
                    Button(action: onDelete) {
                        Image(systemName: "trash")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                } else if thread.isPinned {
                    Image(systemName: "pin.fill")
                        .font(.system(size: 9))
                        .foregroundColor(.matcha500)
                }
            }
            HStack(spacing: 4) {
                Text("\(thread.resolvedTaskType.label) · v\(thread.version) · \(formatThreadDate(thread.lastActivityAt))")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                if thread.nodeMode {
                    Text("Node")
                        .font(.system(size: 8, weight: .medium))
                        .foregroundColor(.purple)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.purple.opacity(0.15))
                        .cornerRadius(3)
                }
                if thread.complianceMode {
                    Text("Compliance")
                        .font(.system(size: 8, weight: .medium))
                        .foregroundColor(.cyan)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.cyan.opacity(0.15))
                        .cornerRadius(3)
                }
                if thread.payerMode {
                    Text("Payer")
                        .font(.system(size: 8, weight: .medium))
                        .foregroundColor(.green)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.green.opacity(0.15))
                        .cornerRadius(3)
                }
            }
        }
        .padding(.vertical, 2)
        .onHover { isHovered = $0 }
    }
}
