import SwiftUI

struct FeedbackListView: View {
    @State private var vm = FeedbackListViewModel()

    var body: some View {
        VStack(spacing: 0) {
            FeedbackFilterBar(vm: vm)

            if vm.reports.isEmpty && !vm.isLoading {
                EmptyState(icon: "bubble.left.and.text.bubble.right", title: "No feedback yet")
                Spacer()
            } else {
                List(vm.reports) { report in
                    NavigationLink {
                        ReportDetailView(id: report.id)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(report.title ?? report.category.rawValue.capitalized).font(.subheadline.bold())
                                Spacer()
                                SentimentBadge(sentiment: report.sentiment)
                            }
                            HStack {
                                StatusChip(text: report.status.rawValue)
                                if let rewardStatus = report.reward_status {
                                    StatusChip(text: "reward: \(rewardStatus.rawValue)", tint: .purple)
                                }
                            }
                        }
                    }
                    .onAppear {
                        if report.id == vm.reports.last?.id { Task { await vm.load(reset: false) } }
                    }
                    .themedRow()
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
        }
        .themedContainer()
        .navigationTitle("Feedback")
        .task { await vm.load(reset: true) }
        .refreshable { await vm.load(reset: true) }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
