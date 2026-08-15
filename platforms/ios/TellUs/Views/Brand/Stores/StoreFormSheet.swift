import SwiftUI

struct StoreFormSheet: View {
    @Bindable var vm: StoresViewModel
    @Environment(\.dismiss) private var dismiss
    let editing: Store?

    @State private var name: String
    @State private var address: String
    @State private var city: String
    @State private var state: String
    @State private var zipcode: String

    init(vm: StoresViewModel, editing: Store? = nil) {
        self.vm = vm
        self.editing = editing
        _name = State(initialValue: editing?.name ?? "")
        _address = State(initialValue: editing?.address ?? "")
        _city = State(initialValue: editing?.city ?? "")
        _state = State(initialValue: editing?.state ?? "")
        _zipcode = State(initialValue: editing?.zipcode ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                TextField("Name", text: $name)
                TextField("Address", text: $address)
                TextField("City", text: $city)
                TextField("State", text: $state)
                TextField("Zip code", text: $zipcode)
                if let error = vm.error {
                    Text(error).foregroundStyle(.red).font(.interFootnote)
                }
            }
            .navigationTitle(editing == nil ? "New store" : "Edit store")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            if let editing {
                                await vm.updateStore(id: editing.id, StoreUpdate(
                                    name: name, address: address.isEmpty ? nil : address,
                                    city: city.isEmpty ? nil : city, state: state.isEmpty ? nil : state,
                                    zipcode: zipcode.isEmpty ? nil : zipcode
                                ))
                            } else {
                                await vm.createStore(StoreCreate(
                                    name: name, address: address.isEmpty ? nil : address,
                                    city: city.isEmpty ? nil : city, state: state.isEmpty ? nil : state,
                                    zipcode: zipcode.isEmpty ? nil : zipcode
                                ))
                            }
                            dismiss()
                        }
                    }
                    .disabled(name.isEmpty)
                }
            }
        }
    }
}
