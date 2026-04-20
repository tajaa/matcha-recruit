import SwiftUI

struct ConsultationDetailView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @Environment(AppState.self) private var appState

    @State private var tab: Tab = .overview
    @State private var showLogSession = false

    enum Tab: String, CaseIterable, Identifiable {
        case overview, sessions, chats, actions
        var id: String { rawValue }
        var label: String {
            switch self {
            case .overview: return "Overview"
            case .sessions: return "Sessions"
            case .chats: return "Chats"
            case .actions: return "Action items"
            }
        }
    }

    private var data: MWConsultationData {
        viewModel.consultationData
    }

    var body: some View {
        VStack(spacing: 0) {
            tabBar
            Divider()
            switch tab {
            case .overview:
                overviewTab
            case .sessions:
                sessionsTab
            case .chats:
                chatsTab
            case .actions:
                actionsTab
            }
        }
        .background(.ultraThinMaterial)
        .sheet(isPresented: $showLogSession) {
            LogSessionSheet(viewModel: viewModel)
        }
    }

    // MARK: - Tab bar

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(Tab.allCases) { t in
                Button {
                    tab = t
                } label: {
                    VStack(spacing: 3) {
                        Text(t.label)
                            .font(.system(size: 11, weight: tab == t ? .semibold : .regular))
                            .foregroundColor(tab == t ? Color.matcha500 : .white.opacity(0.55))
                        Rectangle()
                            .fill(tab == t ? Color.matcha500 : Color.clear)
                            .frame(height: 1)
                    }
                    .padding(.horizontal, 14)
                    .padding(.top, 10)
                    .padding(.bottom, 4)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
    }

    // MARK: - Overview

    private var overviewTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                clientCard
                statsStrip
                quickActions
            }
            .padding(16)
        }
    }

    private var clientCard: some View {
        let c = data.client
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 10) {
                Circle()
                    .fill(Color.matcha500.opacity(0.18))
                    .frame(width: 36, height: 36)
                    .overlay(
                        Text((c.name ?? "?").prefix(1).uppercased())
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Color.matcha500)
                    )
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.name ?? "Untitled client")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                    if let org = c.org, !org.isEmpty {
                        Text(org)
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.55))
                    }
                }
                Spacer()
                stagePicker
            }
            if let pc = c.primaryContact {
                HStack(spacing: 10) {
                    if let e = pc.email, !e.isEmpty {
                        Label(e, systemImage: "envelope")
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.7))
                    }
                    if let p = pc.phone, !p.isEmpty {
                        Label(p, systemImage: "phone")
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.7))
                    }
                }
            }
            if !data.tags.isEmpty {
                HStack(spacing: 4) {
                    ForEach(data.tags, id: \.self) { t in
                        Text(t)
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.7))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.white.opacity(0.08))
                            .cornerRadius(3)
                    }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.2))
        .cornerRadius(8)
    }

    private var stagePicker: some View {
        Menu {
            ForEach(["lead", "proposal", "active", "completed", "archived"], id: \.self) { s in
                Button(s) { Task { await viewModel.patchConsultation(stage: s) } }
            }
        } label: {
            Text(data.stage)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(Color.matcha500)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Color.matcha500.opacity(0.12))
                .cornerRadius(4)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private var statsStrip: some View {
        HStack(spacing: 8) {
            switch data.engagement.pricingModel {
            case "hourly":
                statCard(value: String(format: "%.1f hrs", data.unbilledHours), label: "Unbilled", color: .orange)
                statCard(value: String(format: "$%.0f", Double(data.unbilledCents) / 100.0), label: "Owed", color: Color.matcha500)
            case "retainer":
                let monthly = Double(data.engagement.monthlyRetainerCents ?? 0) / 100.0
                statCard(value: String(format: "$%.0f", monthly), label: "Monthly retainer", color: Color.matcha500)
                statCard(value: String(format: "%.1f hrs", data.sessions.filter { $0.billable }.reduce(0.0) { $0 + Double($1.durationMin ?? 0) / 60.0 }), label: "Hours logged", color: .orange)
            case "fixed":
                let fee = Double(data.engagement.fixedFeeCents ?? 0) / 100.0
                statCard(value: String(format: "$%.0f", fee), label: "Project fee", color: Color.matcha500)
                statCard(value: "\(data.sessions.count)", label: "Sessions", color: .orange)
            default:  // "free"
                statCard(value: "\(data.sessions.count)", label: "Sessions", color: Color.matcha500)
                statCard(value: String(format: "%.1f hrs", data.sessions.reduce(0.0) { $0 + Double($1.durationMin ?? 0) / 60.0 }), label: "Hours", color: .orange)
            }
            statCard(value: "\(data.openActionItems.count)", label: "Open items", color: .blue)
            statCard(value: data.staleDays.map { "\($0)d" } ?? "—", label: "Last contact", color: (data.staleDays ?? 0) >= 14 ? .orange : .white)
        }
    }

    private func statCard(value: String, label: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(color)
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.5))
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.15))
        .cornerRadius(6)
    }

    private var quickActions: some View {
        HStack(spacing: 8) {
            Button { showLogSession = true } label: {
                Label("Log session", systemImage: "clock.badge.checkmark")
                    .font(.system(size: 11, weight: .medium))
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .foregroundColor(Color.matcha500)
                    .background(Color.matcha500.opacity(0.12))
                    .cornerRadius(6)
            }
            .buttonStyle(.plain)

            Button {
                let pid = viewModel.project?.id ?? ""
                NotificationCenter.default.post(name: .mwConsultationPrepRequest, object: pid)
            } label: {
                Label("Prep for next session", systemImage: "sparkles")
                    .font(.system(size: 11, weight: .medium))
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .foregroundColor(.white.opacity(0.75))
                    .background(Color.white.opacity(0.08))
                    .cornerRadius(6)
            }
            .buttonStyle(.plain)
            Spacer()
        }
    }

    // MARK: - Sessions

    private var sessionsTab: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("\(data.sessions.count) session\(data.sessions.count == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.5))
                Spacer()
                Button { showLogSession = true } label: {
                    Text("+ log session")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color.matcha500)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 14)
            .padding(.top, 10)
            .padding(.bottom, 6)

            if data.sessions.isEmpty {
                emptyState(icon: "clock", label: "No sessions logged yet")
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(data.sessions) { s in
                            sessionRow(s)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.bottom, 12)
                }
            }
        }
    }

    private func sessionRow(_ s: MWSession) -> some View {
        let dt = parseMWDate(s.at)
        let dateStr = dt.map { DateFormatter.shortDateTime.string(from: $0) } ?? s.at
        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text(dateStr)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white)
                if let d = s.durationMin {
                    Text("· \(d) min")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.55))
                }
                if s.billable {
                    Text("billable")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundColor(.orange)
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(Color.orange.opacity(0.12))
                        .cornerRadius(3)
                }
                if let inv = s.invoiceId, !inv.isEmpty {
                    Text("invoiced")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundColor(.green)
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(Color.green.opacity(0.12))
                        .cornerRadius(3)
                }
                Spacer()
                Menu {
                    Button("Delete", role: .destructive) {
                        Task { await viewModel.deleteSession(sessionId: s.id) }
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.4))
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
            }
            if let n = s.notes, !n.isEmpty {
                Text(n)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.7))
                    .lineLimit(4)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.15))
        .cornerRadius(6)
    }

    // MARK: - Chats

    private var chatsTab: some View {
        let chats = viewModel.project?.chats ?? []
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("\(chats.count) chat\(chats.count == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.5))
                Spacer()
                Button {
                    Task { await viewModel.createChat(title: nil) }
                } label: {
                    Text("+ new chat")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color.matcha500)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 14).padding(.top, 10).padding(.bottom, 6)

            if chats.isEmpty {
                emptyState(icon: "bubble.left", label: "No chats yet")
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(chats, id: \.id) { t in
                            Button {
                                viewModel.activeChatId = t.id
                            } label: {
                                HStack {
                                    Image(systemName: "bubble.left")
                                        .font(.system(size: 11))
                                        .foregroundColor(.secondary)
                                    Text(t.title)
                                        .font(.system(size: 12))
                                        .foregroundColor(.white)
                                        .lineLimit(1)
                                    Spacer()
                                }
                                .padding(8)
                                .background(viewModel.activeChatId == t.id ? Color.matcha500.opacity(0.12) : Color.black.opacity(0.12))
                                .cornerRadius(5)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 14).padding(.bottom, 12)
                }
            }
        }
    }

    // MARK: - Action items

    private var actionsTab: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !data.pendingActionItems.isEmpty {
                pendingSection
            }
            openAndClosedSection
        }
    }

    private var pendingSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("PROPOSED BY AI — CONFIRM TO ADD")
                .font(.system(size: 9, weight: .medium))
                .tracking(0.5)
                .foregroundColor(Color.matcha500)
                .padding(.horizontal, 14).padding(.top, 10)
            ForEach(data.pendingActionItems) { item in
                HStack(spacing: 6) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 10))
                        .foregroundColor(Color.matcha500)
                    Text(item.text)
                        .font(.system(size: 12))
                        .foregroundColor(.white)
                        .lineLimit(3)
                    Spacer()
                    Button("Accept") {
                        Task { await viewModel.confirmActionItem(itemId: item.id) }
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Color.matcha500)
                    Button("Dismiss") {
                        Task { await viewModel.dismissActionItem(itemId: item.id) }
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.matcha500.opacity(0.08))
                .cornerRadius(5)
                .padding(.horizontal, 14)
            }
            Divider().opacity(0.2).padding(.vertical, 6)
        }
    }

    private var openAndClosedSection: some View {
        let open = data.actionItems.filter { !$0.pendingConfirmation && !$0.completed }
        let done = data.actionItems.filter { $0.completed }
        return ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                Text("\(open.count) open")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.horizontal, 14).padding(.top, 4)
                if open.isEmpty && done.isEmpty && data.pendingActionItems.isEmpty {
                    emptyState(icon: "checkmark.circle", label: "No action items")
                } else {
                    ForEach(open) { item in itemRow(item, completed: false) }
                    if !done.isEmpty {
                        Text("COMPLETED").font(.system(size: 9, weight: .medium)).tracking(0.5)
                            .foregroundColor(.white.opacity(0.3))
                            .padding(.horizontal, 14).padding(.top, 8)
                        ForEach(done) { item in itemRow(item, completed: true) }
                    }
                }
            }
            .padding(.bottom, 12)
        }
    }

    private func itemRow(_ item: MWActionItem, completed: Bool) -> some View {
        HStack(spacing: 6) {
            Button {
                Task { await viewModel.toggleActionItem(itemId: item.id, completed: !completed) }
            } label: {
                Image(systemName: completed ? "checkmark.square.fill" : "square")
                    .font(.system(size: 13))
                    .foregroundColor(completed ? Color.matcha500 : .white.opacity(0.5))
            }
            .buttonStyle(.plain)
            Text(item.text)
                .font(.system(size: 12))
                .foregroundColor(completed ? .white.opacity(0.4) : .white.opacity(0.9))
                .strikethrough(completed)
            Spacer()
            Button {
                Task { await viewModel.dismissActionItem(itemId: item.id) }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.3))
            }
            .buttonStyle(.plain)
        }
        .padding(8)
        .background(Color.black.opacity(0.12))
        .cornerRadius(5)
        .padding(.horizontal, 14)
    }

    private func emptyState(icon: String, label: String) -> some View {
        VStack(spacing: 6) {
            Spacer(minLength: 40)
            Image(systemName: icon).font(.system(size: 22)).foregroundColor(.white.opacity(0.3))
            Text(label).font(.system(size: 11)).foregroundColor(.white.opacity(0.5))
            Spacer()
        }
        .frame(maxWidth: .infinity, minHeight: 160)
    }
}

private extension DateFormatter {
    static let shortDateTime: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()
}

extension Notification.Name {
    static let mwConsultationPrepRequest = Notification.Name("mwConsultationPrepRequest")
}
