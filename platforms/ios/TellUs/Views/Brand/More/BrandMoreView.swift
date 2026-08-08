import SwiftUI

/// Brand overflow tab. Stores/Listings/Settings/Billing rows are added in
/// their own commits as those screens land (13-16) — this starts with what
/// already exists so the tab isn't empty in the meantime.
struct BrandMoreView: View {
    var body: some View {
        List {
            Section {
                NavigationLink("Stores & QR codes") { StoresView() }
                NavigationLink("Reward listings") { BrandListingsView() }
                NavigationLink("Settings & prompts") { BrandSettingsView() }
            }
            Section {
                NavigationLink("Alerts") { NotificationsView() }
                NavigationLink("Account") { BrandAccountView() }
            }
        }
        .navigationTitle("More")
    }
}
