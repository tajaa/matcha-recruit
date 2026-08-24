import SwiftUI

/// Consumer claim surface for a radar offer. It intentionally remains a
/// separate view from the older QR campaign claim sheet because the offer has
/// a store destination and a typed-code fallback.
struct ShoutoutOfferView: View {
    private let token: String?
    private let code: String?
    @State private var vm: ShoutoutOfferViewModel
    @Environment(\.dismiss) private var dismiss

    init(token: String) {
        self.token = token
        self.code = nil
        _vm = State(initialValue: ShoutoutOfferViewModel(token: token))
    }

    init(code: String) {
        self.token = nil
        self.code = code
        _vm = State(initialValue: ShoutoutOfferViewModel(code: code))
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
                case .unavailable:
                    EmptyState(icon: "clock.badge.xmark", title: "Offer unavailable", hint: "This offer has expired, been revoked, or was already claimed.")
                case .failed(let message):
                    EmptyState(icon: "wifi.exclamationmark", title: "Couldn't load this offer", hint: message)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(TU.ink)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
            .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        }
        .task { await vm.load() }
    }

    @ViewBuilder
    private func previewBody(_ preview: ShoutoutOfferPreview) -> some View {
        ScrollView {
            VStack(spacing: 18) {
                if let logo = preview.brand_logo_url, let url = URL(string: logo) {
                    AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                        .frame(width: 64, height: 64).clipShape(RoundedRectangle(cornerRadius: 14))
                }
                Text(preview.brand_name).font(.interSubheadline).foregroundStyle(TU.textDim)
                Text("A thank-you for your shoutout").font(.interTitle2.bold()).multilineTextAlignment(.center).foregroundStyle(.white)
                Text(preview.reward_text).font(.interTitle3).multilineTextAlignment(.center).foregroundStyle(TU.ember)
                if let terms = preview.offer_terms, !terms.isEmpty { Text(terms).font(.interFootnote).multilineTextAlignment(.center).foregroundStyle(TU.textDim) }
                if let store = preview.store_name { Label("Redeem at \(store)", systemImage: "mappin.and.ellipse").font(.interFootnote).foregroundStyle(TU.textDim) }
                Button { Task { await vm.claim() } } label: {
                    if vm.claiming { ProgressView().tint(.black).frame(maxWidth: .infinity) }
                    else { Text("Claim reward").frame(maxWidth: .infinity) }
                }
                .buttonStyle(.borderedProminent).tint(TU.ember).foregroundStyle(.black).disabled(vm.claiming)
                Text("Offer code: \(preview.short_code)").font(.interCaption).foregroundStyle(TU.textDim)
            }
            .padding()
        }
    }
}
