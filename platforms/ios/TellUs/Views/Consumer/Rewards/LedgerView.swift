import SwiftUI

struct LedgerView: View {
    @State private var entries: [LedgerEntry] = []
    @State private var isLoading = false
    @State private var offset = 0
    @State private var hasMore = true

    var body: some View {
        List {
            ForEach(entries) { entry in
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
                    if entry.id == entries.last?.id { Task { await loadMore() } }
                }
            }
            if isLoading { ProgressView().frame(maxWidth: .infinity) }
        }
        .navigationTitle("Ledger")
        .task { await loadMore() }
    }

    private func loadMore() async {
        guard hasMore, !isLoading else { return }
        isLoading = true; defer { isLoading = false }
        if let page = try? await RewardsService.shared.ledger(limit: 50, offset: offset) {
            entries += page
            offset += page.count
            hasMore = page.count == 50
        }
    }
}
