import SwiftUI

struct SiteSettingsView: View {
    let site: CappeSite; @Environment(\.dismiss) private var dismiss; @State private var name: String; @State private var subdomain: String; @State private var timezone = "UTC"; @State private var error: String?
    init(site: CappeSite) { self.site = site; _name = State(initialValue: site.name); _subdomain = State(initialValue: site.subdomain ?? "") }
    var body: some View { Form { ErrorBanner(message: error); Section("Identity") { TextField("Site name", text: $name); TextField("Subdomain", text: $subdomain).textInputAutocapitalization(.never); TextField("Timezone", text: $timezone) }; Section("Publishing") { Text("Publishing and page editing stay on web.").font(.caption).foregroundStyle(.secondary); Link("Open web settings", destination: URL(string: "\(APIClient.shared.webOrigin)/cappe/sites/\(site.slug)/settings")!) } }.navigationTitle("Site settings").toolbar { ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(name.isEmpty) } }.overlay(alignment: .top) { ErrorBanner(message: error) } }
    private func save() async { do { _ = try await SitesService.shared.update(siteId: site.id, CappeSiteUpdate(name: name, subdomain: subdomain.isEmpty ? nil : subdomain, timezone: timezone, tax_label: nil, shipping_label: nil, receipt_prefix: nil, status: nil, tax_rate_bps: nil, shipping_flat_cents: nil, shipping_free_threshold_cents: nil, is_multi_location: nil)); dismiss() } catch { self.error = error.localizedDescription } }
}
