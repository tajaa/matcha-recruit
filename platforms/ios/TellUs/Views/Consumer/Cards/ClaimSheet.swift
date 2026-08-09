import SwiftUI

/// What a scanned promo QR opens: the offer, then the card.
struct ClaimSheet: View {
    let token: String
    @State private var vm: PromoClaimViewModel
    @Environment(\.dismiss) private var dismiss

    init(token: String) {
        self.token = token
        _vm = State(initialValue: PromoClaimViewModel(token: token))
    }

    var body: some View {
        NavigationStack {
            Group {
                switch vm.phase {
                case .loading:
                    ProgressView().tint(TU.ember)
                case .preview(let preview):
                    previewBody(preview)
                case .claimed(let card):
                    CardDetailView(card: card)
                case .unavailable(_, let message):
                    EmptyState(icon: "clock.badge.xmark", title: "Not available", hint: message)
                case .failed(let message):
                    EmptyState(icon: "wifi.exclamationmark", title: "Couldn't load this offer", hint: message)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(TU.ink)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        }
        .task { await vm.load() }
    }

    @ViewBuilder
    private func previewBody(_ preview: PromoClaimPreview) -> some View {
        ScrollView {
            VStack(spacing: 18) {
                // Plain AsyncImage, not AsyncMediaImage — the latter is built
                // around ReportMedia (feedback attachments), and a brand logo
                // is just a public URL.
                if let logo = preview.brand_logo_url, let url = URL(string: logo) {
                    AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                        .frame(width: 64, height: 64)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                }
                Text(preview.brand_name)
                    .font(.subheadline)
                    .foregroundStyle(TU.textDim)
                Text(preview.title)
                    .font(.title2.bold())
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white)
                Text(preview.reward_text)
                    .font(.title3)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(TU.ember)
                if let description = preview.description, !description.isEmpty {
                    Text(description)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(TU.textDim)
                }

                Button {
                    Task { await vm.claim() }
                } label: {
                    if vm.claiming {
                        ProgressView().tint(.black).frame(maxWidth: .infinity)
                    } else {
                        Text("Claim reward").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(TU.ember)
                .foregroundStyle(.black)
                .disabled(vm.claiming)

                Text("One card per person, while they last.")
                    .font(.caption)
                    .foregroundStyle(TU.textDim)
            }
            .padding()
        }
    }
}
