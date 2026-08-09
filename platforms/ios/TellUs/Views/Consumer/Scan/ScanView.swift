import SwiftUI
import VisionKit

/// What a scanned code turned out to be. One camera, two kinds of QR in the
/// wild — a feedback-intake link on a table tent, and a promo claim link on a
/// flyer — so the scanner has to tell them apart rather than assuming.
enum ScannedTarget: Equatable, Hashable {
    case intake(String)
    case promoClaim(String)

    var token: String {
        switch self {
        case .intake(let t), .promoClaim(let t): return t
        }
    }
}

/// Extracts a target from a scanned/pasted string. Handles the full web URL
/// (https://…/tellus/i/{token}, …/tellus/p/{token}), a bare path (/i/{token},
/// /p/{token}), or a bare token — which stays an intake token, the only kind
/// that was ever printed without a URL around it.
/// Pure function, unit-tested in Tests/IntakeTokenTests.swift.
func scannedTarget(from raw: String) -> ScannedTarget? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if let url = URL(string: trimmed) {
        let components = url.pathComponents
        // Search from the END: a host or an earlier path segment could
        // legitimately be "p" (e.g. /p/p/{token} is unlikely, but /tellus/p/…
        // sitting under a path that also contains "i" is not).
        if let i = components.lastIndex(of: "p"), components.indices.contains(i + 1) {
            return .promoClaim(components[i + 1])
        }
        if let i = components.lastIndex(of: "i"), components.indices.contains(i + 1) {
            return .intake(components[i + 1])
        }
    }
    let range = trimmed.range(of: "^[A-Za-z0-9_-]{8,}$", options: .regularExpression)
    return range != nil ? .intake(trimmed) : nil
}

/// Kept as the intake-only shorthand the rest of the app already calls.
func intakeToken(from raw: String) -> String? {
    if case .intake(let token) = scannedTarget(from: raw) { return token }
    return nil
}

struct ScannedToken: Identifiable, Hashable {
    let id = UUID()
    let target: ScannedTarget

    var token: String { target.token }
}

struct ScanView: View {
    @State private var pastedText = ""
    @State private var navigate: ScannedToken?
    private var scannerAvailable: Bool {
        DataScannerViewController.isSupported && DataScannerViewController.isAvailable
    }

    var body: some View {
        VStack(spacing: 16) {
            if scannerAvailable {
                QRScannerView(isActive: navigate == nil) { code in
                    if let target = scannedTarget(from: code) { navigate = ScannedToken(target: target) }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .padding()
            } else {
                EmptyState(icon: "qrcode.viewfinder", title: "Camera scanning unavailable",
                           hint: "Paste a feedback link or token below.")
            }

            VStack(spacing: 8) {
                TextField("Paste feedback link or code", text: $pastedText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding()
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                Button("Go") {
                    if let target = scannedTarget(from: pastedText) { navigate = ScannedToken(target: target) }
                }
                .disabled(scannedTarget(from: pastedText) == nil)
            }
            .padding(.horizontal)
            .padding(.bottom)
        }
        .navigationTitle("Scan")
        .navigationDestination(item: $navigate) { scanned in
            switch scanned.target {
            case .intake(let token):
                IntakeLoaderView(token: token)
            case .promoClaim(let token):
                ClaimSheet(token: token)
            }
        }
    }
}
