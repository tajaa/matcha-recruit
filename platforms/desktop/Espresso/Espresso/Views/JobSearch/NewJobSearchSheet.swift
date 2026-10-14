import SwiftUI
import AppKit

/// Start a job search: what they're after, what matters most, and whether to
/// use their résumé. The first search also shows what Job search does with
/// their data, and starts only once they agree.
struct NewJobSearchSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    let vm: JobSearchViewModel

    @State private var ask = ""
    @State private var titles = ""
    @State private var locations = ""
    @State private var remote = "any"
    @State private var baseFloor = ""
    @State private var weights = JobSearchWeights.standard
    @State private var useResume = false
    @State private var resume: ProfileResume?
    @State private var resumeLoaded = false
    @State private var uploading = false
    @State private var agreed = false
    @State private var starting = false
    @State private var errorMessage: String?
    @State private var requestId = UUID()

    private var needsConsent: Bool { !(vm.consent?.granted ?? false) }
    private var floor: JobSearchCriteria.BaseFloor { JobSearchCriteria.parseBaseFloor(baseFloor) }
    private var canStart: Bool {
        ask.trimmingCharacters(in: .whitespacesAndNewlines).count >= 3
            && weights.anyAboveZero && (!needsConsent || agreed) && !starting && !uploading
            && floor != .invalid
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("New job search")
                .font(.system(size: 15, weight: .bold))
                .padding(.horizontal, 20).padding(.top, 18).padding(.bottom, 10)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    field("What are you looking for?") {
                        TextEditor(text: $ask)
                            .font(.system(size: 12))
                            .frame(height: 70)
                            .scrollContentBackground(.hidden)
                            .padding(6)
                            .background(RoundedRectangle(cornerRadius: 6).stroke(appState.themeBorder))
                        Text("e.g. \u{201C}COO roles across the US. I care most about salary, bonus and equity; "
                             + "Series B or later; no relocation.\u{201D}")
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                    HStack(alignment: .top, spacing: 12) {
                        field("Titles (optional)") {
                            TextField("COO, Chief Operating Officer", text: $titles).textFieldStyle(.roundedBorder)
                        }
                        field("Locations (optional)") {
                            TextField("United States, Austin TX, Remote", text: $locations).textFieldStyle(.roundedBorder)
                        }
                    }
                    HStack(alignment: .top, spacing: 12) {
                        field("Remote") {
                            Picker("", selection: $remote) {
                                Text("Any").tag("any")
                                Text("Remote only").tag("remote_only")
                                Text("On-site only").tag("onsite_only")
                            }
                            .labelsHidden()
                            .frame(width: 160)
                        }
                        field("Minimum base (USD, optional)") {
                            TextField("250000 or $250k", text: $baseFloor).textFieldStyle(.roundedBorder).frame(width: 160)
                            switch floor {
                            case .none: EmptyView()
                            case .amount(let dollars):
                                Text("Using \(JobSearchViewModel.dollars(dollars)) a year")
                                    .font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                            case .invalid:
                                Text("Enter an amount like 250000, $250k or 1.5M (up to $10M).")
                                    .font(.system(size: 10)).foregroundColor(.orange)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    field("What matters most") {
                        WeightSliders(weights: $weights)
                        Text("Pay is only what a posting states, with the text it came from. Jobs that don't post "
                             + "pay are ranked after those that do; unposted pay is never counted as zero.")
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeTextSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    resumeSection
                    if needsConsent, let disclosure = vm.consent?.disclosure { consentSection(disclosure) }
                    if let errorMessage {
                        Text(errorMessage).font(.system(size: 11)).foregroundColor(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.horizontal, 20).padding(.bottom, 12)
            }
            Divider().opacity(0.3)
            HStack {
                if let line = JobSearchViewModel.usageLine(vm.usage) {
                    Text(line).font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button {
                    Task { await start() }
                } label: {
                    if starting { ProgressView().controlSize(.small) } else { Text("Start search") }
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .disabled(!canStart)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 20).padding(.vertical, 12)
        }
        .frame(width: 560, height: 640)
        .task { await loadResume() }
    }

    // MARK: Sections

    private var resumeSection: some View {
        field("Your résumé") {
            HStack(spacing: 8) {
                Image(systemName: "doc.text").foregroundColor(appState.themeTextSecondary)
                if !resumeLoaded {
                    ProgressView().controlSize(.small)
                } else if let resume {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(resume.filename).font(.system(size: 12, weight: .medium))
                        if let title = resume.currentTitle, !title.isEmpty {
                            Text(title).font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                        }
                    }
                } else {
                    Text("No résumé saved").font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                Button(resume == nil ? "Upload…" : "Replace…") { Task { await pickResume() } }
                    .disabled(uploading)
                if uploading { ProgressView().controlSize(.small) }
            }
            Toggle("Use my résumé to judge fit and draft the answers and cover letter", isOn: $useResume)
                .toggleStyle(.checkbox)
                .font(.system(size: 11))
                .disabled(resume == nil)
        }
    }

    private func consentSection(_ disclosure: AssistantDisclosure) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(disclosure.title).font(.system(size: 12, weight: .semibold))
            ForEach(disclosure.body, id: \.self) { line in
                Text("\u{2022} \(line)")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Toggle("I agree", isOn: $agreed).toggleStyle(.checkbox).font(.system(size: 11))
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(appState.themeText.opacity(0.04)))
    }

    private func field<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label).font(.system(size: 11, weight: .semibold)).foregroundColor(appState.themeText)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Actions

    private func loadResume() async {
        resume = try? await JobSearchService.shared.resume()
        resumeLoaded = true
        useResume = resume != nil
    }

    private func pickResume() async {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.allowedContentTypes = JobSearchService.resumeTypes
        guard panel.runModal() == .OK, let url = panel.url else { return }
        uploading = true
        errorMessage = nil
        defer { uploading = false }
        do {
            let data = try Data(contentsOf: url)
            resume = try await JobSearchService.shared.uploadResume(data: data, filename: url.lastPathComponent)
            useResume = true
        } catch let error as APIError {
            errorMessage = AssistantText.message(for: error, fallback: "Couldn't read that résumé.")
        } catch {
            errorMessage = "Couldn't read that file."
        }
    }

    private func start() async {
        starting = true
        errorMessage = nil
        defer { starting = false }
        var criteria = JobSearchCriteria()
        criteria.titles = Array(JobSearchCriteria.split(titles).prefix(8))
        criteria.locations = Array(JobSearchCriteria.split(locations).prefix(6))
        criteria.remote = remote
        if case .amount(let dollars) = floor { criteria.baseFloor = dollars }
        let body = JobSearchService.CreateBody(
            requestId: requestId,
            title: criteria.titles.first ?? "",
            ask: ask.trimmingCharacters(in: .whitespacesAndNewlines),
            criteria: criteria,
            weights: weights == .standard ? nil : weights,
            useResume: useResume && resume != nil,
            consentVersion: needsConsent && agreed ? vm.consent?.disclosure?.version : nil
        )
        do {
            try await vm.create(body)
            dismiss()
        } catch let error as APIError {
            if let plan = error.planRequirement {
                dismiss()
                appState.presentPaywall(for: plan.feature)
                return
            }
            errorMessage = AssistantText.message(for: error, fallback: "Couldn't start the search.")
            // Only a clear refusal makes the retry a new request. After a
            // timeout or a dropped connection the search may have started, so
            // the retry keeps the request id and the server returns that
            // search instead of refusing a second live one or counting another.
            if JobSearchViewModel.retryIsNewRequest(error) { requestId = UUID() }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
