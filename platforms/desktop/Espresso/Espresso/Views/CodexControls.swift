import SwiftUI

struct CodexAccountControls: View {
    private var codex: CodexResearchCoordinator { .shared }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let email = codex.email {
                Text("Signed in as \(email)\(codex.plan.map { " (\($0))" } ?? "")")
                    .font(.caption).textSelection(.enabled)
                if let limits = codex.limits { Text(limits).font(.caption).foregroundStyle(.secondary) }
                Button("Sign out of ChatGPT") { Task { await codex.signOut() } }.disabled(codex.busy)
            } else if codex.loginID != nil {
                Text("Finish signing in with ChatGPT in your browser.").font(.caption)
                if let code = codex.deviceCode {
                    Text("Device code: \(code)").font(.system(.body, design: .monospaced)).textSelection(.enabled)
                }
                Button("Cancel sign-in") { Task { await codex.cancelLogin() } }.disabled(codex.accountBusy)
            } else {
                HStack {
                    Button("Sign in with ChatGPT") { codex.signIn() }
                    Button("Use a device code") { codex.signIn(device: true) }
                }.disabled(codex.busy)
            }
            if codex.accountBusy { ProgressView().controlSize(.small) }
            if let error = codex.accountError { Text(error).font(.caption).foregroundStyle(.red) }
        }
        .task { await codex.refreshAccount() }
    }
}

struct CodexResearchControls: View {
    let projectID: String
    let taskID: String
    let eligible: Bool
    private var codex: CodexResearchCoordinator { .shared }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if codex.email == nil { CodexAccountControls() }
            if eligible {
                Button("Research with Codex") { codex.startResearch(projectID: projectID, taskID: taskID) }
                    .disabled(codex.busy || codex.email == nil)
                    .help("Research locally using your ChatGPT plan and attach the report to this card")
            }
            if codex.taskID == taskID {
                HStack {
                    if codex.running { ProgressView().controlSize(.small) }
                    Text(codex.progress).font(.caption).textSelection(.enabled)
                    if codex.running { Button("Cancel") { Task { await codex.cancelResearch() } } }
                }
                if !codex.transcript.isEmpty {
                    DisclosureGroup("Research progress") {
                        ScrollView { Text(codex.transcript).font(.caption).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                            .frame(maxHeight: 160)
                    }.font(.caption)
                }
            } else if codex.running {
                Text("Codex is researching another card. Finish or cancel that run first.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}
