import SwiftUI

/// Shared status/pricing/location-count UI, embedded both in BillingWallView
/// (a lapsed-plan brand) and the More tab (an active brand checking on
/// billing). Stripe checkout itself stays a web link-out.
struct BillingView: View {
    @State private var vm = BillingViewModel()
    @State private var locationCount: Double = 1

    var body: some View {
        Form {
            if let status = vm.status {
                Section {
                    LabeledContent("Plan", value: status.plan_status.rawValue.capitalized)
                    LabeledContent("Stores", value: "\(status.store_count)")
                    if status.price_available {
                        LabeledContent("Monthly total", value: String(format: "$%.2f", Double(status.monthly_total_cents) / 100))
                    }
                }
                Section("Location count") {
                    Stepper("\(Int(locationCount)) locations", value: $locationCount, in: Double(vm.pricing?.min_locations ?? 1)...Double(vm.pricing?.max_locations ?? 500))
                    Button("Update") { Task { await vm.setLocations(Int(locationCount)) } }
                    if let pricing = vm.pricing {
                        Text(String(format: "$%.2f per location / mo", Double(pricing.price_per_location_cents) / 100))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Section {
                Button {
                    SafeURL.open(URL(string: APIClient.shared.webOrigin + "/tellus/brand/billing"))
                } label: {
                    HStack {
                        Text("Checkout / manage on web")
                        Spacer()
                        Image(systemName: "arrow.up.right.square")
                    }
                }
            }
            if let error = vm.error {
                Section { Text(error).foregroundStyle(.red).font(.footnote) }
            }
        }
        .navigationTitle("Billing")
        .task {
            await vm.load()
            if let count = vm.status?.location_count { locationCount = Double(count) }
        }
        .refreshable { await vm.load() }
    }
}
