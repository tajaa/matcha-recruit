import SwiftUI

struct LinkQRSheet: View {
    let link: FeedbackLink
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false

    private var url: String {
        APIClient.shared.webOrigin + "/tellus/i/" + link.token
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                if let target = URL(string: url) {
                    QRCodeView(content: url)
                        .frame(width: 220, height: 220)
                    ShareLink(item: target) {
                        Label("Share", systemImage: "square.and.arrow.up")
                    }
                }
                Button {
                    UIPasteboard.general.string = url
                    copied = true
                } label: {
                    Label(copied ? "Copied!" : "Copy link", systemImage: "doc.on.doc")
                }
                Text(url).font(.interCaption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
            .padding()
            .navigationTitle(link.label ?? "Feedback link")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
        }
        .presentationDetents([.medium])
    }
}
