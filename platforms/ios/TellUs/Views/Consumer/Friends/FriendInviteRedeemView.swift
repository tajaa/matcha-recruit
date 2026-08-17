import SwiftUI

struct FriendInviteRedeemView: View {
    let token: String
    @State private var preview: InvitePreview?
    @State private var error: String?
    @State private var redeemed = false

    var body: some View {
        VStack(spacing: 20) {
            if let preview {
                Avatar(preview.owner, size: .header)
                Text("Add @\(preview.owner.handle ?? preview.owner.display_name)?").font(.interTitle3)
                Button("Add Friend") {
                    Task {
                        do { _ = try await FriendsService.shared.redeemInvite(token: token); redeemed = true }
                        catch { self.error = error.localizedDescription }
                    }
                }
                .buttonStyle(EmberButtonStyle())
            } else { ProgressView() }
            if redeemed { Text("You're friends now.").foregroundStyle(.green) }
            if let error { Text(error).foregroundStyle(.red).font(.interFootnote) }
        }
        .padding()
        .themedScreen()
        .navigationTitle("Friend Invite")
        .task {
            do { preview = try await FriendsService.shared.invitePreview(token: token) }
            catch { self.error = error.localizedDescription }
        }
    }
}
