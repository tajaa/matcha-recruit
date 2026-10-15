import SwiftUI
import AppKit

/// Email ▸ Drafts: the person's Gmail drafts on the left, the open one on the
/// right to edit, save, send or delete. A job's "Draft email" lands here.
struct EmailDraftsPane: View {
    @Environment(AppState.self) private var appState
    @Environment(\.workPane) private var pane
    private let vm = EmailDraftsViewModel.shared
    @State private var confirmSend = false
    @State private var confirmDelete = false

    var body: some View {
        Group {
            if pane.isSide {
                if vm.selectedId == nil {
                    list
                } else {
                    VStack(spacing: 0) {
                        HStack {
                            Button { Task { await vm.select(nil) } } label: {
                                Label("Drafts", systemImage: "chevron.left").font(.system(size: 11))
                            }
                            .buttonStyle(.plain)
                            Spacer()
                        }
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        Divider().opacity(0.2)
                        editor
                    }
                }
            } else {
                HSplitView {
                    list.frame(minWidth: 260, idealWidth: 320, maxWidth: 440)
                    editor.frame(minWidth: 400, maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .task { if !vm.loaded { await vm.load() } }
        .alert("Send with parts still in brackets?", isPresented: $confirmSend) {
            Button("Send anyway", role: .destructive) { Task { await vm.send() } }
            Button("Keep editing", role: .cancel) {}
        } message: {
            Text("This draft still has \(vm.placeholders.joined(separator: ", ")). Those were left for you to fill in.")
        }
        .confirmationDialog("Delete this draft?", isPresented: $confirmDelete) {
            Button("Delete", role: .destructive) { Task { await vm.delete() } }
        } message: {
            Text("It's removed from Gmail too.")
        }
    }

    // MARK: List

    private var list: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Drafts").font(.system(size: 13, weight: .semibold)).foregroundColor(appState.themeText)
                Spacer()
                if vm.loading {
                    ProgressView().controlSize(.mini)
                } else {
                    Button { Task { await vm.load() } } label: { Image(systemName: "arrow.clockwise") }
                        .buttonStyle(.plain)
                        .foregroundColor(appState.themeTextSecondary)
                        .help("Refresh")
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
            Divider().opacity(0.2)
            if vm.loaded && vm.drafts.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "doc.text").font(.system(size: 24))
                        .foregroundColor(appState.themeTextSecondary.opacity(0.7))
                    Text("No drafts").font(.system(size: 13, weight: .semibold)).foregroundColor(appState.themeText)
                    Text("Your Gmail drafts show up here. A job's Draft email lands here too, ready to edit and send.")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 240)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(vm.drafts) { draft in row(draft) }
                        if vm.nextPageToken != nil {
                            Button { Task { await vm.loadMore() } } label: {
                                if vm.loadingMore { ProgressView().controlSize(.mini) } else { Text("Load more") }
                            }
                            .buttonStyle(.plain)
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeAccent)
                            .padding(.vertical, 8)
                            .disabled(vm.loadingMore)
                        }
                    }
                    .padding(6)
                }
            }
        }
    }

    private func row(_ draft: EmailDraftSummary) -> some View {
        let selected = vm.selectedId == draft.id
        return Button { Task { await vm.select(draft.id) } } label: {
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(draft.subject.isEmpty ? "(no subject)" : draft.subject)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(appState.themeText)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    if let updated = draft.updated {
                        Text(EmailDates.listLabel(updated))
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                }
                Text(draft.to.isEmpty ? "No recipient yet" : "To: \(draft.to)")
                    .font(.system(size: 11))
                    .foregroundColor(draft.to.isEmpty ? .orange : appState.themeTextSecondary)
                    .lineLimit(1)
                if !draft.snippet.isEmpty {
                    Text(draft.snippet)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10).padding(.vertical, 8)
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(selected ? appState.themeAccent.opacity(0.1) : Color.clear))
        }
        .buttonStyle(.plain)
    }

    // MARK: Editor

    @ViewBuilder
    private var editor: some View {
        if vm.selectedId == nil {
            VStack(spacing: 6) {
                if let notice = vm.notice {
                    Label(notice, systemImage: "checkmark.circle").font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                }
                if let error = vm.errorMessage {
                    Text(error).font(.system(size: 12)).foregroundColor(.orange)
                }
                Text(vm.drafts.isEmpty ? "" : "Pick a draft to edit and send it.")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            @Bindable var vm = vm
            VStack(alignment: .leading, spacing: 0) {
                if !vm.editable { gmailOnly }
                if vm.editable {
                    field("To", text: $vm.to, prompt: "name@example.com")
                } else {
                    shown("To", vm.to)
                }
                if let saved = vm.saved {
                    if !saved.cc.isEmpty { Divider().opacity(0.2); shown("Cc", saved.cc) }
                    if !saved.bcc.isEmpty { Divider().opacity(0.2); shown("Bcc", saved.bcc) }
                }
                Divider().opacity(0.2)
                if vm.editable {
                    field("Subject", text: $vm.subject, prompt: "Subject")
                } else {
                    shown("Subject", vm.subject)
                }
                Divider().opacity(0.2)
                if vm.editable {
                    TextEditor(text: $vm.body)
                        .font(.system(size: 13))
                        .scrollContentBackground(.hidden)
                        .padding(10)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        Text(vm.body)
                            .font(.system(size: 13))
                            .foregroundColor(appState.themeText)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(14)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                Divider().opacity(0.2)
                footer
            }
        }
    }

    /// A draft with an attachment or formatting: saving it here (as plain
    /// text) would lose them, so it's edited in Gmail. Sending is fine: it
    /// goes exactly as Gmail has it.
    private var gmailOnly: some View {
        HStack(spacing: 8) {
            Image(systemName: "paperclip").foregroundColor(appState.themeTextSecondary)
            Text(vm.saved?.hasAttachments == true
                 ? "This draft has an attachment. Edit it in Gmail so nothing is lost; you can still send it from here."
                 : "This draft has formatting. Edit it in Gmail so nothing is lost; you can still send it from here.")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if let url = EmailDraftsViewModel.gmailURL(messageId: vm.saved?.messageId,
                                                       account: EmailViewModel.shared.email) {
                Button("Open in Gmail") { NSWorkspace.shared.open(url) }
                    .controlSize(.small)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
        .background(appState.themeAccent.opacity(0.06))
    }

    private func shown(_ label: String, _ value: String) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 54, alignment: .leading)
            Text(value)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .lineLimit(2)
                .textSelection(.enabled)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
    }

    private func field(_ label: String, text: Binding<String>, prompt: String) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 54, alignment: .leading)
            TextField("", text: text, prompt: Text(prompt))
                .textFieldStyle(.plain)
                .font(.system(size: 12))
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !vm.placeholders.isEmpty {
                Label("Still to fill in: \(vm.placeholders.joined(separator: ", "))", systemImage: "square.and.pencil")
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
                    .lineLimit(2)
            }
            if let error = vm.errorMessage {
                Text(error).font(.system(size: 11)).foregroundColor(.orange).lineLimit(2)
            }
            HStack(spacing: 8) {
                Button(role: .destructive) { confirmDelete = true } label: { Image(systemName: "trash") }
                    .buttonStyle(.plain)
                    .foregroundColor(appState.themeTextSecondary)
                    .help("Delete this draft")
                    .disabled(vm.busy)
                if vm.busy {
                    ProgressView().controlSize(.mini)
                } else if let notice = vm.notice, !vm.isDirty {
                    Text(notice).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                if vm.editable {
                    Button("Save") { Task { await vm.save() } }
                        .keyboardShortcut("s", modifiers: .command)
                        .disabled(!vm.isDirty || vm.busy)
                }
                Button {
                    if vm.placeholders.isEmpty { Task { await vm.send() } } else { confirmSend = true }
                } label: {
                    Label("Send", systemImage: "paperplane.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .disabled(vm.busy || vm.to.trimmingCharacters(in: .whitespaces).isEmpty)
                .help(vm.to.trimmingCharacters(in: .whitespaces).isEmpty ? "Add who it goes to first" : "Send it from your Gmail")
            }
            .font(.system(size: 12))
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
    }
}
