import SwiftUI

struct ResumeBatchPanelView: View {
    let state: [String: AnyCodable]
    let threadId: String?

    @State private var searchText = ""
    @State private var sortKey = "name"
    @State private var sortAscending = true
    @State private var expandedId: String?
    @State private var selectedIds: Set<String> = []
    @State private var isSending = false
    @State private var isSyncing = false
    @State private var positionTitle = ""
    @State private var showSendSheet = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    private var candidates: [MWResumeCandidate] {
        guard let raw = state["candidates"]?.value as? [AnyCodable] else { return [] }
        let data = try? JSONSerialization.data(withJSONObject: raw.map { $0.value })
        guard let data else { return [] }
        return (try? JSONDecoder().decode([MWResumeCandidate].self, from: data)) ?? []
    }

    private var filtered: [MWResumeCandidate] {
        var list = candidates
        if !searchText.isEmpty {
            let q = searchText.lowercased()
            list = list.filter {
                ($0.name?.lowercased().contains(q) ?? false)
                || ($0.currentTitle?.lowercased().contains(q) ?? false)
                || ($0.location?.lowercased().contains(q) ?? false)
                || ($0.skills?.joined(separator: " ").lowercased().contains(q) ?? false)
            }
        }
        return list.sorted { a, b in
            let result: Bool
            switch sortKey {
            case "experience":
                result = (a.experienceYears ?? 0) < (b.experienceYears ?? 0)
            case "title":
                result = (a.currentTitle ?? "") < (b.currentTitle ?? "")
            case "location":
                result = (a.location ?? "") < (b.location ?? "")
            default:
                result = (a.displayName) < (b.displayName)
            }
            return sortAscending ? result : !result
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Candidates")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text("(\(candidates.count))")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Spacer()

                if let tid = threadId {
                    Button {
                        isSyncing = true
                        Task {
                            do {
                                try await MatchaWorkService.shared.syncInterviews(threadId: tid)
                                await MainActor.run { successMessage = "Synced"; isSyncing = false }
                            } catch {
                                await MainActor.run { errorMessage = error.localizedDescription; isSyncing = false }
                            }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            if isSyncing { ProgressView().controlSize(.mini) }
                            Image(systemName: "arrow.triangle.2.circlepath")
                                .font(.system(size: 11))
                        }
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                    .disabled(isSyncing)
                    .help("Sync interview statuses")

                    Button { showSendSheet = true } label: {
                        Text("Send Interviews")
                            .font(.system(size: 11, weight: .medium))
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .controlSize(.small)
                    .disabled(selectedIds.isEmpty)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            // Search + Sort
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                TextField("Search candidates...", text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))

                Menu {
                    ForEach(["name", "experience", "title", "location"], id: \.self) { key in
                        Button {
                            if sortKey == key { sortAscending.toggle() }
                            else { sortKey = key; sortAscending = true }
                        } label: {
                            HStack {
                                Text(key.capitalized)
                                if sortKey == key {
                                    Image(systemName: sortAscending ? "chevron.up" : "chevron.down")
                                }
                            }
                        }
                    }
                } label: {
                    Image(systemName: "arrow.up.arrow.down")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(Color.zinc800.opacity(0.5))

            Divider().opacity(0.3)

            // Messages
            if let msg = successMessage {
                Text(msg)
                    .font(.system(size: 11))
                    .foregroundColor(.matcha500)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 4)
            }
            if let err = errorMessage {
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 4)
            }

            // Candidate list
            if filtered.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("No candidates yet")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                    Text("Upload resumes to start analyzing")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary.opacity(0.7))
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(filtered) { candidate in
                            CandidateRow(
                                candidate: candidate,
                                isExpanded: expandedId == candidate.id,
                                isSelected: selectedIds.contains(candidate.id),
                                onToggleExpand: {
                                    withAnimation(.easeOut(duration: 0.15)) {
                                        expandedId = expandedId == candidate.id ? nil : candidate.id
                                    }
                                },
                                onToggleSelect: {
                                    if selectedIds.contains(candidate.id) {
                                        selectedIds.remove(candidate.id)
                                    } else {
                                        selectedIds.insert(candidate.id)
                                    }
                                }
                            )
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .background(Color.zinc900)
        .sheet(isPresented: $showSendSheet) {
            SendInterviewSheet(
                count: selectedIds.count,
                positionTitle: $positionTitle,
                isSending: $isSending,
                onSend: {
                    guard let tid = threadId else { return }
                    isSending = true
                    Task {
                        do {
                            _ = try await MatchaWorkService.shared.sendInterviews(
                                threadId: tid,
                                candidateIds: Array(selectedIds),
                                positionTitle: positionTitle.isEmpty ? nil : positionTitle
                            )
                            await MainActor.run {
                                successMessage = "Sent \(selectedIds.count) interview invite(s)"
                                selectedIds.removeAll()
                                isSending = false
                                showSendSheet = false
                            }
                        } catch {
                            await MainActor.run {
                                errorMessage = error.localizedDescription
                                isSending = false
                            }
                        }
                    }
                }
            )
        }
    }
}

// MARK: - Candidate Row

private struct CandidateRow: View {
    let candidate: MWResumeCandidate
    let isExpanded: Bool
    let isSelected: Bool
    let onToggleExpand: () -> Void
    let onToggleSelect: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Button(action: onToggleSelect) {
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 14))
                        .foregroundColor(isSelected ? .matcha500 : .secondary)
                }
                .buttonStyle(.plain)

                VStack(alignment: .leading, spacing: 2) {
                    Text(candidate.displayName)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                    HStack(spacing: 6) {
                        if let title = candidate.currentTitle {
                            Text(title)
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                        }
                        if let yrs = candidate.experienceYears {
                            Text("\(String(format: "%.0f", yrs))y exp")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                        }
                        if let loc = candidate.location {
                            Text(loc)
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                        }
                    }
                }

                Spacer()

                // Interview status badge
                if let istatus = candidate.interviewStatus {
                    Text(istatus)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundColor(istatus == "completed" ? .green : .orange)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background((istatus == "completed" ? Color.green : Color.orange).opacity(0.15))
                        .cornerRadius(4)
                }

                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
            .onTapGesture { onToggleExpand() }

            if isExpanded {
                VStack(alignment: .leading, spacing: 8) {
                    if let summary = candidate.summary {
                        Text(summary)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }
                    if let skills = candidate.skills, !skills.isEmpty {
                        FlowTagView(label: "Skills", tags: skills, color: .cyan)
                    }
                    if let strengths = candidate.strengths, !strengths.isEmpty {
                        FlowTagView(label: "Strengths", tags: strengths, color: .green)
                    }
                    if let flags = candidate.flags, !flags.isEmpty {
                        FlowTagView(label: "Flags", tags: flags, color: .red)
                    }
                    if let edu = candidate.education {
                        Label(edu, systemImage: "graduationcap")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    if let certs = candidate.certifications, !certs.isEmpty {
                        Label(certs.joined(separator: ", "), systemImage: "rosette")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal, 46)
                .padding(.bottom, 10)
                .transition(.opacity)
            }
        }
        .background(isExpanded ? Color.zinc800.opacity(0.3) : Color.clear)
    }
}

private struct FlowTagView: View {
    let label: String
    let tags: [String]
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(.secondary)
            HStack(spacing: 4) {
                ForEach(tags.prefix(8), id: \.self) { tag in
                    Text(tag)
                        .font(.system(size: 9))
                        .foregroundColor(color)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(color.opacity(0.12))
                        .cornerRadius(3)
                }
                if tags.count > 8 {
                    Text("+\(tags.count - 8)")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }
        }
    }
}

// MARK: - Send Interview Sheet

private struct SendInterviewSheet: View {
    let count: Int
    @Binding var positionTitle: String
    @Binding var isSending: Bool
    let onSend: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Send Interview Invites")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.white)

            Text("Sending to \(count) candidate\(count == 1 ? "" : "s")")
                .font(.system(size: 12))
                .foregroundColor(.secondary)

            TextField("Position title (optional)", text: $positionTitle)
                .textFieldStyle(.roundedBorder)

            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { }
                Button { onSend() } label: {
                    HStack(spacing: 4) {
                        if isSending { ProgressView().controlSize(.mini) }
                        Text("Send")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .disabled(isSending)
            }
        }
        .padding(24)
        .frame(width: 360)
        .background(Color.appBackground)
    }
}
