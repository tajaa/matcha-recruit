import SwiftUI

struct OrderListView: View {
    let site: CappeSite

    @State private var vm = OrdersListViewModel()

    var body: some View {
        Group {
            if vm.isLoading && vm.orders.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.orders.isEmpty {
                ContentUnavailableView("No orders yet", systemImage: "bag")
            } else {
                List(vm.orders) { order in
                    NavigationLink {
                        OrderDetailView(site: site, orderId: order.id)
                    } label: {
                        OrderRow(order: order)
                    }
                    .gummfitListRow()
                }
                .listStyle(.plain)
                .gummfitListBackground()
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .task { await vm.load(siteId: site.id) }
        .refreshable { await vm.load(siteId: site.id) }
    }
}

private struct OrderRow: View {
    let order: CappeOrder

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(order.customer_name ?? order.customer_email ?? "Order")
                    .gummfitSectionTitle()
                Text(Formatters.cents(order.total_cents ?? order.subtotal_cents, currency: order.currency))
                    .font(.caption)
                    .foregroundStyle(GummfitTheme.textDim)
            }
            Spacer()
            if order.requires_approval && order.status == .pending {
                GummfitStatusPill(status: "pending", label: "Needs review")
            } else {
                GummfitStatusPill(status: order.status.rawValue)
            }
        }
    }
}
