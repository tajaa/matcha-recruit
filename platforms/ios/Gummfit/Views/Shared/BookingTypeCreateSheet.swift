import SwiftUI

/// Shared "create a booking type" form — used by BookingTypesView (Sales →
/// Booking types) and ProductFormView's inline "+ New booking type" picker
/// row. Owns its own save/error state so a failure keeps the sheet open with
/// the typed fields intact and a visible reason, instead of silently
/// dismissing (see PR #201 review: ProductFormView's original `try?` variant
/// swallowed failures with no feedback).
struct BookingTypeCreateSheet: View {
    let siteId: String
    var onCreated: (CappeBookingType) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var duration = 30
    @State private var priceCents = 0
    @State private var isSaving = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                ErrorBanner(message: error)
                TextField("Name", text: $name)
                Stepper("\(duration) minutes", value: $duration, in: 5...480, step: 5)
                HStack {
                    Text("Price")
                    Spacer()
                    TextField("0.00", value: Binding(
                        get: { Double(priceCents) / 100 },
                        set: { priceCents = Int(($0 * 100).rounded()) }
                    ), format: .number.precision(.fractionLength(2)))
                        .keyboardType(.decimalPad)
                }
            }
            .navigationTitle("New booking type")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") { Task { await save() } }
                        .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func save() async {
        isSaving = true
        defer { isSaving = false }
        do {
            let created = try await BookingsService.shared.createType(
                siteId: siteId,
                CappeBookingTypeCreate(name: name, duration_minutes: duration, price_cents: priceCents)
            )
            onCreated(created)
            dismiss()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
