import SwiftUI

struct InboxComposeView: View {
    let currentUserId: String
    let onCreated: (MWInboxConversationDetail) -> Void

    @State private var searchText = ""
    @State private var searchResults: [MWInboxUserSearch] = []
    @State private var selected: [MWInboxUserSearch] = []
    @State private var message = ""
    @State private var isSending = false
    @State private var errorMessage: String?
    @State private var searchTimer: Timer?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("New Message")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.white)

            // Recipients
            VStack(alignment: .leading, spacing: 6) {
                Text("To").font(.system(size: 12, weight: .medium)).foregroundColor(.secondary)

                // Selected chips
                if !selected.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(selected) { user in
                            HStack(spacing: 4) {
                                Text(user.name)
                                    .font(.system(size: 11))
                                    .foregroundColor(.white)
                                Button { selected.removeAll { $0.id == user.id } } label: {
                                    Image(systemName: "xmark").font(.system(size: 8)).foregroundColor(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(.horizontal, 6).padding(.vertical, 3)
                            .background(Color.zinc800)
                            .cornerRadius(4)
                        }
                    }
                }

                TextField("Search by name or email...", text: $searchText)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 12))
                    .onChange(of: searchText) { scheduleSearch() }

                if !searchResults.isEmpty {
                    VStack(spacing: 0) {
                        ForEach(searchResults.filter { u in !selected.contains { $0.id == u.id } }) { user in
                            Button {
                                selected.append(user)
                                searchText = ""
                                searchResults = []
                            } label: {
                                HStack(spacing: 8) {
                                    Circle().fill(Color.matcha500).frame(width: 22, height: 22)
                                        .overlay(Text(String(user.name.prefix(1)).uppercased()).font(.system(size: 9, weight: .bold)).foregroundColor(.white))
                                    VStack(alignment: .leading) {
                                        Text(user.name).font(.system(size: 12)).foregroundColor(.white)
                                        Text(user.email).font(.system(size: 10)).foregroundColor(.secondary)
                                    }
                                    Spacer()
                                }
                                .padding(.horizontal, 8).padding(.vertical, 4)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .background(Color.zinc800.opacity(0.5))
                    .cornerRadius(6)
                }
            }

            // Message
            VStack(alignment: .leading, spacing: 4) {
                Text("Message").font(.system(size: 12, weight: .medium)).foregroundColor(.secondary)
                TextEditor(text: $message)
                    .font(.system(size: 13))
                    .frame(minHeight: 80)
                    .scrollContentBackground(.hidden)
                    .background(Color.zinc800.opacity(0.5))
                    .cornerRadius(6)
            }

            if let err = errorMessage {
                Text(err).font(.system(size: 11)).foregroundColor(.red)
            }

            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                Button {
                    sendMessage()
                } label: {
                    HStack(spacing: 4) {
                        if isSending { ProgressView().controlSize(.mini) }
                        Text("Send")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .disabled(selected.isEmpty || message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
            }
        }
        .padding(24)
        .frame(width: 420)
        .background(Color.appBackground)
    }

    private func sendMessage() {
        isSending = true
        errorMessage = nil
        Task {
            do {
                let convo = try await InboxService.shared.createConversation(
                    participantIds: selected.map(\.id),
                    message: message.trimmingCharacters(in: .whitespacesAndNewlines)
                )
                await MainActor.run { onCreated(convo) }
            } catch {
                await MainActor.run { errorMessage = error.localizedDescription; isSending = false }
            }
        }
    }

    private func scheduleSearch() {
        searchTimer?.invalidate()
        guard searchText.count >= 2 else { searchResults = []; return }
        searchTimer = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: false) { _ in
            Task {
                let results = try? await InboxService.shared.searchUsers(query: searchText)
                await MainActor.run { searchResults = results ?? [] }
            }
        }
    }
}
