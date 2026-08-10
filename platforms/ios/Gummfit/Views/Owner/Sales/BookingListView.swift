import SwiftUI

struct BookingListView: View {
    let site: CappeSite

    @State private var vm = BookingsListViewModel()
    @State private var declineTarget: CappeBooking?
    @State private var declineReason = ""
    @State private var showDecline = false

    var body: some View {
        Group {
            if vm.isLoading && vm.bookings.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.bookings.isEmpty {
                ContentUnavailableView("No bookings yet", systemImage: "calendar")
            } else {
                List(vm.bookings) { booking in
                    BookingRow(booking: booking)
                        .gummfitListRow()
                        .swipeActions {
                            if booking.requires_approval && booking.status == .pending {
                                Button("Accept") { Task { await vm.accept(siteId: site.id, bookingId: booking.id) } }
                                    .tint(GummfitTheme.accent)
                                Button("Decline", role: .destructive) {
                                    declineTarget = booking
                                    declineReason = ""
                                    showDecline = true
                                }
                            }
                        }
                }
                .listStyle(.plain)
                .gummfitListBackground()
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .alert("Decline booking", isPresented: $showDecline, presenting: declineTarget) { target in
            TextField("Reason (optional)", text: $declineReason)
            Button("Decline", role: .destructive) {
                Task { await vm.decline(siteId: site.id, bookingId: target.id, reason: declineReason.isEmpty ? nil : declineReason) }
            }
            Button("Cancel", role: .cancel) {}
        }
        .task { await vm.load(siteId: site.id) }
        .refreshable { await vm.load(siteId: site.id) }
    }
}

private struct BookingRow: View {
    let booking: CappeBooking

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(booking.customer_name ?? booking.customer_email ?? "Booking")
                    .font(.subheadline.bold())
                    .foregroundStyle(GummfitTheme.textPrimary)
                Text(booking.starts_at).font(.caption).foregroundStyle(GummfitTheme.textDim)
                if let staffName = booking.staff_name {
                    Text(staffName).font(.caption2).foregroundStyle(GummfitTheme.textDim)
                }
            }
            Spacer()
            Text(booking.requires_approval && booking.status == .pending ? "Needs review" : booking.status.rawValue.capitalized)
                .font(.caption2.bold())
                .foregroundStyle(booking.requires_approval && booking.status == .pending ? .orange : GummfitTheme.textDim)
        }
    }
}
