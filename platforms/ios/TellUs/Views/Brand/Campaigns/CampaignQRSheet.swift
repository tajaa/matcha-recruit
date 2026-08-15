import SwiftUI

struct CampaignQRSheet: View {
    let campaign: PromoCampaign
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false

    private var claimURL: String {
        APIClient.shared.webOrigin + campaign.claim_url
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 18) {
                QRCodeView(content: claimURL)
                    .frame(width: 240, height: 240)
                    .padding(18)
                    .background(.white, in: RoundedRectangle(cornerRadius: 18))

                VStack(spacing: 6) {
                    Text(campaign.title)
                        .font(.interHeadline)
                        .multilineTextAlignment(.center)
                    Text(campaign.reward_text)
                        .font(.interSubheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }

                NavigationLink {
                    CampaignDesignerView(campaignID: campaign.id)
                } label: {
                    Label(campaign.has_design ? "Edit flyer design" : "Design flyer", systemImage: "paintbrush")
                }

                if let url = URL(string: claimURL) {
                    ShareLink(item: url) {
                        Label("Share claim link", systemImage: "square.and.arrow.up")
                    }
                }

                Button {
                    UIPasteboard.general.string = claimURL
                    copied = true
                } label: {
                    Label(copied ? "Copied!" : "Copy claim link", systemImage: "doc.on.doc")
                }

                Text(claimURL)
                    .font(.interCaption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .textSelection(.enabled)
            }
            .padding()
            .navigationTitle("Campaign QR")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
