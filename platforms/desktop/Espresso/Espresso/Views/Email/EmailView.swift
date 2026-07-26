import SwiftUI

// MARK: - Sidebar section content

/// Rendered inside the collapsible "Email" sidebar section. Shows a connect
/// prompt when no Gmail is linked, otherwise the unread list. Tapping a row
/// routes the primary detail pane to `EmailDetailView` via `selectedEmailId`.
struct EmailSidebarView: View {
    let searchText: String
    @Environment(AppState.self) private var appState
    private let vm = EmailViewModel.shared

    private var filtered: [EmailMessage] {
        guard !searchText.isEmpty else { return vm.emails }
        let q = searchText.lowercased()
        return vm.emails.filter {
            $0.subject.lowercased().contains(q) || $0.fromAddress.lowercased().contains(q)
        }
    }

    var body: some View {
        VStack(spacing: 2) {
            if !vm.connected {
                connectRow
            } else {
                if vm.isLoading && vm.emails.isEmpty {
                    infoRow(icon: "arrow.triangle.2.circlepath", text: "Loading…")
                } else if filtered.isEmpty {
                    infoRow(icon: "tray", text: searchText.isEmpty ? "No unread mail" : "No matches")
                } else {
                    ForEach(filtered) { msg in emailRow(msg) }
                }
                connectedFooter
            }

            if let err = vm.errorMessage {
                Text(err)
                    .font(.system(size: 10))
                    .foregroundColor(.red.opacity(0.85))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 3)
            }
        }
        .padding(.bottom, 6)
        .task { await vm.loadStatus() }
    }

    // MARK: rows

    private var connectRow: some View {
        Button {
            Task { await vm.connect() }
        } label: {
            HStack(spacing: 8) {
                if vm.isConnecting {
                    ProgressView().controlSize(.small)
                    Text("Connecting…")
                } else {
                    Image(systemName: "envelope.badge")
                        .font(.system(size: 12))
                    Text("Connect Gmail")
                }
                Spacer()
            }
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(appState.themeAccent)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(vm.isConnecting)
    }

    private func emailRow(_ msg: EmailMessage) -> some View {
        let isSelected = appState.selectedEmailId == msg.id
        return Button {
            selectEmail(msg.id)
        } label: {
            VStack(alignment: .leading, spacing: 1) {
                Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Text(msg.fromAddress)
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(isSelected ? appState.themeAccent.opacity(0.14) : Color.clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 4)
    }

    private func infoRow(icon: String, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon).font(.system(size: 10))
            Text(text).font(.system(size: 11))
            Spacer()
        }
        .foregroundColor(appState.themeTextSecondary)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private var connectedFooter: some View {
        HStack(spacing: 6) {
            Image(systemName: "checkmark.seal")
                .font(.system(size: 9))
                .foregroundColor(appState.themeAccent)
            Text(vm.email ?? "Connected")
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
                .lineLimit(1)
            Spacer()
            Menu {
                Button("Refresh") { Task { await vm.loadInbox() } }
                Divider()
                Button("Disconnect", role: .destructive) { Task { await vm.disconnect() } }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)
                    .frame(width: 18, height: 18)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Email account options")
        }
        .padding(.horizontal, 12)
        .padding(.top, 4)
    }

    private func selectEmail(_ id: String) {
        appState.selectedEmailId = id
        appState.selectedThreadId = nil
        appState.selectedProjectId = nil
        appState.selectedChannelId = nil
        appState.selectedJournalId = nil
        appState.showInbox = false
        appState.showPeople = false
        appState.showHome = false
        appState.showChannelBrowse = false
        appState.showSkills = false
        appState.showArchive = false
    }
}

// MARK: - Detail pane

/// Read-only viewer for one unread message. Resolves the message from the
/// shared view model's loaded list (the fetch payload already carries the body).
struct EmailDetailView: View {
    let emailId: String
    @Environment(AppState.self) private var appState
    private let vm = EmailViewModel.shared

    var body: some View {
        Group {
            if let msg = vm.message(id: emailId) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                            .font(.system(size: 18, weight: .bold))
                            .foregroundColor(appState.themeText)
                            .textSelection(.enabled)

                        HStack(alignment: .firstTextBaseline) {
                            Text(msg.fromAddress)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(appState.themeTextSecondary)
                            Spacer()
                            Text(msg.date)
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeTextSecondary)
                        }

                        Divider().background(appState.themeBorder)

                        Text(msg.body)
                            .font(.system(size: 13))
                            .foregroundColor(appState.themeText)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(24)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .background(appState.themeBg)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "envelope.open")
                        .font(.system(size: 28))
                        .foregroundColor(appState.themeTextSecondary)
                    Text("Select an email")
                        .font(.system(size: 13))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(appState.themeBg)
            }
        }
    }
}
