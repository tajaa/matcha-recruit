import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct RecruitingPipelineView: View {
    @Bindable var viewModel: ProjectDetailViewModel

    @State private var tab: Tab = .posting
    @State private var searchText = ""
    @State private var sortField: SortField = .match
    @State private var selectedCandidateIds: Set<String> = []
    @State private var showSendSheet = false
    @State private var isUploading = false
    @State private var isSyncing = false
    @State private var postingDraft: String = ""
    @State private var expandedCandidateId: String?

    enum Tab: String, CaseIterable, Identifiable {
        case posting, candidates, shortlist
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

    var body: some View {
        VStack(spacing: 0) {
            tabBar
            Divider()
            switch tab {
            case .posting:
                postingTab
            case .candidates:
                candidatesTab(shortlistOnly: false)
            case .shortlist:
                candidatesTab(shortlistOnly: true)
            }
        }
        .background(.ultraThinMaterial)
        .onAppear {
            postingDraft = recruiting.posting.content ?? ""
        }
        .onChange(of: viewModel.project?.id) {
            postingDraft = recruiting.posting.content ?? ""
        }
        .sheet(isPresented: $showSendSheet) {
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
    }

    // MARK: - Tab bar

    private var tabBar: some View {
        HStack(spacing: 20) {
            ForEach(Tab.allCases) { t in
                Button {
                    tab = t
                } label: {
                    VStack(spacing: 3) {
                        HStack(spacing: 4) {
                            Text(t.rawValue)
                                .font(.system(size: 11, weight: tab == t ? .medium : .regular))
                                .foregroundColor(tab == t ? Color.matcha500 : .white.opacity(0.5))
                            if t == .candidates {
                                Text("(\(recruiting.candidates.count))")
                                    .font(.system(size: 10))
                                    .foregroundColor(.white.opacity(0.35))
                            } else if t == .shortlist {
                                Text("(\(recruiting.shortlistIds.count))")
                                    .font(.system(size: 10))
                                    .foregroundColor(.white.opacity(0.35))
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
            if tab != .posting {
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
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.regularMaterial)
    }

    // MARK: - Posting tab

    private var postingTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Text(recruiting.posting.finalized == true ? "● finalized" : "○ draft")
                    .font(.system(size: 10))
                    .foregroundColor(recruiting.posting.finalized == true ? Color.matcha500 : .white.opacity(0.5))
                Spacer()
                Button {
                    Task {
                        await viewModel.savePosting(
                            title: recruiting.posting.title,
                            content: postingDraft,
                            finalized: !(recruiting.posting.finalized ?? false)
                        )
                    }
                } label: {
                    Text(recruiting.posting.finalized == true ? "unfinalize" : "finalize")
                        .font(.system(size: 11))
                        .foregroundColor(Color.matcha500)
                }
                .buttonStyle(.plain)
                Button {
                    pickResumes()
                } label: {
                    Text(isUploading ? "uploading…" : "+ upload resumes")
                        .font(.system(size: 11))
                        .foregroundColor(
                            recruiting.posting.finalized == true && !isUploading
                                ? Color.matcha500
                                : .white.opacity(0.25)
                        )
                }
                .buttonStyle(.plain)
                .disabled(recruiting.posting.finalized != true || isUploading)
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)

            ScrollView {
                TextEditor(text: $postingDraft)
                    .font(.system(size: 13))
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 300)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.black.opacity(0.15))
                    .onChange(of: postingDraft) {
                        // Debounced save could go here; for MVP push immediately
                    }
                    .onSubmit {
                        Task { await savePosting() }
                    }
            }
            .padding(.horizontal, 16)

            HStack {
                Spacer()
                Button {
                    Task { await savePosting() }
                } label: {
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

    private func savePosting() async {
        await viewModel.savePosting(
            title: recruiting.posting.title,
            content: postingDraft,
            finalized: recruiting.posting.finalized ?? false
        )
    }

    // MARK: - Candidates / shortlist tabs

    private func candidatesTab(shortlistOnly: Bool) -> some View {
        let base = shortlistOnly
            ? recruiting.candidates.filter { recruiting.shortlistIds.contains($0.id) }
            : recruiting.candidates
        let filtered = filterAndSort(candidates: base)

        return VStack(spacing: 0) {
            // Search + sort bar
            HStack(spacing: 10) {
                HStack(spacing: 6) {
                    Text("›")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.35))
                    TextField("",
                              text: $searchText,
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
                    Button {
                        showSendSheet = true
                    } label: {
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
                Text(shortlistOnly ? "nothing shortlisted yet" : "no candidates yet")
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
                    if selectedCandidateIds.contains(c.id) {
                        selectedCandidateIds.remove(c.id)
                    } else {
                        selectedCandidateIds.insert(c.id)
                    }
                } label: {
                    Text(selectedCandidateIds.contains(c.id) ? "[x]" : "[ ]")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.55))
                }
                .buttonStyle(.plain)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text(c.displayName.lowercased())
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(dismissed ? 0.35 : 0.9))
                            .strikethrough(dismissed)
                        if let score = c.matchScore {
                            Text(String(format: "%.0f%%", score))
                                .font(.system(size: 10))
                                .foregroundColor(Color.matcha500.opacity(0.8))
                        }
                        if let status = c.interviewStatus, !status.isEmpty {
                            Text(status)
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.4))
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
                Button { Task { await viewModel.toggleDismiss(candidateId: c.id) } } label: {
                    Text(dismissed ? "↺" : "✕")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.45))
                }
                .buttonStyle(.plain)
                Button {
                    expandedCandidateId = expanded ? nil : c.id
                } label: {
                    Text(expanded ? "▾" : "▸")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.45))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            if expanded {
                candidateDetail(c)
            }
        }
    }

    private func candidateDetail(_ c: MWResumeCandidate) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let email = c.email { detailRow("email", email) }
            if let phone = c.phone { detailRow("phone", phone) }
            if let edu = c.education { detailRow("education", edu) }
            if let skills = c.skills, !skills.isEmpty {
                detailRow("skills", skills.joined(separator: ", "))
            }
            if let summary = c.summary { detailRow("summary", summary) }
            if let strengths = c.strengths, !strengths.isEmpty {
                detailRow("strengths", strengths.joined(separator: ", "))
            }
            if let flags = c.flags, !flags.isEmpty {
                detailRow("flags", flags.joined(separator: ", "))
            }
            if let matchSummary = c.matchSummary {
                detailRow("match", matchSummary)
            }
            if let interviewSummary = c.interviewSummary {
                detailRow("interview", interviewSummary)
            }
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
        case .name:
            list.sort { ($0.name ?? "") < ($1.name ?? "") }
        case .experience:
            list.sort { ($0.experienceYears ?? 0) > ($1.experienceYears ?? 0) }
        case .match:
            list.sort { ($0.matchScore ?? 0) > ($1.matchScore ?? 0) }
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
                    Text("cancel")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    onSend(positionTitle, message)
                    dismiss()
                } label: {
                    Text("send")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color.matcha500)
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
