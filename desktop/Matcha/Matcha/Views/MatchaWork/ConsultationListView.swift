import SwiftUI

struct ConsultationListView: View {
    @Environment(AppState.self) private var appState
    var showHeader: Bool = true
    @State private var projects: [MWProject] = []
    @State private var isLoading = true
    @State private var showCreate = false
    @State private var stageFilter: String? = nil   // nil = all

    private let stageFilters: [(label: String, value: String?)] = [
        ("All", nil),
        ("Leads", "lead"),
        ("Proposals", "proposal"),
        ("Active", "active"),
        ("Completed", "completed"),
    ]

    private var filtered: [MWProject] {
        guard let stage = stageFilter else { return projects }
        return projects.filter { p in
            let d = MWConsultationData.from(projectData: p.projectData)
            return d.stage == stage
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if showHeader { header }
            filterBar
            Divider().opacity(0.3)
            content
        }
        .background(Color.appBackground)
        .task { await load() }
        .onChange(of: appState.channelsListGeneration) { _, _ in
            Task { await load() }
        }
        .sheet(isPresented: $showCreate) {
            NewConsultationSheet { created in
                Task {
                    await load()
                    await MainActor.run {
                        appState.selectedProjectId = created.id
                        appState.selectedThreadId = nil
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if isLoading {
            Spacer()
            ProgressView().tint(.secondary)
            Spacer()
        } else if filtered.isEmpty {
            emptyView
        } else {
            List(filtered, selection: Binding(
                get: { appState.selectedProjectId },
                set: {
                    appState.selectedProjectId = $0
                    appState.selectedThreadId = nil
                    appState.showSkills = false
                }
            )) { project in
                row(for: project).tag(project.id)
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
        }
    }

    private var header: some View {
        HStack {
            Text("Consultations")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
            Button { showCreate = true } label: {
                Image(systemName: "plus")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(width: 24, height: 24)
                    .background(Color.zinc800)
                    .cornerRadius(6)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(stageFilters, id: \.label) { f in
                    let active = stageFilter == f.value
                    Button {
                        stageFilter = f.value
                    } label: {
                        Text(f.label)
                            .font(.system(size: 10, weight: active ? .semibold : .regular))
                            .foregroundColor(active ? Color.matcha500 : .secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(active ? Color.matcha500.opacity(0.12) : Color.clear)
                            .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10)
            .padding(.bottom, 6)
        }
    }

    private var emptyView: some View {
        VStack(spacing: 8) {
            Spacer()
            Image(systemName: "person.crop.rectangle.stack")
                .font(.system(size: 22))
                .foregroundColor(.secondary)
            Text("No consultations")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            Button {
                showCreate = true
            } label: {
                Text("Create one")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Color.matcha500)
            }
            .buttonStyle(.plain)
            Spacer()
        }
    }

    private func row(for project: MWProject) -> some View {
        let data = MWConsultationData.from(projectData: project.projectData)
        return VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(project.title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Spacer(minLength: 4)
                stageChip(data.stage)
                if let days = data.staleDays, days >= 14 {
                    Text("⚠ \(days)d")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundColor(.orange)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.orange.opacity(0.12))
                        .cornerRadius(3)
                }
            }
            subline(data)
        }
        .padding(.vertical, 2)
        .contextMenu {
            Button("Archive") {
                Task {
                    try? await MatchaWorkService.shared.archiveProject(id: project.id)
                    await load()
                }
            }
        }
    }

    @ViewBuilder
    private func subline(_ data: MWConsultationData) -> some View {
        let hrs = data.unbilledHours
        let cents = data.unbilledCents
        let open = data.openActionItems.count
        let pending = data.pendingActionItems.count
        HStack(spacing: 6) {
            if cents > 0 {
                Text(String(format: "%.1f hr / $%.0f unbilled", hrs, Double(cents) / 100.0))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            } else if let org = data.client.org, !org.isEmpty {
                Text(org)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 4)
            if pending > 0 {
                Text("✨ \(pending)")
                    .font(.system(size: 10))
                    .foregroundColor(Color.matcha500)
            } else if open > 0 {
                Text("\(open) open")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
    }

    private func stageChip(_ stage: String) -> some View {
        let (bg, fg) = stageColors(stage)
        return Text(stage)
            .font(.system(size: 9, weight: .medium))
            .foregroundColor(fg)
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(bg)
            .cornerRadius(3)
    }

    private func stageColors(_ stage: String) -> (Color, Color) {
        switch stage {
        case "lead": return (Color.gray.opacity(0.15), .gray)
        case "proposal": return (Color.blue.opacity(0.15), .blue)
        case "active": return (Color.matcha500.opacity(0.12), Color.matcha500)
        case "completed": return (Color.purple.opacity(0.15), .purple)
        case "archived": return (Color.white.opacity(0.06), .secondary)
        default: return (Color.white.opacity(0.08), .secondary)
        }
    }

    private func load() async {
        do {
            let all = try await MatchaWorkService.shared.listProjects()
            let mine = all.filter { $0.projectType == "consultation" }
            await MainActor.run {
                projects = mine
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}
