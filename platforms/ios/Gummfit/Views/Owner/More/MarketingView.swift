import SwiftUI
import Observation

@MainActor @Observable final class MarketingViewModel: LoadableVM {
    var subscribers: [CappeSubscriber] = []; var campaigns: [CappeCampaign] = []; var forms: [CappeForm] = []; var posts: [CappePost] = []
    var isLoading = false; var error: String?
    func load(_ siteId: String) async { await withLoad { async let a = MarketingService.shared.subscribers(siteId); async let b = MarketingService.shared.campaigns(siteId); async let c = MarketingService.shared.forms(siteId); async let d = MarketingService.shared.posts(siteId); self.subscribers = try await a; self.campaigns = try await b; self.forms = try await c; self.posts = try await d } }
    func send(_ siteId: String, campaign: CappeCampaign) async { do { let updated = try await MarketingService.shared.sendCampaign(siteId, campaign.id); if let i = campaigns.firstIndex(where: {$0.id == campaign.id}) { campaigns[i] = updated } } catch { self.error = error.localizedDescription } }
}

struct MarketingView: View {
    let site: CappeSite; @State private var vm = MarketingViewModel(); @State private var adding: String?; @State private var editing: MarketingEditTarget?; @State private var confirmCampaign: CappeCampaign?
    var body: some View {
        List {
            subscribersSection
            campaignsSection
            formsSection
            postsSection
        }
        .navigationTitle("Marketing")
        .listStyle(.insetGrouped)
        .gummfitListBackground()
        .gummfitScreenChrome()
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .task { await vm.load(site.id) }
        .refreshable { await vm.load(site.id) }
        .sheet(isPresented: Binding(get: { adding != nil }, set: { if !$0 { adding = nil } })) {
            if let kind = adding {
                MarketingCreateSheet(siteId: site.id, kind: kind) { await vm.load(site.id) }
            }
        }
        .sheet(item: $editing) { target in
            MarketingEditSheet(siteId: site.id, target: target) { await vm.load(site.id) }
        }
        .alert("Send campaign?", isPresented: Binding(get: { confirmCampaign != nil }, set: { if !$0 { confirmCampaign = nil } })) {
            Button("Send", role: .destructive) {
                if let campaign = confirmCampaign { Task { await vm.send(site.id, campaign: campaign) } }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This will send \(confirmCampaign?.subject ?? "the campaign") to subscribed recipients.")
        }
    }

    @ViewBuilder private var subscribersSection: some View {
        Section("Subscribers") {
            ForEach(vm.subscribers) { subscriber in
                HStack {
                    Text(subscriber.name ?? subscriber.email)
                    Spacer()
                    GummfitStatusPill(status: subscriber.status)
                }
                    .swipeActions {
                        Button("Delete", role: .destructive) {
                            Task { try? await MarketingService.shared.deleteSubscriber(site.id, subscriber.id); await vm.load(site.id) }
                        }
                    }
            }
            Button("Add subscriber", systemImage: "plus") { adding = "subscriber" }
        }
    }

    @ViewBuilder private var campaignsSection: some View {
        Section("Campaigns") {
            ForEach(vm.campaigns) { campaign in
                let status = campaign.status ?? "unknown"
                HStack {
                    VStack(alignment: .leading) {
                        Text(campaign.subject)
                        Text("\(campaign.recipient_count) recipients").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if status == "draft" { Button("Send") { confirmCampaign = campaign } }
                    GummfitStatusPill(status: status)
                }
                .contentShape(Rectangle())
                .onTapGesture { if ["draft", "scheduled"].contains(status) { editing = .campaign(campaign) } }
                .swipeActions {
                    Button("Delete", role: .destructive) {
                        Task { try? await MarketingService.shared.deleteCampaign(site.id, campaign.id); await vm.load(site.id) }
                    }
                }
            }
            Button("New campaign", systemImage: "plus") { adding = "campaign" }
        }
    }

    @ViewBuilder private var formsSection: some View {
        Section("Forms") {
            ForEach(vm.forms) { form in
                NavigationLink { FormBuilderView(siteId: site.id, form: form) { await vm.load(site.id) } } label: {
                    HStack {
                        Text(form.name)
                        Spacer()
                        GummfitStatusPill(status: form.status)
                    }
                }
                    .swipeActions {
                        Button("Delete", role: .destructive) {
                            Task { try? await MarketingService.shared.deleteForm(site.id, form.id); await vm.load(site.id) }
                        }
                    }
            }
            Button("New form", systemImage: "plus") { adding = "form" }
        }
    }

    @ViewBuilder private var postsSection: some View {
        Section("Blog") {
            ForEach(vm.posts) { post in
                HStack {
                    Text(post.title)
                    Spacer()
                    GummfitStatusPill(status: post.status)
                }
                    .contentShape(Rectangle())
                    .onTapGesture { editing = .post(post) }
                    .swipeActions {
                        Button("Delete", role: .destructive) {
                            Task { try? await MarketingService.shared.deletePost(site.id, post.id); await vm.load(site.id) }
                        }
                    }
            }
            Button("New post", systemImage: "plus") { adding = "post" }
        }
    }
}
private enum MarketingEditTarget: Identifiable { case campaign(CappeCampaign), post(CappePost); var id: String { switch self { case .campaign(let item): return "campaign-\(item.id)"; case .post(let item): return "post-\(item.id)" } } }
private struct MarketingEditSheet: View {
    let siteId: String; let target: MarketingEditTarget; let reload: () async -> Void; @Environment(\.dismiss) private var dismiss; @State private var title: String; @State private var bodyText: String; @State private var status: String; @State private var error: String?
    init(siteId: String, target: MarketingEditTarget, reload: @escaping () async -> Void) { self.siteId = siteId; self.target = target; self.reload = reload; switch target { case .campaign(let value): _title = State(initialValue: value.subject); _bodyText = State(initialValue: value.body_html ?? ""); _status = State(initialValue: value.status ?? "draft"); case .post(let value): _title = State(initialValue: value.title); _bodyText = State(initialValue: value.body ?? ""); _status = State(initialValue: value.status) } }
    var body: some View { NavigationStack { Form { ErrorBanner(message: error); TextField("Title", text: $title); TextField("Body", text: $bodyText, axis: .vertical); statusPicker }.navigationTitle("Edit").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(title.isEmpty) } } } }
    @ViewBuilder private var statusPicker: some View { switch target { case .campaign: Picker("Status", selection: $status) { Text("Draft").tag("draft"); Text("Scheduled").tag("scheduled"); Text("Cancelled").tag("cancelled") }; case .post: Picker("Status", selection: $status) { Text("Draft").tag("draft"); Text("Published").tag("published"); Text("Archived").tag("archived") } } }
    private func save() async { do { switch target { case .campaign(let item): _ = try await MarketingService.shared.updateCampaign(siteId, item.id, CappeCampaignUpdate(subject: title, body_html: bodyText, from_name: item.from_name, scheduled_at: item.scheduled_at, status: status)); case .post(let item): _ = try await MarketingService.shared.updatePost(siteId, item.id, CappePostUpdate(title: title, slug: item.slug, excerpt: item.excerpt, body: bodyText, cover_image_url: item.cover_image_url, status: status)) }; await reload(); dismiss() } catch { self.error = error.localizedDescription } }
}
private struct FormSubmissionsView: View {
    let siteId: String; let form: CappeForm; @State private var submissions: [CappeFormSubmission] = []; @State private var error: String?
    var body: some View { List(submissions) { submission in VStack(alignment: .leading) { Text(submission.submitter_email ?? "Anonymous").font(.headline); Text(submission.created_at).font(.caption).foregroundStyle(.secondary); ForEach(submission.data.keys.sorted(), id: \.self) { Text("\($0): \(String(describing: submission.data[$0]!))").font(.caption) } }.swipeActions { if !submission.is_read { Button("Read") { Task { _ = try? await MarketingService.shared.markRead(siteId, form.id, submission.id); await load() } } }; Button("Delete", role: .destructive) { Task { try? await MarketingService.shared.deleteSubmission(siteId, form.id, submission.id); await load() } } } }.navigationTitle(form.name).overlay(alignment: .top) { ErrorBanner(message: error) }.task { await load() } }
    private func load() async { do { submissions = try await MarketingService.shared.submissions(siteId, form.id) } catch { self.error = error.localizedDescription } }
}

private struct FormBuilderView: View {
    let siteId: String; let form: CappeForm; let reload: () async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name: String; @State private var status: String; @State private var fields: [CappeFormField]; @State private var addingField = false; @State private var error: String?
    init(siteId: String, form: CappeForm, reload: @escaping () async -> Void) { self.siteId = siteId; self.form = form; self.reload = reload; _name = State(initialValue: form.name); _status = State(initialValue: form.status); _fields = State(initialValue: form.fields) }
    var body: some View { Form { ErrorBanner(message: error); Section("Form") { TextField("Name", text: $name); Picker("Status", selection: $status) { Text("Active").tag("active"); Text("Draft").tag("draft"); Text("Archived").tag("archived") } }; Section("Fields") { ForEach($fields) { $field in VStack(alignment: .leading) { TextField("Key", text: $field.key); TextField("Label", text: $field.label); Picker("Type", selection: $field.type) { ForEach(["text", "email", "textarea", "number", "tel", "select", "checkbox", "date"], id: \.self) { Text($0.capitalized).tag($0) } }; if field.type == "select" { TextField("Options (comma-separated)", text: Binding(get: { field.options?.joined(separator: ", ") ?? "" }, set: { field.options = $0.csv.nilIfEmpty })) }; Toggle("Required", isOn: $field.required) }.swipeActions { Button("Delete", role: .destructive) { fields.removeAll { $0.key == field.key } } } }; Button("Add field", systemImage: "plus") { addingField = true } }; Section("Submissions") { NavigationLink("View submissions") { FormSubmissionsView(siteId: siteId, form: form) } } }.navigationTitle("Form builder").toolbar { ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(name.isEmpty) } }.sheet(isPresented: $addingField) { NewFormFieldSheet { fields.append($0) } }.overlay(alignment: .top) { ErrorBanner(message: error) } }
    private func save() async { do { _ = try await MarketingService.shared.updateForm(siteId, form.id, CappeFormUpdate(name: name, fields: fields, status: status)); await reload(); dismiss() } catch { self.error = error.localizedDescription } }
}

private struct NewFormFieldSheet: View {
    let add: (CappeFormField) -> Void; @Environment(\.dismiss) private var dismiss; @State private var key = ""; @State private var label = ""; @State private var type = "text"; @State private var options = ""; @State private var required = false
    var body: some View { NavigationStack { Form { TextField("Key", text: $key); TextField("Label", text: $label); Picker("Type", selection: $type) { ForEach(["text", "email", "textarea", "number", "tel", "select", "checkbox", "date"], id: \.self) { Text($0.capitalized).tag($0) } }; if type == "select" { TextField("Options (comma-separated)", text: $options) }; Toggle("Required", isOn: $required) }.navigationTitle("New field").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("Add") { add(CappeFormField(key: key, label: label, type: type, required: required, options: options.csv.nilIfEmpty)); dismiss() }.disabled(key.isEmpty || label.isEmpty) } } } }
}
private extension Array where Element == String { var nilIfEmpty: [String]? { isEmpty ? nil : self } }
private extension String { var csv: [String] { split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty } } }

private struct MarketingCreateSheet: View {
    let siteId, kind: String; let reload: () async -> Void; @Environment(\.dismiss) private var dismiss; @State private var title = ""; @State private var detail = ""; @State private var scheduledAt = ""; @State private var error: String?
    var body: some View { NavigationStack { Form { ErrorBanner(message: error); TextField(kind == "subscriber" ? "Email" : "Title", text: $title); if kind != "subscriber" { TextField(kind == "campaign" ? "Message (HTML)" : "Details", text: $detail, axis: .vertical) }; if kind == "campaign" { TextField("Schedule (ISO-8601, optional)", text: $scheduledAt).textInputAutocapitalization(.never) } }.navigationTitle("New \(kind.capitalized)").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(title.trimmingCharacters(in: .whitespaces).isEmpty) } } } }
    private func save() async { do { switch kind { case "subscriber": _ = try await MarketingService.shared.addSubscriber(siteId, CappeSubscriberCreate(email: title, name: nil)); case "campaign": _ = try await MarketingService.shared.createCampaign(siteId, CappeCampaignCreate(subject: title, body_html: detail.emptyToNil, from_name: nil, scheduled_at: scheduledAt.emptyToNil)); case "form": _ = try await MarketingService.shared.createForm(siteId, CappeFormCreate(name: title, slug: nil, fields: [], status: "active")); default: _ = try await MarketingService.shared.createPost(siteId, CappePostCreate(title: title, slug: nil, excerpt: detail.emptyToNil, body: nil, cover_image_url: nil, status: "draft")) }; await reload(); dismiss() } catch { self.error = error.localizedDescription } }
}
private extension String { var emptyToNil: String? { isEmpty ? nil : self } }
