import SwiftUI

struct SiteSettingsView: View {
    let site: CappeSite; @Environment(\.dismiss) private var dismiss; @State private var name: String; @State private var subdomain: String; @State private var timezone: String; @State private var taxRate: String; @State private var taxLabel: String; @State private var shippingFlat: String; @State private var freeShipping: String; @State private var receiptPrefix: String; @State private var error: String?
    init(site: CappeSite) {
        self.site = site
        _name = State(initialValue: site.name)
        _subdomain = State(initialValue: site.subdomain ?? "")
        _timezone = State(initialValue: site.timezone ?? "UTC")
        _taxRate = State(initialValue: site.tax_rate_bps.map(String.init) ?? "")
        _taxLabel = State(initialValue: site.tax_label ?? "")
        _shippingFlat = State(initialValue: site.shipping_flat_cents.map(String.init) ?? "")
        _freeShipping = State(initialValue: site.shipping_free_threshold_cents.map(String.init) ?? "")
        _receiptPrefix = State(initialValue: site.receipt_prefix ?? "")
    }
    private var themePreset: CappePublishedThemePreset {
        CappePublishedThemeCatalog.resolved(for: site.theme_config)
    }

    var body: some View {
        Form {
            ErrorBanner(message: error)
            Section("Identity") {
                TextField("Site name", text: $name)
                TextField("Subdomain", text: $subdomain).textInputAutocapitalization(.never)
                TextField("Timezone", text: $timezone)
            }
            Section("Checkout") {
                TextField("Tax rate (basis points)", text: $taxRate).keyboardType(.numberPad)
                TextField("Tax label", text: $taxLabel)
                TextField("Flat shipping (cents)", text: $shippingFlat).keyboardType(.numberPad)
                TextField("Free shipping threshold (cents)", text: $freeShipping).keyboardType(.numberPad)
                TextField("Receipt prefix", text: $receiptPrefix)
            }
            Section("Public site design") {
                HStack(spacing: GummfitSpacing.md) {
                    ForEach([
                        themePreset.swatch.background,
                        themePreset.swatch.surface,
                        themePreset.swatch.brand,
                        themePreset.swatch.text,
                    ], id: \.self) { hex in
                        Circle()
                            .fill(Color(hex: hex))
                            .frame(width: 24, height: 24)
                            .overlay { Circle().stroke(GummfitTheme.inputBorder, lineWidth: 1) }
                    }
                    VStack(alignment: .leading, spacing: GummfitSpacing.xs) {
                        Text(themePreset.name).font(GummfitTypography.label).foregroundStyle(GummfitTheme.textPrimary)
                        if themePreset.premium { GummfitStatusPill(status: "approved", label: "Premium") }
                    }
                }
                Text(themePreset.blurb).gummfitMuted()
                LabeledContent("Fonts", value: "\(themePreset.headingFont) / \(themePreset.bodyFont)")
                LabeledContent("Radius", value: themePreset.radius.uppercased())
                Text("Theme editing and page editing stay on web.").gummfitMuted()
                NavigationLink("Preview selected theme") {
                    ScrollView { CappePublishedThemePreview(preset: themePreset) }
                }
            }
            Section("Publishing") {
                Text("Publishing and page editing stay on web.").gummfitMuted()
                Link("Open web settings", destination: URL(string: "\(APIClient.shared.webOrigin)/cappe/sites/\(site.slug)/settings")!)
            }
        }
        .navigationTitle("Site settings")
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") { Task { await save() } }
                    .buttonStyle(.gummfitGhost)
                    .disabled(name.isEmpty)
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: error) }
        .gummfitListBackground()
        .gummfitScreenChrome()
    }
    private func save() async { do { _ = try await SitesService.shared.update(siteId: site.id, CappeSiteUpdate(name: name, subdomain: subdomain.isEmpty ? nil : subdomain, timezone: timezone, tax_label: taxLabel.isEmpty ? nil : taxLabel, shipping_label: nil, receipt_prefix: receiptPrefix.isEmpty ? .clear : .value(receiptPrefix), status: nil, tax_rate_bps: Int(taxRate), shipping_flat_cents: Int(shippingFlat), shipping_free_threshold_cents: freeShipping.isEmpty ? .clear : .value(Int(freeShipping) ?? 0), is_multi_location: nil)); dismiss() } catch { self.error = error.localizedDescription } }
}
