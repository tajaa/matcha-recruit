import SwiftUI

struct MobileProjectEditor: View {
    var project: MWProject? = nil
    let onSave: (MWProject) async -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState
    @State private var title = ""
    @State private var kind = "general"
    @State private var icon = "folder"
    @State private var saving = false
    @State private var error: String?
    private var canCreate: Bool {
        guard project == nil, let entitlements = appState.entitlements else { return true }
        return entitlements.has(kind == "collab" ? "projects_collab" : "projects_solo")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Make space for something good") {
                    TextField("Project name", text: $title)
                    if project == nil {
                        Picker("Workspace", selection: $kind) {
                            Text("Solo · Just for you").tag("general")
                            Text("Together · Invite collaborators").tag("collab")
                        }
                    }
                }
                Section("Choose a symbol") {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 48))], spacing: 12) {
                        ForEach(mwProjectIconOptions, id: \.self) { symbol in
                            Button { icon = symbol } label: {
                                Image(systemName: symbol).font(.title2).frame(width: 48, height: 48)
                                    .background(icon == symbol ? EspressoStyle.accent.opacity(0.15) : Color.clear, in: RoundedRectangle(cornerRadius: 12))
                            }.buttonStyle(.plain).accessibilityLabel(symbol.replacingOccurrences(of: ".", with: " "))
                                .accessibilityAddTraits(icon == symbol ? .isSelected : [])
                        }
                    }.padding(.vertical, 6)
                }
                if !canCreate {
                    Section { Text(kind == "collab" ? "Creating collaborative projects requires Pro or Business. You can still open your existing projects." : "Creating solo projects requires Lite or higher. You can still open your existing projects.").font(.subheadline).foregroundStyle(.secondary) }
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }.scrollContentBackground(.hidden).espressoBackground()
                .navigationTitle(project == nil ? "New project" : "Edit project").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(saving) }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(saving ? "Saving…" : "Save") { Task { await save() } }
                            .disabled(saving || !canCreate || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }.interactiveDismissDisabled(saving)
                .onAppear { if let project { title = project.title; icon = project.icon ?? "folder"; kind = project.projectType ?? "general" } }
        }.tint(EspressoStyle.accent)
    }

    private func save() async {
        saving = true; error = nil
        defer { saving = false }
        do {
            let name = title.trimmingCharacters(in: .whitespacesAndNewlines)
            let result: MWProject
            if let project { result = try await MatchaWorkService.shared.updateProjectMeta(id: project.id, title: name, icon: icon) }
            else { result = try await MatchaWorkService.shared.createProject(title: name, projectType: kind, icon: icon) }
            await onSave(result); dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
