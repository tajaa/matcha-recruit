import SwiftUI

struct NewConversationView: View {
    @Environment(\.dismiss) private var dismiss
    let onCreated: (String) async -> Void
    @State private var query = ""
    @State private var results: [MWInboxUserSearch] = []
    @State private var selected: MWInboxUserSearch?
    @State private var draft = ""
    @State private var creating = false
    @State private var searching = false
    @State private var error: String?
    @FocusState private var searchFocused: Bool
    @FocusState private var draftFocused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let selected {
                        compose(to: selected)
                    } else {
                        search
                    }
                }
                .padding(.horizontal, Metrics.gutter)
                .padding(.top, 8)
                .padding(.bottom, 24)
                .animation(.spring(response: 0.4, dampingFraction: 0.86), value: selected?.id)
            }
            .scrollDismissesKeyboard(.interactively)
            .ambientBackground()
            .navigationTitle(selected == nil ? "New message" : "Message")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: { Text("Cancel").font(TypeScale.callout) }
                }
                if selected != nil {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { selected = nil } label: { Image(systemName: "chevron.left") }
                            .accessibilityLabel("Back to people")
                    }
                }
            }
        }
    }

    private var search: some View {
        VStack(alignment: .leading, spacing: 14) {
            GlassField(icon: "magnifyingglass", focused: searchFocused) {
                TextField("Search coworkers by name or email", text: $query)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($searchFocused)
            }
            .task(id: query) { await runSearch() }
            .onAppear { searchFocused = true }
            if let error { ErrorBanner(message: error) }
            if searching && results.isEmpty {
                HStack { Spacer(); ProgressView(); Spacer() }.padding(.top, 20)
            } else if query.trimmingCharacters(in: .whitespaces).count >= 2 && results.isEmpty {
                QuietNote(symbol: "person.crop.circle.badge.questionmark",
                          text: "No one at your company matches \u{201C}\(query)\u{201D}.")
            } else if !results.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(results.enumerated()), id: \.element.id) { index, person in
                        Button { selected = person; draftFocused = true } label: {
                            HStack(spacing: 12) {
                                Avatar(name: person.name, size: 40)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(person.name).font(TypeScale.headline).foregroundStyle(Palette.ink)
                                    Text(person.email).font(TypeScale.caption).foregroundStyle(Palette.inkSoft)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 12, weight: .semibold)).foregroundStyle(Palette.inkFaint)
                            }
                            .padding(.vertical, 10)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(PressableStyle())
                        if index < results.count - 1 { Divider().overlay(Palette.inkFaint.opacity(0.3)).padding(.leading, 52) }
                    }
                }
                .padding(.horizontal, 14)
                .glassSurface()
            } else {
                QuietNote(symbol: "sparkle.magnifyingglass", text: "Type at least two letters of a name.")
            }
        }
    }

    private func compose(to person: MWInboxUserSearch) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Avatar(name: person.name, size: 44)
                VStack(alignment: .leading, spacing: 2) {
                    Eyebrow("To")
                    Text(person.name).font(TypeScale.headline).foregroundStyle(Palette.ink)
                }
                Spacer()
            }
            .padding(14)
            .glassSurface(elevated: false)
            TextField("Write a message", text: $draft, axis: .vertical)
                .font(TypeScale.body)
                .lineLimit(4...10)
                .focused($draftFocused)
                .padding(16)
                .glassSurface(cornerRadius: 18, elevated: false)
            if let error { ErrorBanner(message: error) }
            Button { Task { await create(with: person) } } label: {
                LoadingLabel(title: "Send", busy: creating)
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(creating || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .transition(.move(edge: .trailing).combined(with: .opacity))
    }

    private func runSearch() async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else { results = []; return }
        do { try await Task.sleep(for: .milliseconds(250)) }
        catch { return }
        guard !Task.isCancelled else { return }
        searching = true
        defer { searching = false }
        do {
            results = try await InboxService.shared.searchUsers(trimmed)
            error = nil
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    private func create(with person: MWInboxUserSearch) async {
        creating = true
        defer { creating = false }
        do {
            let conversation = try await InboxService.shared.createConversation(
                with: person.id, message: draft.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            await onCreated(conversation.id)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
