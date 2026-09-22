import SwiftUI

struct MobileProjectPeople: View {
    let vm: ProjectDetailViewModel
    let projectId: String
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var results: [MWAdminSearchUser] = []
    @State private var invited: Set<String> = []
    @State private var busy = false
    @State private var searching = false
    @State private var error: String?
    @State private var removing: MWProjectCollaborator?
    private var isOwner: Bool { vm.project?.mobileIsOwner == true }

    var body: some View {
        NavigationStack {
            List {
                Section("In this space") {
                    ForEach(vm.collaborators) { person in
                        HStack(spacing: 12) {
                            Text(String(person.name.prefix(1)).uppercased()).font(.headline)
                                .frame(width: 40, height: 40).background(EspressoStyle.sage.opacity(0.12), in: Circle())
                            VStack(alignment: .leading, spacing: 3) {
                                Text(person.name).font(.subheadline.weight(.semibold))
                                Text(person.email).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if person.role == "owner" { EspressoBadge(text: "Owner") }
                        }.swipeActions {
                            if isOwner && person.role != "owner" {
                                Button("Remove", role: .destructive) { removing = person }
                            }
                        }
                    }
                }
                if isOwner {
                    Section {
                        TextField("Search by name or email", text: $query)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        if searching { ProgressView() }
                        ForEach(results.filter { result in !vm.collaborators.contains { $0.userId == result.id } }) { person in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(person.name).font(.subheadline.weight(.medium))
                                    Text(person.email).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button(invited.contains(person.id) ? "Invited" : "Invite") { invite(person) }
                                    .buttonStyle(.bordered).disabled(busy || invited.contains(person.id))
                            }
                        }
                    } header: { Text("Bring someone in") }
                    footer: { Text("Invitations appear in their Espresso Projects screen. They choose whether to join.") }
                }
                if let error { Text(error).foregroundStyle(.red) }
            }.scrollContentBackground(.hidden).espressoBackground()
                .navigationTitle("People").navigationBarTitleDisplayMode(.inline)
                .toolbar { Button("Done") { dismiss() }.disabled(busy) }
                .interactiveDismissDisabled(busy)
                .task(id: query) {
                    results = []
                    let search = query.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard search.count >= 2 else { searching = false; return }
                    searching = true
                    do {
                        try await Task.sleep(for: .milliseconds(300))
                        let found = try await MatchaWorkService.shared.searchInvitableUsers(query: search)
                        try Task.checkCancellation()
                        results = found; searching = false
                    } catch is CancellationError { /* A newer query owns the UI. */ }
                    catch { if !Task.isCancelled { self.error = error.localizedDescription; searching = false } }
                }
                .confirmationDialog("Remove this person from the project?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
                    if let person = removing {
                        Button("Remove \(person.name)", role: .destructive) {
                            run {
                                try await MatchaWorkService.shared.removeCollaborator(projectId: projectId, userId: person.userId)
                                vm.collaborators.removeAll { $0.id == person.id }
                            }
                        }
                    }
                }
        }.tint(EspressoStyle.accent)
    }

    private func invite(_ person: MWAdminSearchUser) {
        run {
            try await MatchaWorkService.shared.addCollaborator(projectId: projectId, userId: person.id)
            invited.insert(person.id)
        }
    }
    private func run(_ operation: @escaping () async throws -> Void) {
        guard !busy else { return }
        busy = true; error = nil
        Task {
            defer { busy = false }
            do { try await operation() } catch { self.error = error.localizedDescription }
        }
    }
}
