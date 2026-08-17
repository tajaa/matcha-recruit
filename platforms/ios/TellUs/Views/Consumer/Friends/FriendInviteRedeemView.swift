import SwiftUI
import VisionKit

struct FriendInviteRedeemView: View {
    @State private var preview: InvitePreview?
    @State private var error: String?
    @State private var redeemed = false
    @State private var enteredToken: String

    init(token: String) {
        _enteredToken = State(initialValue: token)
    }

    var body: some View {
        VStack(spacing: 20) {
            if let preview {
                Avatar(preview.owner, size: .header)
                Text("Add @\(preview.owner.handle ?? preview.owner.display_name)?").font(.interTitle3)
                Button("Add Friend") {
                    Task {
                        do { _ = try await FriendsService.shared.redeemInvite(token: normalizedToken()); redeemed = true }
                        catch { self.error = error.localizedDescription }
                    }
                }
                 .buttonStyle(EmberButtonStyle())
            } else {
                if DataScannerViewController.isSupported && DataScannerViewController.isAvailable {
                    QRScannerView(isActive: true) { code in
                        if case .friendInvite(let scannedToken) = scannedTarget(from: code) {
                            enteredToken = scannedToken
                            Task { await loadPreview() }
                        }
                    }
                    .frame(height: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                TextField("Paste invite code or link", text: $enteredToken)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Load invite") { Task { await loadPreview() } }
            }
            if redeemed { Text("You're friends now.").foregroundStyle(.green) }
            if let error { Text(error).foregroundStyle(.red).font(.interFootnote) }
        }
        .padding()
        .themedScreen()
        .navigationTitle("Friend Invite")
        .task {
            await loadPreview()
        }
    }

    private func loadPreview() async {
        let candidate = enteredToken.trimmingCharacters(in: .whitespacesAndNewlines)
        let parsed: String
        if case .friendInvite(let scannedToken) = scannedTarget(from: candidate) {
            parsed = scannedToken
        } else {
            parsed = candidate
        }
        guard !parsed.isEmpty else { return }
        enteredToken = parsed
        do { preview = try await FriendsService.shared.invitePreview(token: parsed) }
        catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }

    private func normalizedToken() -> String {
        if case .friendInvite(let scannedToken) = scannedTarget(from: enteredToken) {
            return scannedToken
        }
        return enteredToken.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
