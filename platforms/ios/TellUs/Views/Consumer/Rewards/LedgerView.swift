import SwiftUI

struct LedgerView: View {
    @State private var vm = LedgerViewModel()

    var body: some View {
        List {
            ForEach(vm.entries) { entry in
                HStack {
                    VStack(alignment: .leading) {
                        Text(entry.description ?? entry.reason.replacingOccurrences(of: "_", with: " ").capitalized)
                        Text(Formatters.relativeString(from: entry.created_at))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(entry.delta > 0 ? "+\(entry.delta)" : "\(entry.delta)")
                        .foregroundStyle(entry.delta >= 0 ? .green : .red)
                        .bold()
                }
                .onAppear {
                    if entry.id == vm.entries.last?.id { Task { await vm.loadMore() } }
                }
            }
            if vm.isLoading { ProgressView().frame(maxWidth: .infinity) }
        }
        .navigationTitle("Ledger")
        .task { await vm.loadMore() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
