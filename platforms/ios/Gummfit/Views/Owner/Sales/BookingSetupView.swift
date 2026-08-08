import SwiftUI

/// Sub-nav to booking configuration screens. Rider is hidden for business
/// accounts — it's a personal-creator-only capability (rider.py:31-47).
struct BookingSetupView: View {
    let site: CappeSite

    @Environment(AppState.self) private var appState

    var body: some View {
        List {
            NavigationLink("Booking types") { BookingTypesView(site: site) }
            NavigationLink("Availability") { AvailabilityView(site: site) }
            NavigationLink("Rate rules") { RateRulesView(site: site) }
            if appState.account?.account_type == .personal {
                NavigationLink("Rider") { RiderView(site: site) }
            }
        }
        .navigationTitle("Booking setup")
    }
}
