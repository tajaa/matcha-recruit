import SwiftUI

struct CollabOverviewView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @Binding var collabPanel: CollabRightPanel
    @Binding var showCollaborators: Bool
    let onExport: (String) -> Void

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
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
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
