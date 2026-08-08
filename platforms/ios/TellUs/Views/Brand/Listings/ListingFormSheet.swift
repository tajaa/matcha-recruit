import SwiftUI

struct ListingFormSheet: View {
    @Bindable var vm: BrandListingsViewModel
    @Environment(\.dismiss) private var dismiss
    let editing: Listing?

    @State private var title: String
    @State private var description: String
    @State private var pointsCost: String
    @State private var quantityTotal: String
    @State private var redemptionType: RedemptionType
    @State private var terms: String
    @State private var city: String
    @State private var state: String
    @State private var expiryDays: Double
    @State private var visibility: ListingVisibility
    @State private var isActive: Bool

    init(vm: BrandListingsViewModel, editing: Listing? = nil) {
        self.vm = vm
        self.editing = editing
        _title = State(initialValue: editing?.title ?? "")
        _description = State(initialValue: editing?.description ?? "")
        _pointsCost = State(initialValue: editing.map { String($0.points_cost) } ?? "")
        _quantityTotal = State(initialValue: editing?.quantity_total.map(String.init) ?? "")
        _redemptionType = State(initialValue: editing?.redemption_type ?? .code)
        _terms = State(initialValue: editing?.terms ?? "")
        _city = State(initialValue: editing?.city ?? "")
        _state = State(initialValue: editing?.state ?? "")
        _expiryDays = State(initialValue: Double(editing?.expiry_days ?? 30))
        _visibility = State(initialValue: editing?.visibility ?? .public)
        _isActive = State(initialValue: editing?.is_active ?? true)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Title", text: $title)
                    TextField("Description", text: $description, axis: .vertical)
                    TextField("Points cost", text: $pointsCost).keyboardType(.numberPad)
                    TextField("Quantity available (blank = unlimited)", text: $quantityTotal).keyboardType(.numberPad)
                }
                Section {
                    Picker("Redemption type", selection: $redemptionType) {
                        Text("Code").tag(RedemptionType.code)
                        Text("QR").tag(RedemptionType.qr)
                        Text("Manual").tag(RedemptionType.manual)
                    }
                    Picker("Visibility", selection: $visibility) {
                        Text("Public").tag(ListingVisibility.public)
                        Text("Board members only").tag(ListingVisibility.board)
                    }
                    Stepper("Expires \(Int(expiryDays)) days after redeem", value: $expiryDays, in: 1...365)
                    Toggle("Active", isOn: $isActive)
                }
                Section {
                    TextField("Terms (optional)", text: $terms, axis: .vertical)
                    TextField("City (optional)", text: $city)
                    TextField("State (optional)", text: $state)
                }
                if let error = vm.error {
                    Text(error).foregroundStyle(.red).font(.footnote)
                }
            }
            .navigationTitle(editing == nil ? "New reward" : "Edit reward")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            let points = Int(pointsCost) ?? 0
                            let quantity = Int(quantityTotal)
                            if let editing {
                                await vm.update(id: editing.id, ListingUpdate(
                                    title: title, description: description.isEmpty ? nil : description,
                                    image_url: nil, points_cost: points, quantity_total: quantity,
                                    redemption_type: redemptionType.rawValue, terms: terms.isEmpty ? nil : terms,
                                    city: city.isEmpty ? nil : city, state: state.isEmpty ? nil : state,
                                    active_from: nil, active_to: nil, is_active: isActive,
                                    expiry_days: Int(expiryDays), visibility: visibility.rawValue
                                ))
                            } else {
                                await vm.create(ListingCreate(
                                    title: title, description: description.isEmpty ? nil : description,
                                    image_url: nil, points_cost: points, quantity_total: quantity,
                                    redemption_type: redemptionType.rawValue, terms: terms.isEmpty ? nil : terms,
                                    city: city.isEmpty ? nil : city, state: state.isEmpty ? nil : state,
                                    active_from: nil, active_to: nil, is_active: isActive,
                                    expiry_days: Int(expiryDays), visibility: visibility.rawValue
                                ))
                            }
                            dismiss()
                        }
                    }
                    .disabled(title.isEmpty || Int(pointsCost) == nil)
                }
            }
        }
    }
}
