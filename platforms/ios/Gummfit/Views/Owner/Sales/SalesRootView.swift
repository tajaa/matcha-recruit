import SwiftUI

/// Sales tab root — segmented Orders|Bookings, matching HomeView's top-level
/// NavigationStack shape.
struct SalesRootView: View {
    let site: CappeSite

    @State private var segment = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $segment) {
                    Text("Orders").tag(0)
                    Text("Bookings").tag(1)
                }
                .pickerStyle(.segmented)
                .padding()

                if segment == 0 {
                    OrderListView(site: site)
                } else {
                    BookingListView(site: site)
                }
            }
            .background(Color(GummfitTheme.background).ignoresSafeArea())
            .navigationTitle("Sales")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink("Setup") { BookingSetupView(site: site) }
                }
            }
        }
    }
}
