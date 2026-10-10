import SwiftUI

/// Huume, the schedule assistant, for one store's week. It reads the week and
/// stages changes; nothing changes until the manager confirms.
struct HuumeChatView: View {
    @Environment(\.dismiss) private var dismiss
    let location: ManagedLocation
    let weekStart: Date
    /// The week behind the chat changed (a confirmed action went through).
    let onScheduleChanged: () async -> Void
    @State private var session: HuumeSession?
    @State private var messages: [HuumeMessage] = []
    @State private var state = HuumeState()
    @State private var draft = ""
    @State private var streaming = false
    @State private var status: String?
    @State private var error: String?
    @FocusState private var composing: Bool

    private var weekLabel: String {
        let end = WallClock.move(weekStart, by: 1).addingTimeInterval(-86_400)
        return "\(WallClock.format(weekStart, "MMM d")) – \(WallClock.format(end, "MMM d"))"
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if session == nil && error == nil {
                        HStack { ProgressView(); Text("Opening Huume").foregroundStyle(Color.secondary) }
                            .padding(.top, 24)
                    } else if messages.isEmpty {
                        intro
                    }
                    ForEach(messages) { message in
                        Bubble(message: message).id(message.id)
                    }
                    if streaming {
                        Label(status ?? "Thinking…", systemImage: "sparkles")
                            .font(.app(.subheadline))
                            .foregroundStyle(Color.secondary)
                            .symbolEffect(.pulse)
                            .id("status")
                    }
                    if let error {
                        ErrorRow(message: error)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(16)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: messages.count) { _, _ in withAnimation { proxy.scrollTo("bottom") } }
            .onChange(of: streaming) { _, _ in withAnimation { proxy.scrollTo("bottom") } }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 10) {
                if let action = state.action, action.awaitingConfirmation {
                    actionCard(action)
                }
                if let choice = state.choice, !streaming {
                    choices(choice)
                }
                composer
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.bar)
        }
        .background { AppBackdrop() }
        .navigationTitle("Huume")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                VStack(spacing: 0) {
                    Text("Huume").font(.app(.headline))
                    Text("\(location.displayName) · \(weekLabel)").font(.app(.caption)).foregroundStyle(Color.secondary)
                }
            }
            ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } }
        }
        .task { await open() }
    }

    private var intro: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Ask about this week, or ask for a change.")
                .font(.app(.headline))
            ForEach(["Who's working Saturday?", "Fill the open shifts", "Who's close to overtime?"], id: \.self) { example in
                Button(example) { draft = example; composing = true }
                    .buttonStyle(.bordered)
                    .font(.app(.subheadline))
            }
            Text("Huume stages changes for you to confirm. Nothing changes until you do.")
                .font(.app(.footnote)).foregroundStyle(Color.secondary)
        }
        .padding(.top, 16)
    }

    private func actionCard(_ action: HuumeAction) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(action.question, systemImage: "checkmark.seal")
                .font(.app(.subheadline, .semibold))
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 10) {
                Button { Task { await send("confirm") } } label: {
                    LoadingLabel(title: "Confirm", busy: false)
                }
                .prominentGlassButton()
                .buttonBorderShape(.capsule)
                .accessibilityIdentifier("huume.confirm")
                Button { Task { await send("cancel") } } label: {
                    Text("Cancel").frame(maxWidth: .infinity)
                }
                .glassButton()
                .buttonBorderShape(.capsule)
            }
            .disabled(streaming)
        }
        .padding(14)
        .glassPanel(in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private func choices(_ choice: HuumeChoice) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(choice.question).font(.app(.subheadline)).foregroundStyle(Color.secondary)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(choice.options, id: \.label) { option in
                        Button(option.label) { Task { await send(option.send ?? option.label) } }
                            .buttonStyle(.bordered)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Ask Huume", text: $draft, axis: .vertical)
                .lineLimit(1...5)
                .focused($composing)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .glassPanel(in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .accessibilityIdentifier("huume.input")
            Button {
                let text = draft
                draft = ""
                Task { await send(text) }
            } label: {
                Image(systemName: "arrow.up.circle.fill").font(.system(size: 34))
            }
            .disabled(streaming || session == nil || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .accessibilityLabel("Send")
        }
    }

    private func open() async {
        error = nil
        do {
            let opened = try await HuumeService.openSession(location: location.id, weekStart: weekStart)
            session = opened
            messages = opened.messages
            state = opened.current_state
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    private func send(_ raw: String) async {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let session, !text.isEmpty, !streaming else { return }
        streaming = true
        status = nil
        error = nil
        let pending = HuumeMessage(id: "pending-\(UUID().uuidString)", role: "user", content: text, created_at: nil)
        messages.append(pending)
        var completed = false
        var provisionalError: String?
        do {
            for try await event in HuumeService.send(text, threadID: session.thread_id) {
                switch event {
                case .status(let message): status = message
                case .step(let label): if let label { status = label }
                case .error(let message): provisionalError = message
                case .complete(let user, let assistant, let newState):
                    completed = true
                    messages.removeAll { $0.id == pending.id }
                    if let user { messages.append(user) } else { messages.append(pending) }
                    if let assistant { messages.append(assistant) }
                    let before = state.action
                    if let newState { state = newState }
                    if let action = state.action, action.changedSchedule, action != before {
                        await onScheduleChanged()
                    }
                case .done: break
                }
            }
            if !completed {
                error = provisionalError ?? "The reply stopped before Huume finished. Try again."
            }
        } catch {
            if !error.isCancellation {
                self.error = (error as? URLError)?.code == .timedOut
                    ? "Huume took too long to answer. Try again."
                    : error.localizedDescription
            }
        }
        streaming = false
        status = nil
    }
}

private struct Bubble: View {
    let message: HuumeMessage

    private var text: AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: message.content, options: options)) ?? AttributedString(message.content)
    }

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 48) }
            Text(text)
                .font(.app(.body))
                .foregroundStyle(message.isUser ? Color(.systemBackground) : Color.primary)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background {
                    if message.isUser {
                        RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.primary)
                    } else {
                        CardFill()
                    }
                }
                .textSelection(.enabled)
            if !message.isUser { Spacer(minLength: 48) }
        }
    }
}
