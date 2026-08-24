import SwiftUI

struct RedeemCodeView: View {
    @State private var code = ""
    @State private var showOffer = false

    var body: some View {
        Form {
            Section {
                TextField("8-character offer code", text: $code)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                HStack {
                    PasteButton(payloadType: String.self) { values in
                        if let value = values.first { code = value.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
                    }
                    Spacer()
                    Button("Find offer") { showOffer = normalizeShoutoutCode(code) != nil }
                        .buttonStyle(.borderedProminent).tint(TU.ember).disabled(normalizeShoutoutCode(code) == nil)
                }
            } footer: {
                Text("Paste the code from the thank-you link your business sent you.")
            }
        }
        .themedScreen()
        .navigationTitle("Redeem a code")
        .sheet(isPresented: $showOffer) { if let normalized = normalizeShoutoutCode(code) { ShoutoutOfferView(code: normalized) } }
    }
}
