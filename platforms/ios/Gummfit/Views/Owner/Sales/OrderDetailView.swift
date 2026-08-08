import SwiftUI

struct OrderDetailView: View {
    let site: CappeSite
    let orderId: String

    @State private var vm = OrderDetailViewModel()
    @State private var statusChoice = "pending"
    @State private var carrier = ""
    @State private var originalCarrier = ""
    @State private var tracking = ""
    @State private var originalTracking = ""
    @State private var declineReason = ""
    @State private var showDecline = false
    @State private var receiptURL: URL?
    @State private var deliverableItemId: String?
    @State private var deliverableURL = ""

    var body: some View {
        Group {
            if let order = vm.order {
                Form {
                    ErrorBanner(message: vm.error)

                    Section("Customer") {
                        Text(order.customer_name ?? "—")
                        if let email = order.customer_email { Text(email).font(.caption).foregroundStyle(GummfitTheme.textDim) }
                    }

                    if let address = order.shipping_address {
                        Section("Shipping to") {
                            Text([address.name, address.line1, address.line2, address.city, address.state, address.postal_code, address.country]
                                .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", "))
                        }
                    }

                    Section("Items") {
                        ForEach(order.items) { item in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text("\(item.quantity)× \(item.title)")
                                    Spacer()
                                    Text(Formatters.cents(item.unit_price_cents * item.quantity, currency: order.currency))
                                }
                                ForEach(Array(item.selected_options.enumerated()), id: \.offset) { _, option in
                                    Text("\(option.group): \(option.name)").font(.caption).foregroundStyle(GummfitTheme.textDim)
                                }
                                if item.fulfillment == .service || item.fulfillment == .digital {
                                    if let url = item.deliverable_url {
                                        Text("Delivered: \(url)").font(.caption).foregroundStyle(GummfitTheme.accent)
                                    } else {
                                        Button("Attach deliverable") {
                                            deliverableItemId = item.id
                                            deliverableURL = ""
                                        }
                                        .font(.caption)
                                    }
                                }
                            }
                        }
                    }

                    if order.requires_approval && order.status == .pending {
                        Section {
                            Button("Accept order") { Task { await vm.accept(siteId: site.id) } }
                            Button("Decline order", role: .destructive) { showDecline = true }
                        }
                    }

                    Section("Status & tracking") {
                        Picker("Status", selection: $statusChoice) {
                            Text("Pending").tag("pending")
                            Text("Paid").tag("paid")
                            Text("Fulfilled").tag("fulfilled")
                            Text("Cancelled").tag("cancelled")
                            Text("Refunded").tag("refunded")
                        }
                        TextField("Carrier", text: $carrier)
                        TextField("Tracking number", text: $tracking)
                        Button("Update") {
                            Task {
                                await vm.updateStatus(
                                    siteId: site.id,
                                    status: statusChoice == order.status.rawValue ? nil : statusChoice,
                                    carrier: .from(carrier, touched: carrier != originalCarrier),
                                    trackingNumber: .from(tracking, touched: tracking != originalTracking)
                                )
                            }
                        }
                        .disabled(!OrderDetailViewModel.isValidStatusUpdate(
                            status: statusChoice == order.status.rawValue ? nil : statusChoice,
                            carrier: .from(carrier, touched: carrier != originalCarrier),
                            trackingNumber: .from(tracking, touched: tracking != originalTracking)
                        ))
                    }

                    Section {
                        Button("View receipt") {
                            Task { receiptURL = await vm.downloadReceiptFileURL(siteId: site.id) }
                        }
                    }
                }
                .onAppear {
                    statusChoice = order.status.rawValue
                    carrier = order.carrier ?? ""
                    originalCarrier = carrier
                    tracking = order.tracking_number ?? ""
                    originalTracking = tracking
                }
            } else if vm.isLoading {
                ProgressView()
            }
        }
        .navigationTitle("Order")
        .sheet(item: $receiptURL.map(PresentedURL.init)) { wrapped in
            QLPreviewRepresentable(url: wrapped.url)
        }
        .sheet(isPresented: Binding(get: { deliverableItemId != nil }, set: { if !$0 { deliverableItemId = nil } })) {
            NavigationStack {
                Form {
                    TextField("Deliverable URL", text: $deliverableURL)
                }
                .navigationTitle("Attach deliverable")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Save") {
                            Task {
                                if let itemId = deliverableItemId {
                                    await vm.attachDeliverable(siteId: site.id, itemId: itemId, url: deliverableURL)
                                }
                                deliverableItemId = nil
                            }
                        }
                        .disabled(deliverableURL.isEmpty)
                    }
                }
            }
        }
        .alert("Decline order", isPresented: $showDecline) {
            TextField("Reason (optional)", text: $declineReason)
            Button("Decline", role: .destructive) {
                Task { await vm.decline(siteId: site.id, reason: declineReason.isEmpty ? nil : declineReason) }
            }
            Button("Cancel", role: .cancel) {}
        }
        .task { await vm.load(siteId: site.id, orderId: orderId) }
    }
}

/// `Identifiable` shim so `.sheet(item:)` can key off an optional `URL`
/// (`URL` itself isn't `Identifiable`).
private struct PresentedURL: Identifiable {
    let url: URL
    var id: URL { url }
}

private extension Binding where Value == URL? {
    func map(_ transform: @escaping (URL) -> PresentedURL) -> Binding<PresentedURL?> {
        Binding<PresentedURL?>(
            get: { self.wrappedValue.map(transform) },
            set: { self.wrappedValue = $0?.url }
        )
    }
}
