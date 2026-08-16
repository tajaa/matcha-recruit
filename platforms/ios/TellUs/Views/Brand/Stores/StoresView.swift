import SwiftUI

struct StoresView: View {
    var openAddOnAppear: Bool = false
    @State private var vm = StoresViewModel()
    @State private var editingStore: Store?
    @State private var showNewStore = false
    @State private var showNewLink = false
    @State private var pendingDeleteStore: Store?
    @State private var qrLink: FeedbackLink?
    @State private var didAutoOpen = false

    var body: some View {
        List {
            Section("Stores") {
                ForEach(vm.stores) { store in
                    VStack(alignment: .leading) {
                        Text(store.name).font(.interSubheadline.bold())
                        if let address = store.address { Text(address).font(.interCaption).foregroundStyle(.secondary) }
                    }
                    .contentShape(Rectangle())
                    .onTapGesture { editingStore = store }
                    .swipeActions {
                        Button("Delete", role: .destructive) { pendingDeleteStore = store }
                    }
                }
                Button("Add store") { showNewStore = true }
            }

            Section("Feedback links") {
                ForEach(vm.links) { link in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(link.label ?? String(link.token.prefix(8)))
                            if let storeName = link.store_name {
                                Text(storeName).font(.interCaption).foregroundStyle(.secondary)
                            }
                            Text("\(link.use_count) uses" + (link.max_uses.map { " / \($0) max" } ?? ""))
                                .font(.interCaption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if link.revoked_at != nil {
                            StatusChip(text: "Revoked", tint: .red)
                        } else if !link.is_active {
                            StatusChip(text: "Inactive", tint: .gray)
                        }
                    }
                    .contentShape(Rectangle())
                    .onTapGesture { qrLink = link }
                    .swipeActions {
                        if link.revoked_at == nil {
                            Button("Revoke", role: .destructive) { Task { await vm.revokeLink(id: link.id) } }
                        }
                    }
                }
                Button("Add link") { showNewLink = true }
            }
        }
        .navigationTitle("Stores & QR")
        .task {
            await vm.load()
            // Guarded so re-appearing after dismissing the sheet (pop/push
            // within the same NavigationStack) doesn't reopen it — .task can
            // re-run on view identity changes, this must only fire once.
            if openAddOnAppear, !didAutoOpen {
                didAutoOpen = true
                showNewStore = true
            }
        }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
        .sheet(isPresented: $showNewStore) { StoreFormSheet(vm: vm) }
        .sheet(item: $editingStore) { store in StoreFormSheet(vm: vm, editing: store) }
        .sheet(isPresented: $showNewLink) { LinkFormSheet(vm: vm) }
        .sheet(item: $qrLink) { link in LinkQRSheet(link: link) }
        .confirmationDialog("Delete this store?", isPresented: Binding(
            get: { pendingDeleteStore != nil }, set: { if !$0 { pendingDeleteStore = nil } }
        ), titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                if let store = pendingDeleteStore { Task { await vm.deleteStore(id: store.id) } }
                pendingDeleteStore = nil
            }
        }
    }
}
