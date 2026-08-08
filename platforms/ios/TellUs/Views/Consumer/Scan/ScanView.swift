import SwiftUI
import VisionKit

/// Extracts an intake token from a scanned/pasted string. Handles the full
/// web URL (https://…/tellus/i/{token}), a bare path (/i/{token}), or a
/// bare token. Pure function, unit-tested in Tests/IntakeTokenTests.swift.
func intakeToken(from raw: String) -> String? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if let url = URL(string: trimmed) {
        let components = url.pathComponents
        if let i = components.firstIndex(of: "i"), components.indices.contains(i + 1) {
            return components[i + 1]
        }
    }
    let range = trimmed.range(of: "^[A-Za-z0-9_-]{8,}$", options: .regularExpression)
    return range != nil ? trimmed : nil
}

struct ScanView: View {
    @State private var pastedText = ""
    @State private var navigateToken: String?
    private var scannerAvailable: Bool {
        DataScannerViewController.isSupported && DataScannerViewController.isAvailable
    }

    var body: some View {
        VStack(spacing: 16) {
            if scannerAvailable {
                QRScannerView { code in
                    if let token = intakeToken(from: code) { navigateToken = token }
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
                    if let token = intakeToken(from: pastedText) { navigateToken = token }
                }
                .disabled(intakeToken(from: pastedText) == nil)
            }
            .padding(.horizontal)
            .padding(.bottom)
        }
        .navigationTitle("Scan")
        .navigationDestination(item: $navigateToken) { token in
            IntakeLoaderView(token: token)
        }
    }
}

extension String: @retroactive Identifiable {
    public var id: String { self }
}
