import SwiftUI
import UniformTypeIdentifiers

/// Campaigns are private to the person who created them in this workspace.
struct SalesWorkspaceView: View {
    @Environment(AppState.self) private var appState
    let projectId: String
    @State private var model: SalesWorkspaceModel
    @State private var showCreate = false
    @State private var showImport = false
    @State private var showTemplate = false
    @State private var reviewing: SalesProspect?
    @State private var selected: Set<String> = []
    @State private var batch: [SalesProspect] = []
    @State private var showBatch = false

    init(projectId: String) {
        self.projectId = projectId
        _model = State(initialValue: SalesWorkspaceModel(projectId: projectId))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Sales").font(.headline)
                Text("Your campaigns in this workspace").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("New campaign") { showCreate = true }
                Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
            }
            if let error = model.error { Text(error).foregroundStyle(.orange).font(.caption).textSelection(.enabled) }
            if let notice = model.notice { Text(notice).foregroundStyle(.secondary).font(.caption) }
            if !model.campaigns.isEmpty {
                ViewThatFits(in: .horizontal) {
                    HStack { campaignPicker; campaignActions }
                    VStack(alignment: .leading) { campaignPicker; campaignActions }
                }
            }
            if let data = model.snapshot {
                campaignHeader(data)
                HStack {
                    Button("Draft with template") { showTemplate = true }
                    Button("Select all drafts") { selected = Set(data.prospects.filter { $0.status == "draft" }.map(\.id)) }
                    Button("Clear selection") { selected = [] }.disabled(selected.isEmpty)
                    Spacer()
                    Button("Review and send (\(selected.count))") {
                        batch = data.prospects.filter { selected.contains($0.id) && $0.status == "draft" }
                        showBatch = true
                    }.disabled(selected.isEmpty || data.campaign.status == "sending")
                }.controlSize(.small)
                ScrollView(.horizontal) {
                    HStack(alignment: .top, spacing: 10) {
                        ForEach(SalesStage.columns, id: \.key) { column in
                            let items = data.prospects.filter { $0.stage == column.key }
                            VStack(alignment: .leading, spacing: 8) {
                                Text("\(column.label) · \(items.count)").font(.subheadline.bold()).lineLimit(1)
                                ScrollView {
                                    LazyVStack(alignment: .leading, spacing: 8) {
                                        ForEach(items) { item in prospectCard(item) }
                                    }
                                }
                            }.padding(10).frame(width: 250).frame(maxHeight: .infinity)
                                .background(appState.themeText.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }
                if data.prospects.isEmpty {
                    Text("Import a list, or ask Espresso to find businesses matching your target. Save research and drafts here, then review a batch before sending.")
                        .font(.callout).foregroundStyle(.secondary)
                }
            } else if model.campaigns.isEmpty {
                ContentUnavailableView("Build a sales pipeline", systemImage: "person.3.sequence",
                    description: Text("Start with a target such as dental practices in San Francisco, or import your contacts. Espresso can research prospects and draft personalized outreach."))
            } else { ProgressView() }
        }
        .padding(12)
        .disabled(model.busy)
        .task {
            await model.refresh()
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(15)) } catch { return }
                if !model.busy { await model.refresh() }
            }
        }
        .onChange(of: model.snapshot?.prospects.map { $0.id + $0.review_token + $0.status }) { _, _ in
            selected.formIntersection(Set(model.snapshot?.prospects.filter { $0.status == "draft" }.map(\.id) ?? []))
        }
        .sheet(isPresented: $showCreate) {
            SalesCreateSheet(model: model) { showCreate = false }
        }
        .sheet(isPresented: $showImport) {
            if let id = model.selectedId { SalesImportSheet(model: model, campaignId: id) { showImport = false } }
        }
        .sheet(isPresented: $showTemplate) {
            if let id = model.selectedId { SalesTemplateSheet(model: model, campaignId: id) { showTemplate = false } }
        }
        .sheet(item: $reviewing) { item in
            if let id = model.selectedId { SalesProspectSheet(model: model, campaignId: id, item: item) { reviewing = nil } }
        }
        .sheet(isPresented: $showBatch) {
            if let id = model.selectedId { SalesBatchReview(model: model, campaignId: id, items: batch) { showBatch = false; selected = [] } }
        }
    }
    private var campaignPicker: some View {
        Picker("Campaign", selection: Binding(get: { model.selectedId ?? "" }, set: { id in
            selected = []; Task { await model.select(id) }
        })) {
            ForEach(model.campaigns) { Text($0.title).tag($0.id) }
        }.frame(maxWidth: 330)
    }
    private var campaignActions: some View {
        HStack {
            Button("Import contacts") { showImport = true }.disabled(model.snapshot == nil)
            Button("Research and draft with Espresso", action: askEspresso).disabled(model.snapshot == nil)
        }.controlSize(.small)
    }
    private func campaignHeader(_ data: SalesSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if !data.campaign.target.isEmpty { Text("Target: \(data.campaign.target)").font(.caption).lineLimit(3) }
            if !data.campaign.offer.isEmpty { Text("Offer: \(data.campaign.offer)").font(.caption).lineLimit(3) }
            HStack {
                Text(data.campaign.status.capitalized).font(.caption.bold())
                Text("\(data.prospects.count) prospects · \(data.counts["sent", default: 0]) sent · \(data.counts["failed", default: 0]) failed · \(data.counts["unknown", default: 0]) unconfirmed")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                if data.campaign.status == "sending" {
                    Button("Pause") { command("pause") }
                    Button("Recover queue") { command("resume") }.help("Recover a stalled queue. Messages already in progress are never replayed.")
                } else if data.counts["approved", default: 0] + data.counts["claimed", default: 0] > 0 {
                    Button("Resume") { command("resume") }
                    Button("Release pending drafts") { command("release_pending") }
                }
                if data.counts["failed", default: 0] > 0 {
                    Button("Review failed again") { command("retry_failed") }
                }
            }.controlSize(.small)
            if let sender = data.campaign.sender { Text("Sender: \(sender)").font(.caption).foregroundStyle(.secondary) }
            if let error = data.campaign.error { Text(error).font(.caption).foregroundStyle(.orange) }
            if data.counts["unknown", default: 0] > 0 {
                Text("Unconfirmed messages are never retried. Check Gmail Sent before contacting those recipients again.").font(.caption).foregroundStyle(.orange)
            }
        }
    }
    private func prospectCard(_ item: SalesProspect) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if item.status == "draft" {
                    Toggle("Select draft", isOn: Binding(get: { selected.contains(item.id) }, set: { value in
                        if value { selected.insert(item.id) } else { selected.remove(item.id) }
                    })).labelsHidden().toggleStyle(.checkbox)
                }
                Button { reviewing = item } label: {
                    Text(item.title).font(.subheadline.bold()).lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(.plain)
            }
            if !item.company.isEmpty { Text(item.company).font(.caption).foregroundStyle(.secondary) }
            Text(item.email.isEmpty ? "Email needed" : item.email).font(.caption).textSelection(.enabled)
            Text(item.status == "unknown" ? "Delivery unconfirmed" : item.status.capitalized)
                .font(.caption.bold()).foregroundStyle(item.status == "sent" ? .green : .secondary)
            if !item.research.isEmpty { Text(item.research).font(.caption).lineLimit(3) }
            if !item.subject.isEmpty { Text(item.subject).font(.caption).lineLimit(2) }
            if let error = item.error { Text(error).font(.caption).foregroundStyle(.orange).lineLimit(3) }
            Button("Open prospect & draft") { reviewing = item }.font(.caption)
        }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
            .background(appState.themeBg, in: RoundedRectangle(cornerRadius: 7))
    }
    private func command(_ action: String) {
        guard let id = model.selectedId else { return }
        Task { await model.perform { try await model.action(action, campaignId: id) } }
    }
    private func askEspresso() {
        guard let campaign = model.snapshot?.campaign else { return }
        appState.workOnSales(campaign: campaign, projectId: projectId)
    }
}

private struct SalesCreateSheet: View {
    let model: SalesWorkspaceModel
    let close: () -> Void
    @State private var title = ""
    @State private var target = ""
    @State private var offer = ""
    @State private var requestId = UUID()
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("New sales campaign").font(.headline)
            TextField("Campaign name", text: $title)
            TextField("Who should Espresso find? e.g. dental practices in San Francisco", text: $target)
            Text("What do you offer, and what should the email ask for?").font(.caption)
            TextEditor(text: $offer).frame(height: 110).border(.secondary.opacity(0.2))
            Text("Save the campaign, then import contacts or ask Espresso to discover prospects. Sales campaigns are private to you.").font(.caption).foregroundStyle(.secondary)
            if let error = model.error { Text(error).font(.caption).foregroundStyle(.orange) }
            HStack {
                Button("Cancel", action: close)
                Spacer()
                Button("Create campaign") { Task {
                    await model.perform { try await model.create(title: title, target: target, offer: offer, requestId: requestId) }
                    if model.error == nil { close() }
                }}.disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || title.count > 100 || target.count > 2000 || offer.count > 4000)
            }
        }.textFieldStyle(.roundedBorder).padding(20).frame(width: 580).disabled(model.busy)
    }
}

private struct SalesImportSheet: View {
    let model: SalesWorkspaceModel
    let campaignId: String
    let close: () -> Void
    @State private var text = ""
    @State private var importing = false
    @State private var error: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Import prospects").font(.headline)
            Text("Paste one email per line, or CSV/TSV with headers: email,name,company,website,notes. Up to 1,000 prospects. Duplicate emails in this campaign are skipped.").font(.caption)
            TextEditor(text: $text).font(.system(.body, design: .monospaced)).frame(height: 260).border(.secondary.opacity(0.2))
            if let error = error ?? model.error { Text(error).font(.caption).foregroundStyle(.orange) }
            HStack {
                Button("Choose CSV…") { importing = true }
                Spacer()
                Button("Cancel", action: close)
                Button("Import") { Task {
                    do {
                        let contacts = try SalesCSV.parse(text)
                        await model.perform { try await model.importContacts(contacts, campaignId: campaignId) }
                        if model.error == nil { close() }
                    } catch { self.error = error.localizedDescription }
                }}.disabled(text.isEmpty)
            }
        }.padding(20).frame(width: 640).disabled(model.busy)
        .fileImporter(isPresented: $importing, allowedContentTypes: [.commaSeparatedText, .tabSeparatedText, .plainText]) { result in
            do {
                let url = try result.get()
                let scoped = url.startAccessingSecurityScopedResource()
                defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
                guard size <= 1_000_000 else { throw SalesCSV.Invalid("Import at most 1 MB at a time.") }
                text = try String(contentsOf: url, encoding: .utf8)
            } catch { self.error = error.localizedDescription }
        }
    }
}

private struct SalesTemplateSheet: View {
    let model: SalesWorkspaceModel
    let campaignId: String
    let close: () -> Void
    @State private var subject = ""
    @State private var bodyText = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Draft a campaign template").font(.headline)
            Text("Fields: {{name}}, {{company}}, {{research}}, {{website}}. This replaces all editable drafts in this campaign. Approved and sent messages stay frozen. Review the rendered messages before sending.").font(.caption)
            TextField("Subject", text: $subject).textFieldStyle(.roundedBorder)
            TextEditor(text: $bodyText).frame(height: 260).border(.secondary.opacity(0.2))
            if let error = model.error { Text(error).font(.caption).foregroundStyle(.orange) }
            HStack {
                Button("Cancel", action: close); Spacer()
                Button("Create / replace drafts") { Task {
                    await model.perform { try await model.template(subject: subject, body: bodyText, campaignId: campaignId) }
                    if model.error == nil { close() }
                }}.disabled(subject.isEmpty || bodyText.isEmpty || subject.count > 300 || bodyText.count > 12000)
            }
        }.padding(20).frame(width: 640).disabled(model.busy)
    }
}

private struct SalesProspectSheet: View {
    let model: SalesWorkspaceModel
    let campaignId: String
    let item: SalesProspect
    let close: () -> Void
    @State private var email = ""
    @State private var subject = ""
    @State private var bodyText = ""
    @State private var stage = "lead"
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(item.title).font(.headline)
            Picker("Stage", selection: $stage) { ForEach(SalesStage.columns, id: \.key) { Text($0.label).tag($0.key) } }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if !item.notes.isEmpty { Text(item.notes).font(.caption).textSelection(.enabled) }
                    if !item.research.isEmpty { Text(item.research).font(.callout).textSelection(.enabled) }
                    ForEach(item.sources, id: \.self) { source in
                        if let url = URL(string: source) { Link(source, destination: url).font(.caption).lineLimit(2) }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(maxHeight: 150)
            TextField("Recipient email", text: $email).disabled(!item.editable)
            TextField("Subject", text: $subject).disabled(!item.editable)
            TextEditor(text: $bodyText).frame(height: 230).border(.secondary.opacity(0.2)).disabled(!item.editable)
            if let error = item.error { Text(error).font(.caption).foregroundStyle(.orange) }
            if let error = model.error { Text(error).font(.caption).foregroundStyle(.orange) }
            HStack {
                Button("Close", action: close); Spacer()
                Button("Save") { Task {
                    await model.perform { try await model.edit(item, email: email, subject: subject, body: bodyText, stage: stage, campaignId: campaignId) }
                    if model.error == nil { close() }
                }}.disabled(subject.count > 300 || bodyText.count > 12000)
            }
        }.textFieldStyle(.roundedBorder).padding(20).frame(width: 650).disabled(model.busy)
            .onAppear { email = item.email; subject = item.subject; bodyText = item.body; stage = item.stage }
    }
}

private struct SalesBatchReview: View {
    let model: SalesWorkspaceModel
    let campaignId: String
    let items: [SalesProspect]
    let close: () -> Void
    @State private var reviewed = false
    @State private var requestId = UUID()
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Review \(items.count) personalized emails").font(.headline)
            Text("From: \(model.sender ?? "Connect Gmail in Email settings")").font(.callout)
            Text("Each recipient receives only their own message. Sending continues in the background, at up to 50 messages/hour and 200 recipients/day. You can pause from Sales; a message already in progress may finish.").font(.caption).foregroundStyle(.secondary)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(items) { item in
                        VStack(alignment: .leading, spacing: 6) {
                            Text("To: \(item.email)").bold()
                            Text(item.subject).bold()
                            Text(item.body).textSelection(.enabled)
                        }.font(.callout).padding(12).frame(maxWidth: .infinity, alignment: .leading)
                            .background(.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }.frame(height: 360)
            Toggle("I reviewed these recipients and messages", isOn: $reviewed)
            if let error = model.error { Text(error).font(.caption).foregroundStyle(.orange) }
            HStack {
                Button("Cancel", action: close); Spacer()
                Button("Send \(items.count) emails") { Task {
                    await model.perform { try await model.send(items, campaignId: campaignId, requestId: requestId) }
                    if model.error == nil { close() }
                }}.buttonStyle(.borderedProminent).disabled(!reviewed || model.sender == nil || items.isEmpty)
            }
        }.padding(20).frame(width: 700).disabled(model.busy).task { await model.loadSender() }
    }
}
