import SwiftUI

enum ShiftDetailMode: Equatable { case mine, team, open }

struct ShiftDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let shift: ScheduleShift
    let location: String?
    let employeeID: String
    let mode: ShiftDetailMode
    let onChanged: () async -> Void
    @State private var action: ShiftAction?
    @State private var submitted = false

    private var part: DayPart { DayPart(wallClockISO: shift.starts_at) }

    private var myAssignment: ShiftAssignment? {
        shift.assignments.first { $0.employee_id == employeeID }
    }

    private var crew: [ShiftAssignment] {
        shift.assignments.filter { $0.employee_id != employeeID }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header.rise()
                details.rise(delay: 0.04)
                if let note = myAssignment?.manager_note,
                   !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    managerNote(note).rise(delay: 0.08)
                }
                if let breaks = myAssignment?.planned_breaks, !breaks.isEmpty {
                    plannedBreaks(breaks).rise(delay: 0.1)
                }
                if !crew.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(title: mode == .mine ? "Working with you" : "On this shift")
                        VStack(spacing: 0) {
                            ForEach(Array(crew.enumerated()), id: \.element.id) { index, person in
                                HStack(spacing: 12) {
                                    Avatar(name: person.name, size: 34)
                                    Text(person.name).font(TypeScale.callout).foregroundStyle(Palette.ink)
                                    Spacer()
                                }
                                .padding(.vertical, 10)
                                if index < crew.count - 1 { Divider().overlay(Palette.inkFaint.opacity(0.3)) }
                            }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 4)
                        .glassSurface(elevated: false)
                    }
                    .rise(delay: 0.12)
                }
                if let notes = shift.notes, !notes.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(title: "Shift notes")
                        Text(notes).font(TypeScale.body).foregroundStyle(Palette.ink)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(16).glassSurface(elevated: false)
                    }
                }
                actions.rise(delay: 0.14)
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.top, 8)
            .padding(.bottom, 30)
        }
        .scrollIndicators(.hidden)
        .ambientBackground(part)
        .navigationTitle("Shift")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { dismiss() } label: { Text("Done").font(TypeScale.callout) }
            }
        }
        .sheet(item: $action) { selection in
            NavigationStack {
                RequestComposerView(action: selection, shift: shift) {
                    withAnimation(.spring(response: 0.5, dampingFraction: 0.8)) { submitted = true }
                    Task { await onChanged() }
                }
            }
            .presentationCornerRadius(32)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(part.label.uppercased() + " · " + WallClock.label(shift.starts_at, format: "EEEE, MMM d").uppercased(),
                  systemImage: part.symbol)
                .font(TypeScale.eyebrow).tracking(1.4)
                .foregroundStyle(part.color)
            Text("\(WallClock.label(shift.starts_at, format: "h:mm")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                .font(TypeScale.hero)
                .monospacedDigit()
                .foregroundStyle(Palette.ink)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
            Text(shift.title).font(TypeScale.title).foregroundStyle(Palette.ink)
            HStack(spacing: 8) {
                if let duration = WallClock.duration(from: shift.starts_at, to: shift.ends_at) {
                    StatusPill(text: duration, color: part.color)
                }
                if mode == .open { StatusPill(text: "Open seat", color: Palette.leaf) }
                if shift.has_conflict == true { StatusPill(text: "Overlaps your shift", color: Palette.amber) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(alignment: .bottomTrailing) {
            Image(systemName: part.symbol)
                .font(.system(size: 140))
                .foregroundStyle(part.color.opacity(0.14))
                .offset(x: 30, y: 36)
                .accessibilityHidden(true)
        }
        .clipShape(RoundedRectangle(cornerRadius: Metrics.heroRadius, style: .continuous))
        .glassSurface(cornerRadius: Metrics.heroRadius, tint: part.color)
    }

    private var details: some View {
        VStack(spacing: 0) {
            DetailRow(symbol: "calendar", label: "Date",
                      value: WallClock.label(shift.starts_at, format: "EEEE, MMMM d"))
            if let location { rowDivider; DetailRow(symbol: "mappin.and.ellipse", label: "Location", value: location) }
            if let department = shift.department, !department.isEmpty {
                rowDivider; DetailRow(symbol: "square.grid.2x2", label: "Department", value: department)
            }
            if let minutes = shift.break_minutes, minutes > 0 {
                rowDivider; DetailRow(symbol: "cup.and.saucer", label: "Break", value: "\(minutes) minutes")
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 4)
        .glassSurface(elevated: false)
    }

    private var rowDivider: some View {
        Divider().overlay(Palette.inkFaint.opacity(0.3)).padding(.leading, 34)
    }

    private func managerNote(_ note: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("From your manager", systemImage: "quote.opening")
                .font(TypeScale.eyebrow).tracking(1.2)
                .foregroundStyle(Palette.leaf)
                .textCase(.uppercase)
            Text(note).font(TypeScale.body).foregroundStyle(Palette.ink)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassSurface(tint: Palette.leaf, elevated: false)
    }

    private func plannedBreaks(_ breaks: [PlannedBreak]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(title: "Your breaks")
            ScrollView(.horizontal) {
                HStack(spacing: 10) {
                    ForEach(breaks) { item in
                        HStack(spacing: 10) {
                            Image(systemName: item.kind == "meal" ? "fork.knife" : "cup.and.saucer.fill")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(part.color)
                                .frame(width: 32, height: 32)
                                .background(part.color.opacity(0.14), in: Circle())
                            VStack(alignment: .leading, spacing: 1) {
                                Text(WallClock.clockTime(item.start_local))
                                    .font(TypeScale.headline).monospacedDigit().foregroundStyle(Palette.ink)
                                Text("\(item.kind.capitalized) · \(item.duration_minutes) min")
                                    .font(TypeScale.caption).foregroundStyle(Palette.inkSoft)
                            }
                        }
                        .padding(.vertical, 10).padding(.leading, 10).padding(.trailing, 16)
                        .glassSurface(cornerRadius: 18, elevated: false)
                    }
                }
                .padding(.vertical, 2)
            }
            .scrollIndicators(.hidden)
        }
    }

    @ViewBuilder
    private var actions: some View {
        if submitted {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(Palette.leaf)
                    .symbolEffect(.bounce, value: submitted)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Sent to your manager").font(TypeScale.headline).foregroundStyle(Palette.ink)
                    Text("Track it in Requests.").font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
                }
                Spacer()
            }
            .padding(16)
            .glassSurface(tint: Palette.leaf)
            .transition(.scale(scale: 0.95).combined(with: .opacity))
            .sensoryFeedback(.success, trigger: submitted)
        } else if mode == .mine {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(title: "Need a change?")
                HStack(spacing: 10) {
                    ActionTile(symbol: "arrow.left.arrow.right", title: "Swap") { action = .swap }
                    ActionTile(symbol: "hand.raised.fill", title: "Offer up") { action = .pickup }
                    ActionTile(symbol: "minus.circle.fill", title: "Drop") { action = .drop }
                }
            }
        } else if mode == .open {
            Button { action = .claim } label: {
                Label("Claim this shift", systemImage: "plus.circle.fill")
            }
            .buttonStyle(PrimaryButtonStyle())
            .accessibilityIdentifier("shift.claim")
        }
    }
}

private struct DetailRow: View {
    let symbol: String
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Palette.inkSoft)
                .frame(width: 22)
            Text(label).font(TypeScale.callout).foregroundStyle(Palette.inkSoft)
            Spacer()
            Text(value).font(TypeScale.callout).foregroundStyle(Palette.ink).multilineTextAlignment(.trailing)
        }
        .padding(.vertical, 13)
        .accessibilityElement(children: .combine)
    }
}

struct ActionTile: View {
    let symbol: String
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: symbol)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Palette.leaf)
                    .frame(width: 42, height: 42)
                    .background(Palette.leaf.opacity(0.13), in: Circle())
                Text(title).font(TypeScale.callout).foregroundStyle(Palette.ink)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .glassSurface(cornerRadius: 20)
        }
        .buttonStyle(PressableStyle())
    }
}
