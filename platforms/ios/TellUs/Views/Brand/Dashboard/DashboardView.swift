import SwiftUI

struct DashboardView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = FeedbackListViewModel(pageSize: 5)
    @State private var didLoad = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let stats = vm.stats {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        statTile("Total", stats.total, .white)
                        statTile("New", stats.new, TU.ember)
                        statTile("Positive", stats.positive, .green)
                        statTile("Neutral", stats.neutral, TU.textDim)
                        statTile("Negative", stats.negative, .red)
                    }
                    .padding(.horizontal)

                    if !stats.by_category.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("By category").font(.interHeadline).foregroundStyle(.white.opacity(0.92))
                            ForEach(stats.by_category.sorted { $0.value > $1.value }, id: \.key) { key, count in
                                HStack {
                                    Text(key.capitalized)
                                    Spacer()
                                    Text("\(count)").foregroundStyle(TU.textDim)
                                }
                                .font(.interSubheadline)
                            }
                        }
                        .padding()
                        .glassCard(radius: 10)
                        .padding(.horizontal)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Recent feedback").font(.interHeadline).foregroundStyle(.white.opacity(0.92)).padding(.horizontal)
                    ForEach(vm.reports) { report in
                        NavigationLink {
                            ReportDetailView(id: report.id)
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(report.title ?? report.category.rawValue.capitalized).font(.interSubheadline.bold())
                                    Spacer()
                                    SentimentBadge(sentiment: report.sentiment)
                                }
                                if let description = report.description {
                                    Text(description).font(.interCaption).foregroundStyle(TU.textDim).lineLimit(2)
                                }
                            }
                            .padding()
                            .glassCard(radius: 10)
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal)
                    }
                }
            }
            .padding(.vertical)
        }
        .themedScreen()
        .navigationTitle("Dashboard")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { NotificationsView() } label: {
                    Image(systemName: "bell.fill")
                        .foregroundStyle(.white.opacity(0.85))
                        .overlay(alignment: .topTrailing) {
                            if appState.unreadCount > 0 {
                                Text(appState.unreadCount >= 100 ? "99+" : "\(appState.unreadCount)")
                                    .font(.interCaption2.bold())
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 2)
                                    .background(TU.ember, in: Capsule())
                                    .foregroundStyle(TU.ink)
                                    .offset(x: 10, y: -10)
                            }
                        }
                }
                .accessibilityLabel(
                    appState.unreadCount > 0
                        ? "Alerts, \(appState.unreadCount) unread"
                        : "Alerts"
                )
            }
        }
        .task {
            guard !didLoad else { return }
            didLoad = true
            await vm.loadStats()
            await vm.load(reset: true)
        }
        .refreshable {
            await vm.loadStats()
            await vm.load(reset: true)
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }

    private func statTile(_ label: String, _ value: Int, _ color: Color) -> some View {
        VStack {
            Text("\(value)").font(.interTitle.bold()).foregroundStyle(color)
            Text(label).font(.interCaption).foregroundStyle(TU.textDim)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .glassCard(radius: 10)
    }
}
