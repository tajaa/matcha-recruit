import SwiftUI
import AppKit

// MARK: - Email this note

/// Composer sheet that emails a note as a PDF attachment. Recipients are a
/// mix of project collaborators (toggle list) and free-text addresses. Sends
/// immediately via the backend; no scheduling in v1.
struct NoteEmailComposer: View {
    let projectId: String
    let section: MWProjectSection
    let collaborators: [MWProjectCollaborator]
    var onClose: () -> Void

    @State private var selectedEmails: Set<String> = []
    @State private var extraInput: String = ""
    @State private var extraEmails: [String] = []
    @State private var subject: String = ""
    @State private var message: String = ""
    @State private var sending = false
    @State private var resultText: String? = nil
    @State private var isError = false

    private var allRecipients: [String] {
        // selected collaborator emails + free-text, lowercased + deduped.
        var seen = Set<String>()
        var out: [String] = []
        for e in selectedEmails.map({ $0.lowercased() }) + extraEmails.map({ $0.lowercased() }) {
            if !e.isEmpty && !seen.contains(e) { seen.insert(e); out.append(e) }
        }
        return out
    }

    private func looksLikeEmail(_ s: String) -> Bool {
        let t = s.trimmingCharacters(in: .whitespaces)
        guard let at = t.firstIndex(of: "@"), at != t.startIndex else { return false }
        let domain = t[t.index(after: at)...]
        return domain.contains(".") && !domain.hasSuffix(".")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Email note").font(.system(size: 15, weight: .semibold)).foregroundColor(.white)
                Spacer()
                Button { onClose() } label: {
                    Image(systemName: "xmark").font(.system(size: 12, weight: .semibold)).foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)

            Divider().opacity(0.2)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Collaborators
                    if !collaborators.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("COLLABORATORS").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                            ForEach(collaborators) { c in
                                Button {
                                    if selectedEmails.contains(c.email) { selectedEmails.remove(c.email) }
                                    else { selectedEmails.insert(c.email) }
                                } label: {
                                    HStack(spacing: 8) {
                                        Image(systemName: selectedEmails.contains(c.email) ? "checkmark.circle.fill" : "circle")
                                            .font(.system(size: 13))
                                            .foregroundColor(selectedEmails.contains(c.email) ? .matcha500 : .secondary)
                                        VStack(alignment: .leading, spacing: 1) {
                                            Text(c.name).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                                            Text(c.email).font(.system(size: 10)).foregroundColor(.secondary)
                                        }
                                        Spacer()
                                    }
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    // Free-text recipients
                    VStack(alignment: .leading, spacing: 6) {
                        Text("OTHER RECIPIENTS").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                        if !extraEmails.isEmpty {
                            FlowChips(items: extraEmails) { email in
                                extraEmails.removeAll { $0 == email }
                            }
                        }
                        HStack(spacing: 6) {
                            TextField("name@example.com", text: $extraInput, onCommit: addExtra)
                                .textFieldStyle(.plain)
                                .font(.system(size: 12))
                                .foregroundColor(.white)
                                .padding(.horizontal, 10).padding(.vertical, 7)
                                .background(Color.zinc800).cornerRadius(6)
                            Button("Add", action: addExtra)
                                .buttonStyle(.plain)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.white)
                                .padding(.horizontal, 12).padding(.vertical, 7)
                                .background(looksLikeEmail(extraInput) ? Color.matcha600 : Color.zinc800)
                                .cornerRadius(6)
                                .disabled(!looksLikeEmail(extraInput))
                        }
                    }

                    // Subject
                    VStack(alignment: .leading, spacing: 6) {
                        Text("SUBJECT").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                        TextField(section.title, text: $subject)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12))
                            .foregroundColor(.white)
                            .padding(.horizontal, 10).padding(.vertical, 7)
                            .background(Color.zinc800).cornerRadius(6)
                    }

                    // Cover message
                    VStack(alignment: .leading, spacing: 6) {
                        Text("MESSAGE (OPTIONAL)").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                        TextEditor(text: $message)
                            .font(.system(size: 12))
                            .foregroundColor(.white)
                            .scrollContentBackground(.hidden)
                            .frame(height: 90)
                            .padding(.horizontal, 6).padding(.vertical, 4)
                            .background(Color.zinc800).cornerRadius(6)
                    }

                    HStack(spacing: 6) {
                        Image(systemName: "paperclip").font(.system(size: 10)).foregroundColor(.secondary)
                        Text("“\(section.title)” attached as a PDF").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                }
                .padding(20)
            }

            Divider().opacity(0.2)

            HStack {
                if let resultText {
                    Text(resultText)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(isError ? .red : .matcha500)
                        .lineLimit(2)
                }
                Spacer()
                Button("Cancel") { onClose() }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 12).padding(.vertical, 7)
                Button {
                    Task { await send() }
                } label: {
                    HStack(spacing: 6) {
                        if sending { ProgressView().controlSize(.small) }
                        Image(systemName: "paperplane.fill").font(.system(size: 11))
                        Text("Send").font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 16).padding(.vertical, 7)
                    .background(allRecipients.isEmpty ? Color.zinc800 : Color.matcha600)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(allRecipients.isEmpty || sending)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
        }
        .frame(width: 460, height: 560)
        .background(Color(white: 0.11))
        .onAppear { subject = section.title }
    }

    private func addExtra() {
        let e = extraInput.trimmingCharacters(in: .whitespaces).lowercased()
        guard looksLikeEmail(e), !extraEmails.contains(e) else { return }
        extraEmails.append(e)
        extraInput = ""
    }

    private func send() async {
        guard !allRecipients.isEmpty else { return }
        await MainActor.run { sending = true; resultText = nil }
        let subj = subject.trimmingCharacters(in: .whitespaces)
        let msg = message.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            let res = try await MatchaWorkService.shared.emailProjectSection(
                projectId: projectId,
                sectionId: section.id,
                recipients: allRecipients,
                subject: subj.isEmpty ? nil : subj,
                message: msg.isEmpty ? nil : msg
            )
            await MainActor.run {
                sending = false
                if res.failed.isEmpty {
                    resultText = "Sent to \(res.sent.count) recipient\(res.sent.count == 1 ? "" : "s")"
                    isError = false
                    Task { try? await Task.sleep(for: .seconds(1)); onClose() }
                } else {
                    isError = !res.ok
                    resultText = "Sent \(res.sent.count), failed \(res.failed.count): \(res.failed.joined(separator: ", "))"
                }
            }
        } catch {
            await MainActor.run {
                sending = false
                isError = true
                resultText = error.localizedDescription
            }
        }
    }
}

/// Wrapping chip row for free-text recipient emails with a remove affordance.
private struct FlowChips: View {
    let items: [String]
    var onRemove: (String) -> Void

    var body: some View {
        // Simple wrapping layout; small N so a LazyVGrid-free flow is fine.
        VStack(alignment: .leading, spacing: 4) {
            ForEach(items, id: \.self) { item in
                HStack(spacing: 4) {
                    Text(item).font(.system(size: 11)).foregroundColor(.white)
                    Button { onRemove(item) } label: {
                        Image(systemName: "xmark.circle.fill").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Color.matcha600.opacity(0.25))
                .cornerRadius(10)
            }
        }
    }
}

