import SwiftUI
import Observation

@MainActor @Observable final class MarketingViewModel: LoadableVM {
    var subscribers: [CappeSubscriber] = []; var campaigns: [CappeCampaign] = []; var forms: [CappeForm] = []; var posts: [CappePost] = []
    var isLoading = false; var error: String?
    func load(_ siteId: String) async { await withLoad { async let a = MarketingService.shared.subscribers(siteId); async let b = MarketingService.shared.campaigns(siteId); async let c = MarketingService.shared.forms(siteId); async let d = MarketingService.shared.posts(siteId); self.subscribers = try await a; self.campaigns = try await b; self.forms = try await c; self.posts = try await d } }
    func send(_ siteId: String, campaign: CappeCampaign) async { do { let updated = try await MarketingService.shared.sendCampaign(siteId, campaign.id); if let i = campaigns.firstIndex(where: {$0.id == campaign.id}) { campaigns[i] = updated } } catch { self.error = error.localizedDescription } }
}

struct MarketingView: View {
    let site: CappeSite; @State private var vm = MarketingViewModel(); @State private var adding: String?
    var body: some View { List {
        Section("Subscribers") { ForEach(vm.subscribers) { subscriber in Text(subscriber.name ?? subscriber.email).badge(subscriber.status).swipeActions { Button("Delete", role: .destructive) { Task { try? await MarketingService.shared.deleteSubscriber(site.id, subscriber.id); await vm.load(site.id) } } } }; Button("Add subscriber", systemImage: "plus") { adding = "subscriber" } }
        Section("Campaigns") { ForEach(vm.campaigns) { campaign in HStack { VStack(alignment: .leading) { Text(campaign.subject); Text("\(campaign.recipient_count) recipients").font(.caption).foregroundStyle(.secondary) }; Spacer(); if campaign.status == "draft" { Button("Send") { Task { await vm.send(site.id, campaign: campaign) } } }; Text(campaign.status).font(.caption) }.swipeActions { Button("Delete", role: .destructive) { Task { try? await MarketingService.shared.deleteCampaign(site.id, campaign.id); await vm.load(site.id) } } } }; Button("New campaign", systemImage: "plus") { adding = "campaign" } }
        Section("Forms") { ForEach(vm.forms) { form in NavigationLink { FormSubmissionsView(siteId: site.id, form: form) } label: { Text(form.name).badge(form.status) }.swipeActions { Button("Delete", role: .destructive) { Task { try? await MarketingService.shared.deleteForm(site.id, form.id); await vm.load(site.id) } } } }; Button("New form", systemImage: "plus") { adding = "form" } }
        Section("Blog") { ForEach(vm.posts) { post in Text(post.title).badge(post.status).swipeActions { Button("Delete", role: .destructive) { Task { try? await MarketingService.shared.deletePost(site.id, post.id); await vm.load(site.id) } } } }; Button("New post", systemImage: "plus") { adding = "post" } }
    }.navigationTitle("Marketing").overlay(alignment: .top) { ErrorBanner(message: vm.error) }.task { await vm.load(site.id) }.refreshable { await vm.load(site.id) }.sheet(item: $adding) { kind in MarketingCreateSheet(siteId: site.id, kind: kind) { await vm.load(site.id) } }
    }
}
private struct FormSubmissionsView: View {
    let siteId: String; let form: CappeForm; @State private var submissions: [CappeFormSubmission] = []; @State private var error: String?
    var body: some View { List(submissions) { submission in VStack(alignment: .leading) { Text(submission.submitter_email ?? "Anonymous").font(.headline); Text(submission.created_at).font(.caption).foregroundStyle(.secondary); ForEach(submission.data.keys.sorted(), id: \.self) { Text("\($0): \(String(describing: submission.data[$0]!))").font(.caption) } }.swipeActions { if !submission.is_read { Button("Read") { Task { _ = try? await MarketingService.shared.markRead(siteId, form.id, submission.id); await load() } }; Button("Delete", role: .destructive) { Task { try? await MarketingService.shared.deleteSubmission(siteId, form.id, submission.id); await load() } } } } }.navigationTitle(form.name).overlay(alignment: .top) { ErrorBanner(message: error) }.task { await load() } }
    private func load() async { do { submissions = try await MarketingService.shared.submissions(siteId, form.id) } catch { self.error = error.localizedDescription } }
}

private struct MarketingCreateSheet: View {
    let siteId, kind: String; let reload: () async -> Void; @Environment(\.dismiss) private var dismiss; @State private var title = ""; @State private var detail = ""; @State private var error: String?
    var body: some View { NavigationStack { Form { ErrorBanner(message: error); TextField(kind == "subscriber" ? "Email" : "Title", text: $title); if kind != "subscriber" { TextField(kind == "campaign" ? "Message (HTML)" : "Details", text: $detail, axis: .vertical) } }.navigationTitle("New \(kind.capitalized)").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(title.trimmingCharacters(in: .whitespaces).isEmpty) } } } }
    private func save() async { do { switch kind { case "subscriber": _ = try await MarketingService.shared.addSubscriber(siteId, CappeSubscriberCreate(email: title, name: nil)); case "campaign": _ = try await MarketingService.shared.createCampaign(siteId, CappeCampaignCreate(subject: title, body_html: detail.emptyToNil, from_name: nil, scheduled_at: nil)); case "form": _ = try await MarketingService.shared.createForm(siteId, CappeFormCreate(name: title, slug: nil, fields: [], status: "active")); default: _ = try await MarketingService.shared.createPost(siteId, CappePostCreate(title: title, slug: nil, excerpt: detail.emptyToNil, body: nil, cover_image_url: nil, status: "draft")) }; await reload(); dismiss() } catch { self.error = error.localizedDescription } }
}
private extension String { var emptyToNil: String? { isEmpty ? nil : self } }
