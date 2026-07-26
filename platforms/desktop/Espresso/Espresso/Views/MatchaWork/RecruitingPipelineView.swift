import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct RecruitingPipelineView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @Environment(AppState.self) private var appState

    @State private var tab: Tab = .status
    @State private var searchText = ""
    @State private var sortField: SortField = .match
    @State private var selectedCandidateIds: Set<String> = []
    @State private var showSendSheet = false
    @State private var isUploading = false
    @State private var isSyncing = false
    @State private var isAnalyzing = false
    @State private var postingDraft: String = ""
    @State private var expandedCandidateId: String?
    @State private var rejectTarget: MWResumeCandidate?
    @State private var autoSyncTask: Task<Void, Never>?

    enum Tab: String, CaseIterable, Identifiable {
        case status, posting, candidates, interviews, shortlist
        var id: String { rawValue }
    }

    enum SortField: String, CaseIterable, Identifiable {
        case match, name, experience
        var id: String { rawValue }
        var label: String {
            switch self {
            case .match: return "match"
            case .name: return "name"
            case .experience: return "yrs"
            }
        }
    }

    private var recruiting: MWRecruitingData { viewModel.recruitingData }
    private var isFinalized: Bool { recruiting.posting.finalized ?? false }
    private var analyzedCount: Int { recruiting.candidates.filter { $0.matchScore != nil }.count }
    private var interviewSentCount: Int { recruiting.candidates.filter { $0.interviewId != nil }.count }
    private var interviewedCount: Int { recruiting.candidates.filter { $0.interviewStatus == "completed" || $0.interviewStatus == "interview_completed" }.count }

    var body: some View {
        mainContent
            .background(.ultraThinMaterial)
            .onAppear {
                postingDraft = recruiting.posting.content ?? ""
                startAutoSync()
            }
            .onChange(of: viewModel.project?.id) {
                postingDraft = recruiting.posting.content ?? ""
            }
            .onChange(of: recruiting.posting.content ?? "") { _, newValue in
                if newValue != postingDraft {
                    postingDraft = newValue
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .mwProjectDataChanged)) { _ in
                if let pid = viewModel.project?.id {
                    Task { await viewModel.loadProject(id: pid) }
                }
            }
            .onDisappear { autoSyncTask?.cancel() }
            .sheet(isPresented: $showSendSheet) { sendInterviewSheet }
            .sheet(item: $rejectTarget) { candidate in rejectSheet(for: candidate) }
    }

    @ViewBuilder
    private var mainContent: some View {
        VStack(spacing: 0) {
            progressStrip
            guidanceBanner
            tabBar
            Divider()
            switch tab {
            case .status:
                statusTab
            case .posting:
                postingTab
            case .candidates:
                candidatesTab(filter: .all)
            case .interviews:
                candidatesTab(filter: .interviews)
            case .shortlist:
                candidatesTab(filter: .shortlist)
            }
        }
    }

    private var sendInterviewSheet: some View {
        SendInterviewSheet(
            candidateCount: selectedCandidateIds.count,
            onSend: { title, message in
                let ids = Array(selectedCandidateIds)
                Task {
                    await viewModel.sendProjectInterviews(
                        candidateIds: ids,
                        positionTitle: title.isEmpty ? nil : title,
                        customMessage: message.isEmpty ? nil : message
                    )
                    selectedCandidateIds.removeAll()
                }
            }
        )
    }

    private func rejectSheet(for candidate: MWResumeCandidate) -> some View {
        RejectCandidateSheet(candidate: candidate) { reason, sendEmail in
            Task {
                await viewModel.rejectCandidate(candidateId: candidate.id, reason: reason, sendEmail: sendEmail)
            }
        }
    }

    // MARK: - Auto-sync

    private func startAutoSync() {
        let hasPending = recruiting.candidates.contains { $0.interviewId != nil && $0.interviewStatus != "completed" && $0.interviewStatus != "interview_completed" }
        guard hasPending else { return }
        // Capture the AppState reference so the loop sees live scene-phase
        // updates. Reading `scenePhase` directly here would freeze it at task
        // creation since `self` is a value-type View struct.
        let state = appState
        autoSyncTask = Task { @MainActor in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                if state.isSceneActive {
                    await viewModel.syncProjectInterviews()
                }
            }
        }
    }

    // MARK: - Progress Strip

    private var progressStrip: some View {
        let stages: [(label: String, count: Int?, done: Bool, tab: Tab)] = [
            ("Posting", (viewModel.project?.sections?.count ?? 0) > 0 ? viewModel.project?.sections?.count : nil, isFinalized, .posting),
            ("Candidates", recruiting.candidates.isEmpty ? nil : recruiting.candidates.count, !recruiting.candidates.isEmpty, .candidates),
            ("Analyzed", analyzedCount == 0 ? nil : analyzedCount, analyzedCount > 0, .candidates),
            ("Interviews", interviewSentCount == 0 ? nil : interviewSentCount, interviewSentCount > 0, .interviews),
            ("Completed", interviewedCount == 0 ? nil : interviewedCount, interviewedCount > 0, .interviews),
        ]
        let activeIdx = stages.firstIndex { !$0.done } ?? stages.count

        return HStack(spacing: 0) {
            ForEach(Array(stages.enumerated()), id: \.offset) { i, stage in
                HStack(spacing: 0) {
                    Button { tab = stage.tab } label: {
                        HStack(spacing: 5) {
                            ZStack {
                                Circle()
                                    .fill(stage.done ? Color.matcha500 : i == activeIdx ? Color.matcha500 : Color.clear)
                                    .frame(width: 18, height: 18)
                                Circle()
                                    .stroke(stage.done ? Color.matcha500 : i == activeIdx ? Color.matcha500 : Color.white.opacity(0.25), lineWidth: 1.5)
                                    .frame(width: 18, height: 18)
                                if stage.done {
                                    Image(systemName: "checkmark")
                                        .font(.system(size: 9, weight: .bold))
                                        .foregroundColor(.white)
                                } else {
                                    Text("\(i + 1)")
                                        .font(.system(size: 9, weight: .bold))
                                        .foregroundColor(i == activeIdx ? .white : .white.opacity(0.35))
                                }
                            }
                            VStack(alignment: .leading, spacing: 0) {
                                Text(stage.label)
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(stage.done ? Color.matcha500 : i == activeIdx ? .white : .white.opacity(0.45))
                                if let count = stage.count {
                                    Text("(\(count))")
                                        .font(.system(size: 9))
                                        .foregroundColor(.white.opacity(0.3))
                                }
                            }
                        }
                    }
                    .buttonStyle(.plain)

                    if i < stages.count - 1 {
                        Rectangle()
                            .fill(stage.done ? Color.matcha500.opacity(0.5) : Color.white.opacity(0.1))
                            .frame(height: 1)
                            .frame(maxWidth: .infinity)
                            .padding(.horizontal, 4)
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.2))
    }

    // MARK: - Guidance Banner

    @ViewBuilder
    private var guidanceBanner: some View {
        let text: String? = {
            if !isFinalized && (viewModel.project?.sections ?? []).isEmpty {
                return "Describe the role in the chat to generate a job posting."
            } else if !isFinalized && !(viewModel.project?.sections ?? []).isEmpty {
                return "Review your posting, then finalize it."
            } else if isFinalized && recruiting.candidates.isEmpty {
                return "Posting finalized. Upload resumes to add candidates."
            } else if !recruiting.candidates.isEmpty && analyzedCount == 0 {
                return "Candidates uploaded. Click \"Analyze\" to rank them by match score."
            } else if analyzedCount > 0 && interviewSentCount == 0 {
                return "Candidates ranked. Select candidates and send voice interviews."
            } else if interviewSentCount > 0 && interviewedCount == 0 {
                return "Interviews sent. Waiting for candidates to complete their sessions."
            } else if interviewedCount > 0 && recruiting.shortlistIds.isEmpty {
                return "Interviews complete. Review scores and star your top picks."
            } else if !recruiting.shortlistIds.isEmpty {
                return "Shortlist ready. Generate offer letters for your top candidates."
            }
            return nil
        }()

        if let text {
            HStack(spacing: 6) {
                Text("→").font(.system(size: 12)).foregroundColor(Color.matcha500)
                Text(text).font(.system(size: 10, weight: .medium)).foregroundColor(Color.matcha500)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color.matcha500.opacity(0.08))
        }
    }

    // MARK: - Tab bar

    private var tabBar: some View {
        HStack(spacing: 12) {
            ForEach(Tab.allCases) { t in
                let count: Int? = {
                    switch t {
                    case .status: return nil
                    case .posting: return viewModel.project?.sections?.count
                    case .candidates: return recruiting.candidates.count
                    case .interviews: return interviewSentCount
                    case .shortlist: return recruiting.shortlistIds.count
                    }
                }()
                Button { tab = t } label: {
                    VStack(spacing: 2) {
                        HStack(spacing: 3) {
                            Text(t.rawValue.capitalized)
                                .font(.system(size: 11, weight: tab == t ? .medium : .regular))
                                .foregroundColor(tab == t ? Color.matcha500 : .white.opacity(0.5))
                            if let count, count > 0 {
                                Text("(\(count))")
                                    .font(.system(size: 9))
                                    .foregroundColor(.white.opacity(0.3))
                            }
                        }
                        Rectangle()
                            .fill(tab == t ? Color.matcha500 : Color.clear)
                            .frame(height: 1)
                    }
                }
                .buttonStyle(.plain)
            }
            Spacer()
            if tab != .posting && tab != .status {
                HStack(spacing: 6) {
                    if !recruiting.candidates.isEmpty && analyzedCount < recruiting.candidates.count {
                        Button {
                            Task {
                                isAnalyzing = true
                                await viewModel.analyzeProjectCandidates()
                                isAnalyzing = false
                            }
                        } label: {
                            Text(isAnalyzing ? "analyzing…" : "analyze")
                                .font(.system(size: 10))
                                .foregroundColor(Color.matcha500)
                        }
                        .buttonStyle(.plain)
                        .disabled(isAnalyzing)
                    }
                    Button {
                        Task {
                            isSyncing = true
                            await viewModel.syncProjectInterviews()
                            isSyncing = false
                        }
                    } label: {
                        Text(isSyncing ? "syncing…" : "sync")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.5))
                    }
                    .buttonStyle(.plain)
                    .disabled(isSyncing)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.regularMaterial)
    }

    // MARK: - Status tab

    private var statusTab: some View {
        let created = viewModel.project?.createdAt.flatMap { ISO8601DateFormatter().date(from: $0) } ?? Date()
        let daysOpen = max(1, Calendar.current.dateComponents([.day], from: created, to: Date()).day ?? 1)

        return ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Overview
                HStack(spacing: 20) {
                    statusStat("Days open", "\(daysOpen)")
                    statusStat("Candidates", "\(recruiting.candidates.count)")
                    statusStat("Analyzed", "\(analyzedCount)")
                    statusStat("Interviewed", "\(interviewedCount)")
                    statusStat("Shortlisted", "\(recruiting.shortlistIds.count)")
                }

                Divider().opacity(0.3)

                // Milestones
                VStack(alignment: .leading, spacing: 8) {
                    Text("MILESTONES")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.white.opacity(0.35))
                    milestone("Job posting created", done: !(viewModel.project?.sections ?? []).isEmpty)
                    milestone("Posting finalized", done: isFinalized)
                    milestone("Resumes uploaded", done: !recruiting.candidates.isEmpty)
                    milestone("Candidates analyzed", done: analyzedCount > 0)
                    milestone("Interviews sent", done: interviewSentCount > 0)
                    milestone("Interviews completed", done: interviewedCount > 0)
                    milestone("Shortlist created", done: !recruiting.shortlistIds.isEmpty)
                    milestone("Offer sent", done: false)
                }
            }
            .padding(16)
        }
    }

    private func statusStat(_ label: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.45))
        }
    }

    private func milestone(_ label: String, done: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: done ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 12))
                .foregroundColor(done ? Color.matcha500 : .white.opacity(0.2))
            Text(label)
                .font(.system(size: 12))
                .foregroundColor(done ? .white.opacity(0.8) : .white.opacity(0.4))
        }
    }

    // MARK: - Posting tab

    private var postingTab: some View {
        let sections = viewModel.project?.sections ?? []
        let hasSections = !sections.isEmpty

        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Text(isFinalized ? "● finalized" : "○ draft")
                    .font(.system(size: 10))
                    .foregroundColor(isFinalized ? Color.matcha500 : .white.opacity(0.5))
                Spacer()
                Button {
                    Task {
                        await viewModel.savePosting(
                            title: recruiting.posting.title,
                            content: hasSections ? combinedSectionsMarkdown(sections) : postingDraft,
                            finalized: !isFinalized
                        )
                    }
                } label: {
                    Text(isFinalized ? "unfinalize" : "finalize")
                        .font(.system(size: 11))
                        .foregroundColor(Color.matcha500)
                }
                .buttonStyle(.plain)
                Button { pickResumes() } label: {
                    Text(isUploading ? "uploading…" : "+ upload resumes")
                        .font(.system(size: 11))
                        .foregroundColor(isFinalized && !isUploading ? Color.matcha500 : .white.opacity(0.25))
                }
                .buttonStyle(.plain)
                .disabled(!isFinalized || isUploading)
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)

            if hasSections {
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(sections) { section in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(section.title)
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(.white)
                                if let content = section.content, !content.isEmpty {
                                    Text(content)
                                        .font(.system(size: 12))
                                        .foregroundColor(.white.opacity(0.75))
                                        .lineSpacing(3)
                                        .textSelection(.enabled)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.black.opacity(0.2))
                            .cornerRadius(6)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 12)
                }
            } else {
                ScrollView {
                    TextEditor(text: $postingDraft)
                        .font(.system(size: 13))
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 300)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.black.opacity(0.15))
                        .onSubmit { Task { await savePosting() } }
                }
                .padding(.horizontal, 16)

                HStack {
                    Spacer()
                    Button { Task { await savePosting() } } label: {
                        Text("save posting")
                            .font(.system(size: 11))
                            .foregroundColor(Color.matcha500)
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 12)
                }
            }
        }
    }

    private func combinedSectionsMarkdown(_ sections: [MWProjectSection]) -> String {
        sections.map { section in
            let body = section.content ?? ""
            return "## \(section.title)\n\n\(body)"
        }.joined(separator: "\n\n")
    }

    private func savePosting() async {
        await viewModel.savePosting(
            title: recruiting.posting.title,
            content: postingDraft,
            finalized: isFinalized
        )
    }

    // MARK: - Candidates / Interviews / Shortlist

    enum CandidateFilter { case all, interviews, shortlist }

    private func candidatesTab(filter: CandidateFilter) -> some View {
        let base: [MWResumeCandidate] = {
            switch filter {
            case .all: return recruiting.candidates
            case .interviews: return recruiting.candidates.filter { $0.interviewId != nil }
            case .shortlist: return recruiting.candidates.filter { recruiting.shortlistIds.contains($0.id) }
            }
        }()
        let filtered = filterAndSort(candidates: base)

        return VStack(spacing: 0) {
            HStack(spacing: 10) {
                HStack(spacing: 6) {
                    Text("›").font(.system(size: 11)).foregroundColor(.white.opacity(0.35))
                    TextField("", text: $searchText,
                              prompt: Text("search").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain)
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.9))
                }
                Spacer()
                ForEach(SortField.allCases) { field in
                    Button { sortField = field } label: {
                        Text(field.label)
                            .font(.system(size: 10))
                            .foregroundColor(sortField == field ? Color.matcha500 : .white.opacity(0.4))
                    }
                    .buttonStyle(.plain)
                }
                if !selectedCandidateIds.isEmpty {
                    Button { showSendSheet = true } label: {
                        Text("send interviews (\(selectedCandidateIds.count))")
                            .font(.system(size: 10))
                            .foregroundColor(Color.matcha500)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            Divider()

            if filtered.isEmpty {
                Spacer()
                Text(filter == .shortlist ? "nothing shortlisted yet" : filter == .interviews ? "no interviews yet" : "no candidates yet")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(filtered) { candidate in
                            candidateRow(candidate)
                            Divider().opacity(0.4)
                        }
                    }
                }
            }
        }
    }

    private func candidateRow(_ c: MWResumeCandidate) -> some View {
        let dismissed = recruiting.dismissedIds.contains(c.id)
        let shortlisted = recruiting.shortlistIds.contains(c.id)
        let expanded = expandedCandidateId == c.id

        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 10) {
                Button {
                    if selectedCandidateIds.contains(c.id) { selectedCandidateIds.remove(c.id) }
                    else { selectedCandidateIds.insert(c.id) }
                } label: {
                    Text(selectedCandidateIds.contains(c.id) ? "[x]" : "[ ]")
                        .font(.system(size: 11)).foregroundColor(.white.opacity(0.55))
                }
                .buttonStyle(.plain)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text(c.displayName.lowercased())
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(dismissed ? 0.35 : 0.9))
                            .strikethrough(dismissed)

                        // Match score badge
                        if let score = c.matchScore {
                            Text(String(format: "%.0f%%", score))
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(score >= 80 ? Color.matcha500 : score >= 60 ? .orange : .white.opacity(0.5))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(
                                    (score >= 80 ? Color.matcha500 : score >= 60 ? .orange : .white)
                                        .opacity(0.12)
                                )
                                .cornerRadius(4)
                        }

                        // Interview status + score
                        if let status = c.interviewStatus, !status.isEmpty {
                            HStack(spacing: 3) {
                                Circle()
                                    .fill(status.contains("completed") ? Color.matcha500 : status.contains("sent") ? .orange : .white.opacity(0.3))
                                    .frame(width: 5, height: 5)
                                Text(status.replacingOccurrences(of: "_", with: " "))
                                    .font(.system(size: 10))
                                    .foregroundColor(.white.opacity(0.4))
                                if let score = c.interviewScore {
                                    Text("· \(Int(score))%")
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundColor(Color.matcha500)
                                }
                            }
                        }
                    }
                    HStack(spacing: 8) {
                        if let title = c.currentTitle { Text(title).lineLimit(1) }
                        if let yrs = c.experienceYears { Text("· \(Int(yrs)) yrs") }
                        if let loc = c.location { Text("· \(loc)").lineLimit(1) }
                    }
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(dismissed ? 0.3 : 0.5))
                }
                Spacer()
                Button { Task { await viewModel.toggleShortlist(candidateId: c.id) } } label: {
                    Text(shortlisted ? "★" : "☆")
                        .font(.system(size: 13))
                        .foregroundColor(shortlisted ? Color.matcha500 : .white.opacity(0.4))
                }
                .buttonStyle(.plain)
                .help(shortlisted ? "Remove from shortlist" : "Add to shortlist")

                Button { Task { await viewModel.toggleDismiss(candidateId: c.id) } } label: {
                    Text(dismissed ? "↺" : "✕")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.45))
                }
                .buttonStyle(.plain)
                .help(dismissed ? "Restore" : "Dismiss")

                if c.status != "rejected" {
                    Button { rejectTarget = c } label: {
                        Text("reject")
                            .font(.system(size: 10))
                            .foregroundColor(.red.opacity(0.6))
                    }
                    .buttonStyle(.plain)
                }

                Button { expandedCandidateId = expanded ? nil : c.id } label: {
                    Text(expanded ? "▾" : "▸")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.45))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            if expanded { candidateDetail(c) }
        }
    }

    private func candidateDetail(_ c: MWResumeCandidate) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let email = c.email { detailRow("email", email) }
            if let phone = c.phone { detailRow("phone", phone) }
            if let edu = c.education { detailRow("education", edu) }
            if let skills = c.skills, !skills.isEmpty { detailRow("skills", skills.joined(separator: ", ")) }
            if let summary = c.summary { detailRow("summary", summary) }
            if let strengths = c.strengths, !strengths.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Text("strengths")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.35))
                        .frame(width: 80, alignment: .leading)
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(strengths, id: \.self) { s in
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 9))
                                    .foregroundColor(Color.matcha500)
                                Text(s).font(.system(size: 11)).foregroundColor(.white.opacity(0.75))
                            }
                        }
                    }
                }
            }
            if let flags = c.flags, !flags.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Text("flags")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.35))
                        .frame(width: 80, alignment: .leading)
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(flags, id: \.self) { f in
                            HStack(spacing: 4) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .font(.system(size: 9))
                                    .foregroundColor(.orange)
                                Text(f).font(.system(size: 11)).foregroundColor(.white.opacity(0.75))
                            }
                        }
                    }
                }
            }
            if let matchSummary = c.matchSummary { detailRow("match", matchSummary) }
            if let interviewSummary = c.interviewSummary { detailRow("interview", interviewSummary) }
        }
        .padding(.horizontal, 32)
        .padding(.bottom, 12)
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.35))
                .frame(width: 80, alignment: .leading)
            Text(value)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.75))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Helpers

    private func filterAndSort(candidates: [MWResumeCandidate]) -> [MWResumeCandidate] {
        var list = candidates
        if !searchText.isEmpty {
            let q = searchText.lowercased()
            list = list.filter {
                ($0.name?.lowercased().contains(q) ?? false) ||
                ($0.currentTitle?.lowercased().contains(q) ?? false) ||
                ($0.location?.lowercased().contains(q) ?? false) ||
                ($0.skills?.contains(where: { $0.lowercased().contains(q) }) ?? false)
            }
        }
        switch sortField {
        case .name: list.sort { ($0.name ?? "") < ($1.name ?? "") }
        case .experience: list.sort { ($0.experienceYears ?? 0) > ($1.experienceYears ?? 0) }
        case .match: list.sort { ($0.matchScore ?? 0) > ($1.matchScore ?? 0) }
        }
        return list
    }

    private func pickResumes() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.pdf, .plainText]
        panel.begin { response in
            guard response == .OK else { return }
            var files: [(data: Data, filename: String, mimeType: String)] = []
            for url in panel.urls {
                guard let data = try? Data(contentsOf: url) else { continue }
                let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/pdf"
                files.append((data: data, filename: url.lastPathComponent, mimeType: mime))
            }
            guard !files.isEmpty else { return }
            Task {
                isUploading = true
                await viewModel.uploadProjectResumes(files: files)
                isUploading = false
            }
        }
    }
}

// MARK: - Send Interview Sheet

private struct SendInterviewSheet: View {
    @Environment(\.dismiss) private var dismiss
    let candidateCount: Int
    let onSend: (String, String) -> Void

    @State private var positionTitle = ""
    @State private var message = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("send interviews")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))
            Text("\(candidateCount) candidate(s) selected")
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.5))

            VStack(alignment: .leading, spacing: 4) {
                Text("position title (optional)")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                TextField("", text: $positionTitle, prompt: Text("Senior Engineer").foregroundColor(.white.opacity(0.25)))
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.9))
                Divider()
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("custom message (optional)")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                TextField("", text: $message, prompt: Text("looking forward to chatting").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.9))
                    .lineLimit(2...4)
                Divider()
            }

            HStack {
                Button { dismiss() } label: {
                    Text("cancel").font(.system(size: 11)).foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button { onSend(positionTitle, message); dismiss() } label: {
                    Text("send").font(.system(size: 11, weight: .medium)).foregroundColor(Color.matcha500)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(20)
        .frame(width: 380)
        .background(.ultraThinMaterial)
    }
}

// MARK: - Reject Candidate Sheet

private struct RejectCandidateSheet: View {
    @Environment(\.dismiss) private var dismiss
    let candidate: MWResumeCandidate
    let onReject: (String?, Bool) -> Void

    @State private var reason = ""
    @State private var sendEmail = true

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("reject \(candidate.displayName.lowercased())")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))

            VStack(alignment: .leading, spacing: 4) {
                Text("reason (optional)")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.4))
                TextField("", text: $reason, prompt: Text("not the right fit").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.9))
                    .lineLimit(2...4)
                Divider()
            }

            Toggle("Send rejection email", isOn: $sendEmail)
                .toggleStyle(.switch)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.7))

            HStack {
                Button { dismiss() } label: {
                    Text("cancel").font(.system(size: 11)).foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    onReject(reason.isEmpty ? nil : reason, sendEmail)
                    dismiss()
                } label: {
                    Text("reject").font(.system(size: 11, weight: .medium)).foregroundColor(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(20)
        .frame(width: 380)
        .background(.ultraThinMaterial)
    }
}
