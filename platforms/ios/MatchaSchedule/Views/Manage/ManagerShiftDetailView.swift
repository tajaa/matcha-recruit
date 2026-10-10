import SwiftUI

/// One shift as its manager handles it: who is on it, filling it, moving
/// people, editing, publishing, cancelling.
struct ManagerShiftDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let shift: ScheduleShift
    let weekShifts: [ScheduleShift]
    let roster: [RosterMember]
    let jobs: [ScheduleJob]
    let location: ManagedLocation
    let weekStart: Date
    let canEdit: Bool
    let onChanged: () async -> Void
    @State private var busy = false
    @State private var error: String?
    @State private var force: ForcePrompt?
    /// The one sheet this screen presents, by what it shows.
    @State private var sheet: DetailSheet?

    private enum DetailSheet: Identifiable {
        case pick, edit
        case move(ShiftAssignment)

        var id: String {
            switch self {
            case .pick: "pick"
            case .edit: "edit"
            case .move(let person): "move-\(person.employee_id)"
            }
        }
    }
    @State private var confirmCancel = false
    @State private var confirmDelete = false

    private var isPublished: Bool { shift.status == "published" }
    private var isCancelled: Bool { shift.status == "cancelled" }
    private var job: ScheduleJob? { jobs.first { $0.id == shift.job_id } }

    var body: some View {
        List {
            GlassHero {
                VStack(alignment: .leading, spacing: 6) {
                    Text(WallClock.label(shift.starts_at, format: "EEEE, MMM d"))
                        .font(.app(.subheadline)).foregroundStyle(Color.secondary)
                    Text("\(WallClock.label(shift.starts_at, format: "h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                        .font(.inter(26, .bold)).monospacedDigit()
                    Text([shift.title, WallClock.duration(from: shift.starts_at, to: shift.ends_at)]
                        .compactMap { $0 }.joined(separator: " · "))
                        .font(.app(.subheadline)).foregroundStyle(Color.secondary)
                    HStack(spacing: 6) {
                        StatusPill(text: statusLabel, color: statusColor)
                        if shift.openSeats > 0 { StatusPill(text: "\(shift.openSeats) open", color: .brand) }
                    }
                    .padding(.top, 2)
                }
            }
            .bareRow(top: 8, bottom: 4)

            if !canEdit {
                Label("This shift has no store, so only a business admin can change it.", systemImage: "lock")
                    .font(.app(.subheadline)).foregroundStyle(Color.secondary)
                    .cardRow()
            }
            if let error {
                ErrorRow(message: error).cardRow()
            }

            SectionLabel(staffingLine)
            if shift.assignments.isEmpty {
                Text("Nobody is on this shift yet.")
                    .foregroundStyle(Color.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .cardRow()
            }
            ForEach(shift.assignments) { person in
                HStack(spacing: 12) {
                    Avatar(name: person.name, size: 32)
                    Text(person.name).font(.app(.body))
                    Spacer()
                    if canEdit && !isCancelled {
                        Menu {
                            Button { sheet = .move(person) } label: { Label("Move to another shift", systemImage: "arrow.right.arrow.left") }
                            Button(role: .destructive) { Task { await unassign(person) } } label: {
                                Label("Take off this shift", systemImage: "person.badge.minus")
                            }
                        } label: {
                            Image(systemName: "ellipsis.circle").font(.title3)
                        }
                        .accessibilityLabel("Options for \(person.name)")
                        .disabled(busy)
                    }
                }
                .cardRow()
            }
            if canEdit && !isCancelled {
                Button { sheet = .pick } label: {
                    Label(shift.openSeats > 0 ? "Fill an open seat" : "Add someone", systemImage: "person.badge.plus")
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .disabled(busy)
                .cardRow()
                .accessibilityIdentifier("shift.addPerson")
            }

            if let notes = shift.notes, !notes.isEmpty {
                SectionLabel("Notes")
                Text(notes).cardRow()
            }

            if canEdit && !isCancelled {
                SectionLabel("Shift")
                if shift.status == "draft" {
                    Button { Task { await publish() } } label: {
                        Label("Publish this shift", systemImage: "paperplane").frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .disabled(busy)
                    .cardRow()
                }
                Button { sheet = .edit } label: {
                    Label("Edit time, job or staffing", systemImage: "pencil").frame(maxWidth: .infinity, alignment: .leading)
                }
                .disabled(busy)
                .cardRow()
                if isPublished {
                    Button(role: .destructive) { confirmCancel = true } label: {
                        Label("Cancel shift", systemImage: "xmark.circle").frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .disabled(busy)
                    .cardRow()
                } else {
                    Button(role: .destructive) { confirmDelete = true } label: {
                        Label("Delete draft", systemImage: "trash").frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .disabled(busy)
                    .cardRow()
                }
            }
        }
        .listStyle(.plain)
        .appBackdrop()
        .overlay { if busy { ProgressView() } }
        .navigationTitle(shift.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } }
        }
        .confirmationDialog("Cancel this shift?", isPresented: $confirmCancel, titleVisibility: .visible) {
            Button("Cancel shift", role: .destructive) { Task { await cancelShift() } }
        } message: {
            Text("It stays on the schedule as cancelled. A cancelled shift can't be brought back.")
        }
        .confirmationDialog("Delete this draft?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { Task { await delete() } }
        }
        .sheet(item: $sheet) { item in
            NavigationStack {
                switch item {
                case .pick:
                    AssigneePickerView(shift: shift, roster: roster, job: job, location: location, weekStart: weekStart) { person in
                        await assign(person)
                    }
                case .edit:
                    ShiftEditorView(mode: .edit(shift), location: location, jobs: jobs, onSaved: onChanged)
                case .move(let person):
                    MoveAssignmentView(person: person, from: shift, candidates: moveTargets(for: person)) { target in
                        await move(person, to: target)
                    }
                }
            }
        }
        .forcePrompt($force) { message in
            error = message
            Task { await onChanged() }
        }
    }

    private var statusLabel: String {
        switch shift.status {
        case "draft": "Draft"
        case "published": "Published"
        case "cancelled": "Cancelled"
        default: shift.status.capitalized
        }
    }

    private var statusColor: Color {
        switch shift.status {
        case "draft": .orange
        case "published": .brand
        default: .secondary
        }
    }

    private var staffingLine: String {
        guard let required = shift.required_staff else { return "Crew" }
        return "Crew · \(shift.assignments.count) of \(required)"
    }

    /// Other live shifts at this store the person is not already on.
    private func moveTargets(for person: ShiftAssignment) -> [ScheduleShift] {
        weekShifts.filter { other in
            other.id != shift.id && other.status != "cancelled"
                && (other.location_id == location.id || other.location_id == nil)
                && !other.assignments.contains { $0.employee_id == person.employee_id }
        }
    }

    // MARK: Writes

    /// Each write reloads the week itself once it lands (a forced retry runs
    /// later, from the prompt). A failure reloads too: what is on screen may
    /// be stale, which is the usual reason it failed.
    private func perform(_ work: () async throws -> Void) async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            try await work()
        } catch {
            self.error = error.localizedDescription
            await onChanged()
        }
    }

    /// Fixes a meal-break advisory by letting the server set the legal break.
    private var addRequiredBreak: () async throws -> Void {
        let id = shift.id
        return { try await ManagerService.updateShift(id, ShiftPatch(break_mode: "auto"), force: true) }
    }

    private func assign(_ person: RosterMember) async {
        let shiftID = shift.id
        await perform {
            try await ForcePrompt.run($force, fixBreak: addRequiredBreak) { force in
                try await ManagerService.assign(person.id, to: shiftID, force: force)
                await onChanged()
            }
        }
    }

    private func unassign(_ person: ShiftAssignment) async {
        let shiftID = shift.id
        await perform {
            try await ForcePrompt.run($force) { force in
                try await ManagerService.unassign(person.employee_id, from: shiftID, force: force)
                await onChanged()
            }
        }
    }

    private func move(_ person: ShiftAssignment, to target: ScheduleShift) async {
        let shiftID = shift.id
        await perform {
            try await ForcePrompt.run($force) { force in
                try await ManagerService.move(person.employee_id, from: shiftID, to: target.id, force: force)
                await onChanged()
            }
        }
    }

    private func publish() async {
        let shiftID = shift.id
        await perform {
            try await ManagerService.publishShift(shiftID)
            await onChanged()
        }
    }

    private func cancelShift() async {
        let shiftID = shift.id
        await perform {
            try await ForcePrompt.run($force) { force in
                try await ManagerService.updateShift(shiftID, ShiftPatch(status: "cancelled"), force: force)
                await onChanged()
            }
        }
    }

    private func delete() async {
        let shiftID = shift.id
        await perform {
            try await ForcePrompt.run($force) { force in
                try await ManagerService.deleteShift(shiftID, force: force)
                await onChanged()
                dismiss()
            }
        }
    }
}

// MARK: - Picking someone

/// The store's roster for one shift: qualified people first, with this
/// week's load and any approved time away on the day.
struct AssigneePickerView: View {
    @Environment(\.dismiss) private var dismiss
    let shift: ScheduleShift
    let roster: [RosterMember]
    let job: ScheduleJob?
    let location: ManagedLocation
    let weekStart: Date
    let onPick: (RosterMember) async -> Void
    @State private var planning: [String: PlanningPerson] = [:]
    @State private var search = ""

    private var dayKey: String { WallClock.dayKey(shift.starts_at) }

    private var candidates: [RosterMember] {
        let onShift = Set(shift.assignments.map(\.employee_id))
        let query = search.trimmingCharacters(in: .whitespaces).lowercased()
        return roster
            .filter { !onShift.contains($0.id) && (query.isEmpty || $0.name.lowercased().contains(query)) }
            .sorted { lhs, rhs in
                let left = (qualified(lhs) ? 0 : 1, away(lhs) ? 1 : 0, planning[lhs.id]?.load?.minutes ?? 0)
                let right = (qualified(rhs) ? 0 : 1, away(rhs) ? 1 : 0, planning[rhs.id]?.load?.minutes ?? 0)
                return left == right ? lhs.name < rhs.name : left < right
            }
    }

    private func qualified(_ person: RosterMember) -> Bool { job?.qualifies(person.id) ?? true }
    private func away(_ person: RosterMember) -> Bool { planning[person.id]?.isAway(on: dayKey) == true }

    var body: some View {
        List {
            if roster.isEmpty {
                Text("No one works at \(location.displayName) yet.")
                    .foregroundStyle(Color.secondary).cardRow()
            }
            ForEach(candidates) { person in
                Button {
                    Task {
                        dismiss()
                        await onPick(person)
                    }
                } label: {
                    HStack(spacing: 12) {
                        Avatar(name: person.name, size: 34)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(person.name).font(.app(.headline)).foregroundStyle(Color.primary)
                            if let line = planning[person.id]?.loadLine {
                                Text("This week: \(line)").font(.app(.subheadline)).foregroundStyle(Color.secondary)
                            }
                            HStack(spacing: 6) {
                                if !qualified(person) { StatusPill(text: "Not qualified for \(job?.name ?? "this job")", color: .orange) }
                                if away(person) { StatusPill(text: "Time off that day", color: .red) }
                            }
                        }
                        Spacer(minLength: 0)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .cardRow()
            }
        }
        .listStyle(.plain)
        .appBackdrop()
        .searchable(text: $search, prompt: "Search crew")
        .navigationTitle("Who's working?")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
        }
        .task {
            // Guidance only: the picker works without it.
            if let inputs = try? await ManagerService.planningInputs(location: location.id, weekStart: weekStart) {
                planning = Dictionary(inputs.roster.map { ($0.employee_id, $0) }, uniquingKeysWith: { first, _ in first })
            }
        }
    }
}

// MARK: - Moving someone

struct MoveAssignmentView: View {
    @Environment(\.dismiss) private var dismiss
    let person: ShiftAssignment
    let from: ScheduleShift
    let candidates: [ScheduleShift]
    let onPick: (ScheduleShift) async -> Void

    var body: some View {
        List {
            if candidates.isEmpty {
                Text("There's no other shift this week to move \(person.name) to.")
                    .foregroundStyle(Color.secondary).cardRow()
            }
            ForEach(candidates) { target in
                Button {
                    Task {
                        dismiss()
                        await onPick(target)
                    }
                } label: {
                    ShiftRow(shift: target, location: nil, showsCrew: true, showsDay: true, showsChevron: false)
                        .contentShape(Rectangle())
                }
                .cardRow()
            }
        }
        .listStyle(.plain)
        .appBackdrop()
        .navigationTitle("Move \(person.name.split(separator: " ").first.map(String.init) ?? person.name)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
        }
    }
}
