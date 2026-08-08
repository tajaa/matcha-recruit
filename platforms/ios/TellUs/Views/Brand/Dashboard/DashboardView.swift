import SwiftUI

struct DashboardView: View {
    @State private var vm = FeedbackListViewModel(pageSize: 5)
    @State private var didLoad = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let stats = vm.stats {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        statTile("Total", stats.total, .primary)
                        statTile("New", stats.new, .blue)
                        statTile("Positive", stats.positive, .green)
                        statTile("Neutral", stats.neutral, .gray)
                        statTile("Negative", stats.negative, .red)
                    }
                    .padding(.horizontal)

                    if !stats.by_category.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("By category").font(.headline)
                            ForEach(stats.by_category.sorted { $0.value > $1.value }, id: \.key) { key, count in
                                HStack {
                                    Text(key.capitalized)
                                    Spacer()
                                    Text("\(count)").foregroundStyle(.secondary)
                                }
                                .font(.subheadline)
                            }
                        }
                        .padding()
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                        .padding(.horizontal)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Recent feedback").font(.headline).padding(.horizontal)
                    ForEach(vm.reports) { report in
                        NavigationLink {
                            ReportDetailView(id: report.id)
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(report.title ?? report.category.rawValue.capitalized).font(.subheadline.bold())
                                    Spacer()
                                    SentimentBadge(sentiment: report.sentiment)
                                }
                                if let description = report.description {
                                    Text(description).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                                }
                            }
                            .padding()
                            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal)
                    }
                }
            }
            .padding(.vertical)
        }
        .navigationTitle("Dashboard")
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
            Text("\(value)").font(.title.bold()).foregroundStyle(color)
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}
