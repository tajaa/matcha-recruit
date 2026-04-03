import SwiftUI
import AuthenticationServices

struct AgentPanelView: View {
    @State private var status: MWAgentEmailStatus?
    @State private var emails: [MWAgentEmail] = []
    @State private var selectedEmail: MWAgentEmail?
    @State private var draftInstructions = ""
    @State private var draftContent = ""
    @State private var isConnecting = false
    @State private var isFetching = false
    @State private var isDrafting = false
    @State private var isSending = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    private let service = MatchaWorkService.shared

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Email Agent")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                if status?.connected == true {
                    Circle().fill(Color.green).frame(width: 8, height: 8)
                    Text(status?.email ?? "Connected")
                        .font(.system(size: 10)).foregroundColor(.secondary)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider().opacity(0.3)

            if status?.connected != true {
                // Connect button
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "envelope.badge").font(.system(size: 36)).foregroundColor(.secondary)
                    Text("Connect Gmail to get started")
                        .font(.system(size: 13)).foregroundColor(.secondary)
                    Button {
                        Task { await connectGmail() }
                    } label: {
                        HStack(spacing: 4) {
                            if isConnecting { ProgressView().controlSize(.mini) }
                            Text("Connect Gmail")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .disabled(isConnecting)
                }
                Spacer()
            } else {
                // Toolbar
                HStack(spacing: 8) {
                    Button {
                        Task { await fetchEmails() }
                    } label: {
                        HStack(spacing: 4) {
                            if isFetching { ProgressView().controlSize(.mini) }
                            Text("Fetch Emails").font(.system(size: 11))
                        }
                    }
                    .buttonStyle(.plain).foregroundColor(.matcha500)
                    .disabled(isFetching)

                    Spacer()

                    Button("Disconnect") {
                        Task { await disconnect() }
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.red.opacity(0.7))
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 6)

                Divider().opacity(0.3)

                // Email list + detail
                HSplitView {
                    // Email list
                    ScrollView {
                        LazyVStack(spacing: 1) {
                            ForEach(emails) { email in
                                Button {
                                    selectedEmail = email
                                    draftContent = ""
                                    draftInstructions = ""
                                } label: {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(email.subject ?? "(no subject)")
                                            .font(.system(size: 12, weight: selectedEmail?.id == email.id ? .semibold : .regular))
                                            .foregroundColor(.white)
                                            .lineLimit(1)
                                        Text(email.from ?? "")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                            .lineLimit(1)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(selectedEmail?.id == email.id ? Color.matcha600.opacity(0.15) : Color.clear)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    .frame(minWidth: 180)

                    // Detail / reply
                    if let email = selectedEmail {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(email.subject ?? "").font(.system(size: 14, weight: .semibold)).foregroundColor(.white)
                            Text("From: \(email.from ?? "")").font(.system(size: 11)).foregroundColor(.secondary)
                            ScrollView {
                                Text(email.body ?? "").font(.system(size: 12)).foregroundColor(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .frame(maxHeight: 150)

                            Divider().opacity(0.3)

                            // Draft reply
                            TextField("Instructions for AI reply...", text: $draftInstructions)
                                .textFieldStyle(.roundedBorder)
                                .font(.system(size: 12))

                            Button {
                                Task { await draftReply(emailId: email.id) }
                            } label: {
                                HStack(spacing: 4) {
                                    if isDrafting { ProgressView().controlSize(.mini) }
                                    Text("Draft Reply")
                                }
                            }
                            .buttonStyle(.borderedProminent).tint(Color.matcha600).controlSize(.small)
                            .disabled(draftInstructions.isEmpty || isDrafting)

                            if !draftContent.isEmpty {
                                TextEditor(text: $draftContent)
                                    .font(.system(size: 12))
                                    .frame(minHeight: 80)
                                    .scrollContentBackground(.hidden)
                                    .background(Color.zinc800.opacity(0.5))
                                    .cornerRadius(6)

                                Button {
                                    Task { await sendReply(email: email) }
                                } label: {
                                    HStack(spacing: 4) {
                                        if isSending { ProgressView().controlSize(.mini) }
                                        Text("Send")
                                    }
                                }
                                .buttonStyle(.borderedProminent).tint(Color.matcha600).controlSize(.small)
                                .disabled(draftContent.isEmpty || isSending)
                            }
                        }
                        .padding(12)
                    } else {
                        ZStack {
                            Color.clear
                            Text("Select an email").font(.system(size: 12)).foregroundColor(.secondary)
                        }
                    }
                }
            }

            if let msg = successMessage {
                Text(msg).font(.system(size: 11)).foregroundColor(.matcha500)
                    .padding(.horizontal, 16).padding(.vertical, 4)
            }
            if let err = errorMessage {
                Text(err).font(.system(size: 11)).foregroundColor(.red)
                    .padding(.horizontal, 16).padding(.vertical, 4)
            }
        }
        .background(Color.zinc900)
        .task { await loadStatus() }
    }

    private func loadStatus() async {
        do {
            let s = try await service.agentEmailStatus()
            await MainActor.run { status = s }
        } catch { }
    }

    private func connectGmail() async {
        isConnecting = true
        do {
            let authUrl = try await service.agentConnectGmail()
            if let url = URL(string: authUrl) {
                await MainActor.run { NSWorkspace.shared.open(url) }
            }
            // Poll status after a delay
            try? await Task.sleep(for: .seconds(5))
            await loadStatus()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
        await MainActor.run { isConnecting = false }
    }

    private func disconnect() async {
        do {
            try await service.agentDisconnectGmail()
            await MainActor.run { status = nil; emails = []; selectedEmail = nil }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    private func fetchEmails() async {
        isFetching = true
        do {
            let fetched = try await service.agentFetchEmails()
            await MainActor.run { emails = fetched; isFetching = false }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription; isFetching = false }
        }
    }

    private func draftReply(emailId: String) async {
        isDrafting = true
        do {
            let draft = try await service.agentDraftReply(emailId: emailId, instructions: draftInstructions)
            await MainActor.run { draftContent = draft; isDrafting = false }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription; isDrafting = false }
        }
    }

    private func sendReply(email: MWAgentEmail) async {
        isSending = true
        do {
            let subject = "Re: \(email.subject ?? "")"
            try await service.agentSendEmail(to: email.from ?? "", subject: subject, body: draftContent, replyToId: email.id)
            await MainActor.run { successMessage = "Sent!"; draftContent = ""; isSending = false }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription; isSending = false }
        }
    }
}
