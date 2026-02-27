import SwiftUI

struct ThreadListView: View {
    @Environment(AppState.self) private var appState
    @Bindable var viewModel: ThreadListViewModel
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
            // Header
            HStack {
                Text("Matcha Work")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.secondary)
                Spacer()
                Button {
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

            // Filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(filterOptions, id: \.label) { option in
                        Button {
                            viewModel.filterStatus = option.value
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
        .confirmationDialog("Delete thread?", isPresented: $showDeleteConfirm) {
            Button("Delete", role: .destructive) {
                if let thread = threadToDelete {
                    Task { await viewModel.deleteThread(thread: thread) }
                }
            }
        } message: {
            Text("This cannot be undone.")
        }
    }
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
            HStack(spacing: 6) {
                Spacer()
                Text("v\(thread.version)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 2)
        .onHover { isHovered = $0 }
    }
}
