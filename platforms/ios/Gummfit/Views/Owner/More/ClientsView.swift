import SwiftUI

struct ClientsView: View {
    let site: CappeSite

    @State private var vm = ClientsViewModel()
    @State private var search = ""
    @State private var editing: CappeClient?

    private var filtered: [CappeClient] {
        guard !search.isEmpty else { return vm.clients }
        let q = search.lowercased()
        return vm.clients.filter {
            $0.email.lowercased().contains(q) || ($0.name?.lowercased().contains(q) ?? false)
        }
    }

    var body: some View {
        Group {
            if vm.isLoading && vm.clients.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.clients.isEmpty {
                ContentUnavailableView("No clients yet", systemImage: "person.2")
            } else {
                List {
                    ForEach(filtered) { client in
                        Button { editing = client } label: {
                            ClientRow(client: client)
                        }
                        .buttonStyle(.plain)
                    }
                    .onDelete { offsets in
                        for index in offsets {
                            let client = filtered[index]
                            Task { await vm.delete(siteId: site.id, email: client.email) }
                        }
                    }
                }
                .listStyle(.plain)
                .searchable(text: $search)
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Clients")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Add", systemImage: "plus") { editing = CappeClient(email: "", name: nil, phone: nil, orders_count: 0, bookings_count: 0, is_subscriber: false, has_thread: false, is_imported: false, total_spent_cents: 0, last_activity: nil, location_id: nil, location_name: nil) }
            }
        }
        .sheet(item: $editing) { client in
            NavigationStack {
                ClientEditSheet(site: site, client: client, onSaved: { Task { await vm.load(siteId: site.id) } })
            }
        }
        .task { await vm.load(siteId: site.id) }
        .refreshable { await vm.load(siteId: site.id) }
    }
}

private struct ClientRow: View {
    let client: CappeClient

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(client.name ?? client.email).font(.subheadline.bold())
                if client.name != nil { Text(client.email).font(.caption).foregroundStyle(GummfitTheme.textDim) }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(Formatters.cents(client.total_spent_cents)).font(.caption.bold())
                Text("\(client.orders_count) orders · \(client.bookings_count) bookings")
                    .font(.caption2)
                    .foregroundStyle(GummfitTheme.textDim)
            }
        }
    }
}

private struct ClientEditSheet: View {
    let site: CappeSite
    let client: CappeClient
    var onSaved: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @State private var email: String
    @State private var name: String
    @State private var phone: String
    @State private var notes = ""
    @State private var isSaving = false
    @State private var error: String?

    init(site: CappeSite, client: CappeClient, onSaved: @escaping () -> Void = {}) {
        self.site = site
        self.client = client
        self.onSaved = onSaved
        _email = State(initialValue: client.email)
        _name = State(initialValue: client.name ?? "")
        _phone = State(initialValue: client.phone ?? "")
    }

    var body: some View {
        Form {
            ErrorBanner(message: error)
            TextField("Email", text: $email)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .disabled(!client.email.isEmpty)
            TextField("Name", text: $name)
            TextField("Phone", text: $phone)
            TextField("Notes", text: $notes, axis: .vertical)
        }
        .navigationTitle(client.email.isEmpty ? "Add client" : "Edit client")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(isSaving ? "Saving…" : "Save") { Task { await save() } }
                    .disabled(email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
            }
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
        }
    }

    private func save() async {
        isSaving = true
        error = nil
        defer { isSaving = false }
        do {
            _ = try await ClientsService.shared.upsert(siteId: site.id, CappeClientCreate(
                email: email, name: name.isEmpty ? nil : name, phone: phone.isEmpty ? nil : phone,
                notes: notes.isEmpty ? nil : notes
            ))
            onSaved()
            dismiss()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
