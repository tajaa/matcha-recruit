import SwiftUI

struct RiderView: View {
    let site: CappeSite

    @State private var vm = RiderViewModel()

    var body: some View {
        List {
            ForEach($vm.items) { $item in
                VStack(alignment: .leading) {
                    TextField("Label", text: $item.label)
                    TextField("Detail", text: Binding(get: { item.detail ?? "" }, set: { item.detail = $0.isEmpty ? nil : $0 }))
                        .font(.caption)
                    Toggle("Required", isOn: $item.is_required)
                }
            }
            .onDelete { vm.items.remove(atOffsets: $0) }
            Button("Add item") {
                vm.items.append(CappeRiderItemInput(label: ""))
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Rider")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(vm.isSaving ? "Saving…" : "Save") { Task { await vm.save(siteId: site.id) } }
                    .disabled(vm.isSaving)
            }
        }
        .task { await vm.load(siteId: site.id) }
    }
}
