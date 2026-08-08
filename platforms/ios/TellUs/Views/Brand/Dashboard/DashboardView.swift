import SwiftUI

struct DashboardView: View {
    @State private var vm = FeedbackListViewModel()

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
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Recent feedback").font(.headline).padding(.horizontal)
                    ForEach(vm.reports.prefix(5)) { report in
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
