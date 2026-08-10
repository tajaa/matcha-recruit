import SwiftUI

struct ReportDetailView: View {
    let id: String
    @State private var vm: ReportDetailViewModel

    init(id: String) {
        self.id = id
        _vm = State(initialValue: ReportDetailViewModel(id: id))
    }

    var body: some View {
        content
            .navigationTitle("Feedback")
            .navigationBarTitleDisplayMode(.inline)
            .task { await vm.load() }
            .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }

    @ViewBuilder
    private var content: some View {
        if let report = vm.report {
            ReportDetailForm(report: report, vm: vm)
        } else {
            ProgressView()
        }
    }
}

/// Split from ReportDetailView's body — a single Form with this many
/// conditional Sections defeats Swift's type-checker (times out). Each
/// section is its own small computed property so inference stays local.
private struct ReportDetailForm: View {
    let report: Report
    @Bindable var vm: ReportDetailViewModel
    @State private var replyText = ""
    @State private var showPublishConfirm = false
    @State private var messageThread: DmThread?
    @State private var showMessageComposer = false

    var body: some View {
        Form {
            summarySection
            statusSection
            if report.reward_status == .pending { rewardSection }
            heartSection
            replySection
            if report.review_state == .held { publishSection }
            // Identified feedback only, matching web's dm gating.
            if report.is_identified { messageSection }
            if !report.media.isEmpty {
                Section("Media") {
                    ReportMediaGallery(media: report.media) { vm.refetchOnceForExpiredMedia() }
                }
            }
            if !report.answers.isEmpty { answersSection }
        }
        .onAppear { replyText = report.brand_public_reply ?? replyText }
        .confirmationDialog(
            "Waives the remaining 48-hour hold — cannot be undone.",
            isPresented: $showPublishConfirm,
            titleVisibility: .visible
        ) {
            Button("Publish now", role: .destructive) { Task { await vm.publishNow() } }
        }
        .navigationDestination(item: $messageThread) { thread in
            DmThreadView(vm: DmThreadViewModel(thread: thread))
        }
        .sheet(isPresented: $showMessageComposer) {
            FeedbackComposerSheet(reportId: report.id) { thread in
                messageThread = thread
            }
        }
    }

    private var messageSection: some View {
        Section {
            Button {
                showMessageComposer = true
            } label: {
                Text("Message reporter")
            }
        }
    }

    private var summarySection: some View {
        Section {
            HStack {
                Text(report.title ?? report.category.rawValue.capitalized).font(.headline)
                Spacer()
                SentimentBadge(sentiment: report.sentiment)
            }
            if let description = report.description { Text(description) }
            if let rating = report.rating {
                Label("\(rating)", systemImage: "star.fill").foregroundStyle(.yellow)
            }
        }
    }

    private var statusSection: some View {
        Section("Status") {
            Picker("Status", selection: Binding(
                get: { report.status },
                set: { newValue in Task { await vm.setStatus(newValue) } }
            )) {
                ForEach(ReportStatus.allCases, id: \.self) { status in
                    Text(status.rawValue.capitalized).tag(status)
                }
            }
        }
    }

    private var rewardSection: some View {
        Section("Reward decision") {
            HStack {
                Button("Approve") { Task { await vm.decideReward(approve: true) } }
                    .buttonStyle(.borderedProminent)
                Button("Reject") { Task { await vm.decideReward(approve: false) } }
                    .buttonStyle(.bordered)
            }
        }
    }

    private var heartSection: some View {
        let hearted = report.hearted_at != nil
        return Section {
            Button {
                Task { await vm.toggleHeart() }
            } label: {
                Label(hearted ? "Hearted" : "Heart", systemImage: hearted ? "heart.fill" : "heart")
                    .foregroundStyle(hearted ? Color.pink : Color.primary)
            }
        }
    }

    private var replySection: some View {
        Section("Public reply") {
            TextField("Write a reply visible on your public page…", text: $replyText, axis: .vertical)
            HStack {
                Button("Save") { Task { await vm.saveReply(replyText) } }
                if report.brand_public_reply != nil {
                    Button("Delete", role: .destructive) { Task { await vm.deleteReply() } }
                }
            }
        }
    }

    private var publishSection: some View {
        Section {
            Button("Publish now") { showPublishConfirm = true }
        }
    }

    private var answersSection: some View {
        Section("Answers") {
            ForEach(report.answers) { answer in
                VStack(alignment: .leading) {
                    Text(answer.prompt_text).font(.caption).foregroundStyle(.secondary)
                    Text(answer.answer)
                }
            }
        }
    }
}
