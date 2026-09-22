import SwiftUI

struct MobileProjectNotes: View {
    let vm: ProjectDetailViewModel
    let projectId: String
    @State private var creating = false
    @State private var editing: MWProjectSection?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                HStack {
                    EspressoSectionHeading(title: "The thinking space", detail: "\(vm.project?.sections?.count ?? 0) notes")
                    Button("New note", systemImage: "plus") { creating = true }.labelStyle(.iconOnly).frame(width: 44, height: 44)
                        .disabled(vm.project?.mobileCanEdit != true)
                }
                if (vm.project?.sections ?? []).isEmpty {
                    EspressoEmptyState(title: "Keep the good ideas", message: "Capture a brief, meeting notes, or the thought you don't want to lose.", symbol: "square.and.pencil")
                }
                ForEach(vm.project?.sections ?? []) { section in
                    Button { editing = section } label: {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text(section.title.isEmpty ? "Untitled note" : section.title).font(.headline)
                                Spacer()
                                Image(systemName: "arrow.up.right").font(.caption).foregroundStyle(EspressoStyle.accent)
                            }
                            Text(.init(section.content ?? "Start writing…")).font(.subheadline).foregroundStyle(.secondary)
                                .lineLimit(5).frame(maxWidth: .infinity, alignment: .leading)
                            if section.hasPendingRevision { EspressoBadge(text: "Revision waiting · review on desktop") }
                        }.multilineTextAlignment(.leading).espressoCard()
                    }.buttonStyle(EspressoPressStyle())
                }
            }.padding(20).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }
        .refreshable { await vm.loadProject(id: projectId) }
        .sheet(isPresented: $creating) { MobileNoteEditor(vm: vm, projectId: projectId) }
        .sheet(item: $editing) { MobileNoteEditor(vm: vm, projectId: projectId, section: $0) }
    }
}

struct MobileNoteEditor: View {
    let vm: ProjectDetailViewModel
    let projectId: String
    var section: MWProjectSection? = nil
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var content = ""
    @State private var preview = false
    @State private var busy = false
    @State private var error: String?
    @State private var confirmDelete = false
    @State private var confirmDiscard = false
    private var hasChanges: Bool { title != (section?.title ?? "") || content != (section?.content ?? "") }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 18) {
                TextField("Note title", text: $title).font(.title.weight(.semibold))
                Picker("Mode", selection: $preview) { Text("Write").tag(false); Text("Preview").tag(true) }.pickerStyle(.segmented)
                if preview {
                    ScrollView { Text(.init(content)).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled) }
                } else {
                    TextEditor(text: $content).scrollContentBackground(.hidden)
                        .accessibilityLabel("Note content").frame(maxHeight: .infinity)
                    Text("Markdown supported: **bold**, *italic*, and [links](https://…).").font(.caption).foregroundStyle(.secondary)
                }
                if let error { Text(error).font(.footnote).foregroundStyle(.red) }
            }.padding(20).espressoBackground().disabled(busy || vm.project?.mobileCanEdit != true)
                .navigationTitle(section == nil ? "New note" : "Note").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") { if hasChanges { confirmDiscard = true } else { dismiss() } }.disabled(busy)
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(busy ? "Saving…" : "Save") { Task { await save() } }
                            .disabled(busy || vm.project?.mobileCanEdit != true || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    if section != nil && vm.project?.mobileCanEdit == true {
                        ToolbarItem(placement: .bottomBar) { Button("Delete note", role: .destructive) { confirmDelete = true }.disabled(busy) }
                    }
                }
                .interactiveDismissDisabled(busy || hasChanges)
                .confirmationDialog("Discard unsaved edits?", isPresented: $confirmDiscard, titleVisibility: .visible) {
                    Button("Discard edits", role: .destructive) { dismiss() }
                }
                .onAppear { title = section?.title ?? ""; content = section?.content ?? "" }
                .confirmationDialog("Permanently delete this note?", isPresented: $confirmDelete, titleVisibility: .visible) {
                    Button("Delete note", role: .destructive) { Task { await remove() } }
                }
        }.tint(EspressoStyle.accent)
    }

    private func save() async {
        busy = true; error = nil
        defer { busy = false }
        do {
            let name = title.trimmingCharacters(in: .whitespacesAndNewlines)
            let updated: MWProject
            if let section {
                // Detect remote edits before replacing the section. The API has
                // no revision precondition, so keep the user's draft on conflict.
                let fresh = try await MatchaWorkService.shared.getProjectDetail(id: projectId, forceRefresh: true)
                guard let current = fresh.sections?.first(where: { $0.id == section.id }),
                      current.content == section.content, current.title == section.title else {
                    error = "This note changed elsewhere. Your draft is still here—copy it before reopening the latest version."
                    return
                }
                updated = try await MatchaWorkService.shared.updateProjectSection(projectId: projectId, sectionId: section.id, title: name, content: content)
            } else {
                updated = try await MatchaWorkService.shared.addProjectSection(projectId: projectId, title: name, content: content)
            }
            vm.project = updated
            MatchaWorkService.shared.invalidateProjectDetail(id: projectId)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }

    private func remove() async {
        guard let section else { return }
        busy = true
        defer { busy = false }
        do {
            vm.project = try await MatchaWorkService.shared.deleteProjectSection(projectId: projectId, sectionId: section.id)
            MatchaWorkService.shared.invalidateProjectDetail(id: projectId)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
