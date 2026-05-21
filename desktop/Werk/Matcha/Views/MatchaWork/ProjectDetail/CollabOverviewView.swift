import SwiftUI

struct CollabOverviewView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @Binding var collabPanel: CollabRightPanel
    @Binding var showCollaborators: Bool
    let onExport: (String) -> Void

    @State private var showAddElement = false
    @State private var newElementName = ""
    @State private var newElementKind: String? = nil
    @State private var newElementAssignedTo: String? = nil
    @State private var editingElement: MWProjectElement? = nil
    @State private var editElementName = ""
    @State private var editElementKind: String? = nil
    @State private var editElementAssignedTo: String? = nil

    private let elementKinds: [(key: String, label: String)] = [
        ("chapter", "Chapter"), ("feature", "Feature"), ("section", "Section"),
        ("milestone", "Milestone"), ("other", "Other"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let project = viewModel.project {
                    overviewHeader(project: project)
                    HStack(alignment: .top, spacing: 14) {
                        upNextCard.frame(maxWidth: .infinity, alignment: .topLeading)
                        recentActivityCard.frame(maxWidth: .infinity, alignment: .topLeading)
                    }
                    peopleCard(project: project)
                    elementsCard
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
        }
        .task(id: viewModel.project?.id) {
            // Pull server-side activity (task history + file uploads +
            // collaborator joins) and seed `recentActivity`. In-session
            // logActivity() calls keep working as optimistic prepends.
            await viewModel.loadProjectActivity()
        }
    }

    private func overviewHeader(project: MWProject) -> some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(project.title)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)
                HStack(spacing: 10) {
                    TaskProgressBar(tasks: viewModel.tasks)
                        .frame(width: 180)
                    headerChip(icon: "doc", label: "\(viewModel.files.count) files")
                    headerChip(icon: "person.2", label: "\(project.collaborators?.count ?? 0) collaborators")
                }
            }
            Spacer()
            Menu {
                Button("PDF") { onExport("pdf") }
                Button("Markdown") { onExport("md") }
                Button("DOCX") { onExport("docx") }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "square.and.arrow.up").font(.system(size: 11))
                    Text("Export").font(.system(size: 11, weight: .medium))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.matcha600)
                .cornerRadius(5)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Export the project as PDF, Markdown, or DOCX")
        }
    }

    private func headerChip(icon: String, label: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9))
            Text(label).font(.system(size: 10))
        }
        .foregroundColor(.white.opacity(0.55))
    }

    private var upNextCard: some View {
        let upcoming = upcomingTasks()
        return VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "UP NEXT", trailing: upcoming.isEmpty ? nil : "\(upcoming.count)")
            if upcoming.isEmpty {
                Text("No open tasks. Add one in Kanban.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(upcoming) { task in
                    Button {
                        collabPanel = .kanban
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 8) {
                                Circle().fill(priorityColor(task.priority)).frame(width: 6, height: 6)
                                Text(task.title)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                                    .lineLimit(1)
                                Spacer()
                                if let due = task.dueDate, !due.isEmpty {
                                    Text(due.prefix(10))
                                        .font(.system(size: 9))
                                        .foregroundColor(.white.opacity(0.4))
                                }
                            }
                            if let note = task.progressNote,
                               !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Text(note)
                                    .font(.system(size: 10))
                                    .italic()
                                    .foregroundColor(.white.opacity(0.5))
                                    .lineLimit(1)
                                    .padding(.leading, 14)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private var recentActivityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "RECENT ACTIVITY", trailing: nil)
            if viewModel.recentActivity.isEmpty {
                Text("No activity yet this session.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(viewModel.recentActivity.prefix(5)) { item in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: item.icon)
                            .font(.system(size: 10))
                            .foregroundColor(.matcha500)
                            .frame(width: 12)
                        Text(item.text)
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.75))
                            .lineLimit(2)
                        Spacer()
                        Text(relativeTime(from: item.timestamp))
                            .font(.system(size: 9))
                            .foregroundColor(.white.opacity(0.4))
                    }
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private func peopleCard(project: MWProject) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                cardHeader(title: "PEOPLE", trailing: "\(project.collaborators?.count ?? 0)")
                Spacer()
                Button { showCollaborators = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "person.badge.plus").font(.system(size: 10))
                        Text("Invite").font(.system(size: 11, weight: .medium))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(Color.matcha600)
                    .cornerRadius(5)
                }
                .buttonStyle(.plain)
                .help("Invite a collaborator")
            }
            if let collabs = project.collaborators, !collabs.isEmpty {
                ForEach(collabs) { c in
                    HStack(spacing: 8) {
                        Circle().fill(Color.matcha500).frame(width: 22, height: 22)
                            .overlay(Text(String(c.name.prefix(1)).uppercased())
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(.white))
                        VStack(alignment: .leading, spacing: 1) {
                            Text(c.name).font(.system(size: 12)).foregroundColor(.white)
                            Text(c.email).font(.system(size: 10)).foregroundColor(.secondary)
                        }
                        Spacer()
                        if c.role == "owner" {
                            Text("Owner")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(.matcha500)
                        }
                    }
                    .padding(.vertical, 2)
                }
            } else {
                Text("No collaborators yet — click Invite to add someone.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    // MARK: - Elements card

    private var canEditElements: Bool {
        let role = viewModel.myRole
        return role == "owner" || role == "editor" || role == nil
    }

    private var elementsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                cardHeader(title: "ELEMENTS", trailing: viewModel.elements.isEmpty ? nil : "\(viewModel.elements.count)")
                Spacer()
                if canEditElements {
                    Button {
                        newElementName = ""
                        newElementKind = nil
                        newElementAssignedTo = nil
                        showAddElement = true
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "plus").font(.system(size: 10))
                            Text("Add").font(.system(size: 11, weight: .medium))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 4)
                        .background(Color.matcha600)
                        .cornerRadius(5)
                    }
                    .buttonStyle(.plain)
                }
            }

            if viewModel.elements.isEmpty && !showAddElement {
                Text("No elements yet. Add chapters, features, or sections to organize work.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            }

            if showAddElement {
                elementAddForm
            }

            ForEach(viewModel.elements) { el in
                if editingElement?.id == el.id {
                    elementEditForm(el)
                } else {
                    elementRow(el)
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    @ViewBuilder
    private var elementAddForm: some View {
        VStack(alignment: .leading, spacing: 6) {
            TextField("Element name", text: $newElementName)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white)
                .padding(6)
                .background(Color.zinc800)
                .cornerRadius(5)

            HStack(spacing: 8) {
                Picker("Kind", selection: $newElementKind) {
                    Text("No kind").tag(String?.none)
                    ForEach(elementKinds, id: \.key) { k in
                        Text(k.label).tag(String?.some(k.key))
                    }
                }
                .labelsHidden()
                .fixedSize()

                if !viewModel.collaborators.isEmpty {
                    Picker("Assign", selection: $newElementAssignedTo) {
                        Text("Unassigned").tag(String?.none)
                        ForEach(viewModel.collaborators) { c in
                            Text(c.name).tag(String?.some(c.userId))
                        }
                    }
                    .labelsHidden()
                    .fixedSize()
                }
                Spacer()
            }

            HStack {
                Button("Cancel") { showAddElement = false }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
                Button("Add") {
                    let n = newElementName.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !n.isEmpty else { return }
                    showAddElement = false
                    Task {
                        await viewModel.createElement(
                            name: n, kind: newElementKind,
                            description: nil, assignedTo: newElementAssignedTo
                        )
                    }
                }
                .buttonStyle(.plain)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.matcha500)
                .disabled(newElementName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(8)
        .background(Color.zinc800.opacity(0.5))
        .cornerRadius(6)
    }

    @ViewBuilder
    private func elementEditForm(_ el: MWProjectElement) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            TextField("Element name", text: $editElementName)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.white)
                .padding(6)
                .background(Color.zinc800)
                .cornerRadius(5)

            HStack(spacing: 8) {
                Picker("Kind", selection: $editElementKind) {
                    Text("No kind").tag(String?.none)
                    ForEach(elementKinds, id: \.key) { k in
                        Text(k.label).tag(String?.some(k.key))
                    }
                }
                .labelsHidden()
                .fixedSize()

                if !viewModel.collaborators.isEmpty {
                    Picker("Assign", selection: $editElementAssignedTo) {
                        Text("Unassigned").tag(String?.none)
                        ForEach(viewModel.collaborators) { c in
                            Text(c.name).tag(String?.some(c.userId))
                        }
                    }
                    .labelsHidden()
                    .fixedSize()
                }
                Spacer()
            }

            HStack {
                Button("Cancel") { editingElement = nil }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
                Button("Save") {
                    let n = editElementName.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !n.isEmpty else { return }
                    let target = el
                    editingElement = nil
                    Task {
                        await viewModel.updateElement(
                            target, name: n, kind: editElementKind,
                            description: nil, assignedTo: editElementAssignedTo
                        )
                    }
                }
                .buttonStyle(.plain)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.matcha500)
            }
        }
        .padding(8)
        .background(Color.zinc800.opacity(0.5))
        .cornerRadius(6)
    }

    @ViewBuilder
    private func elementRow(_ el: MWProjectElement) -> some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(el.name)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                HStack(spacing: 6) {
                    if let kind = el.kind {
                        let kLabel = elementKinds.first(where: { $0.key == kind })?.label ?? kind.capitalized
                        Text(kLabel)
                            .font(.system(size: 9, weight: .medium))
                            .foregroundColor(.matcha500)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.matcha500.opacity(0.12))
                            .cornerRadius(3)
                    }
                    if let name = el.assignedName, !name.isEmpty {
                        HStack(spacing: 3) {
                            Circle().fill(Color.matcha500.opacity(0.5)).frame(width: 10, height: 10)
                                .overlay(
                                    Text(String(name.prefix(1)).uppercased())
                                        .font(.system(size: 6, weight: .bold))
                                        .foregroundColor(.white)
                                )
                            Text(name)
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.6))
                        }
                    }
                }
            }
            Spacer()
            if canEditElements {
                HStack(spacing: 8) {
                    Button {
                        editElementName = el.name
                        editElementKind = el.kind
                        editElementAssignedTo = el.assignedTo
                        editingElement = el
                        showAddElement = false
                    } label: {
                        Image(systemName: "pencil")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)

                    Button {
                        Task { await viewModel.deleteElement(el) }
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 10))
                            .foregroundColor(.red.opacity(0.7))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, 3)
    }

    private func cardHeader(title: String, trailing: String?) -> some View {
        HStack {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.5)
            if let trailing {
                Text(trailing)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.zinc800.opacity(0.7))
                    .cornerRadius(3)
            }
            Spacer()
        }
    }

    private func priorityColor(_ priority: String) -> Color {
        switch priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .white.opacity(0.4)
        }
    }

    /// Top 5 open tasks sorted by priority bucket then due date.
    private func upcomingTasks() -> [MWProjectTask] {
        let priorityRank: (String) -> Int = { p in
            switch p {
            case "critical": return 0
            case "high": return 1
            case "medium": return 2
            case "low": return 3
            default: return 4
            }
        }
        return viewModel.tasks
            .filter { $0.status != "completed" }
            .sorted { a, b in
                let ar = priorityRank(a.priority), br = priorityRank(b.priority)
                if ar != br { return ar < br }
                return (a.dueDate ?? "9999-99-99") < (b.dueDate ?? "9999-99-99")
            }
            .prefix(5)
            .map { $0 }
    }

    private func relativeTime(from date: Date) -> String {
        let secs = Int(Date().timeIntervalSince(date))
        if secs < 60 { return "just now" }
        if secs < 3600 { return "\(secs/60)m" }
        if secs < 86400 { return "\(secs/3600)h" }
        return "\(secs/86400)d"
    }
}
