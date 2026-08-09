import SwiftUI
import VisionKit

/// Counter redeem in the brand owner's own app — their phone is the scanner.
///
/// The web `/scan/{device_token}` page exists for a shared tablet that nobody
/// wants to log in on; this path is authenticated by the owner's session, so it
/// needs no device token and can't be left minted after a phone is lost.
struct BrandScanView: View {
    @State private var vm = BrandScanViewModel()
    @State private var typed = ""

    private var scannerAvailable: Bool {
        DataScannerViewController.isSupported && DataScannerViewController.isAvailable
    }

    var body: some View {
        VStack(spacing: 16) {
            if let outcome = vm.outcome {
                resultCard(outcome)
            } else {
                scanner
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(TU.ink)
        .navigationTitle("Redeem a card")
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private var scanner: some View {
        if scannerAvailable {
            QRScannerView(isActive: vm.isScanning) { code in
                Task { await vm.handle(decoded: code) }
            }
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .padding()
        } else {
            EmptyState(
                icon: "camera.metering.unknown",
                title: "Camera unavailable",
                hint: "Type the code printed under the customer's QR instead."
            )
        }

        // Always present, not just as a fallback: a cracked screen or a dim
        // phone is common enough at a counter that staff need a way through
        // that doesn't depend on the camera reading anything.
        HStack {
            TextField("Card code", text: $typed)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
            Button("Redeem") {
                Task {
                    await vm.redeem(cardToken: typed.trimmingCharacters(in: .whitespacesAndNewlines))
                    typed = ""
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(TU.ember)
            .foregroundStyle(.black)
            .disabled(typed.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || vm.redeeming)
        }
        .padding(.horizontal)
        .padding(.bottom)
    }

    @ViewBuilder
    private func resultCard(_ outcome: BrandScanViewModel.Outcome) -> some View {
        VStack(spacing: 14) {
            Image(systemName: icon(outcome))
                .font(.system(size: 64))
                .foregroundStyle(tint(outcome))
            Text(headline(outcome))
                .font(.title2.bold())
                .multilineTextAlignment(.center)
                .foregroundStyle(.white)
            if let sub = subhead(outcome) {
                Text(sub)
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(TU.textDim)
            }
            Button("Scan next") { vm.scanNext() }
                .buttonStyle(.borderedProminent)
                .tint(TU.ember)
                .foregroundStyle(.black)
                .padding(.top, 8)
        }
        .padding(32)
    }

    private func icon(_ o: BrandScanViewModel.Outcome) -> String {
        switch o {
        case .success: return "checkmark.circle.fill"
        case .alreadyRedeemed: return "exclamationmark.triangle.fill"
        case .expired, .cancelled: return "xmark.circle.fill"
        case .invalid: return "questionmark.circle.fill"
        }
    }

    private func tint(_ o: BrandScanViewModel.Outcome) -> Color {
        switch o {
        case .success: return .green
        case .alreadyRedeemed: return .orange
        case .expired, .cancelled, .invalid: return .red
        }
    }

    private func headline(_ o: BrandScanViewModel.Outcome) -> String {
        switch o {
        case .success(let result): return result.reward_text
        case .alreadyRedeemed: return "Already used"
        case .expired: return "Card expired"
        case .cancelled: return "Card no longer valid"
        case .invalid: return "Not a valid reward card"
        }
    }

    private func subhead(_ o: BrandScanViewModel.Outcome) -> String? {
        switch o {
        case .success(let result):
            return [result.campaign_title, result.store_name].compactMap { $0 }.joined(separator: " · ")
        case .alreadyRedeemed(let at, let store):
            // When and where, so staff can tell an honest double-tap from
            // someone trying a screenshot of a card used yesterday.
            let when = at.map { Formatters.relativeString(from: $0) } ?? ""
            if let store, !when.isEmpty { return "Redeemed \(when) at \(store)" }
            if !when.isEmpty { return "Redeemed \(when)" }
            return "This card has already been redeemed."
        case .expired(let message), .cancelled(let message), .invalid(let message):
            return message
        }
    }
}
