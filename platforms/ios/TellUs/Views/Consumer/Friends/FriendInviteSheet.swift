import SwiftUI
import UIKit

struct FriendInviteSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var invite: FriendInvite?
    @State private var error: String?

    var body: some View {
        VStack(spacing: 16) {
            if let invite {
                QRCodeView(content: APIClient.shared.webOrigin + invite.share_url)
                    .padding(14).background(.white, in: RoundedRectangle(cornerRadius: 12))
                    .frame(width: 220, height: 220)
                ShareLink(item: APIClient.shared.webOrigin + invite.share_url) { Label("Share invite", systemImage: "square.and.arrow.up") }
                Button("Copy code") { UIPasteboard.general.string = invite.token }
            } else { ProgressView() }
            if let error { Text(error).foregroundStyle(.red).font(.interFootnote) }
        }
        .padding().presentationDetents([.height(420)])
        .task { do { invite = try await FriendsService.shared.invite() } catch { self.error = error.localizedDescription } }
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
    }
}
