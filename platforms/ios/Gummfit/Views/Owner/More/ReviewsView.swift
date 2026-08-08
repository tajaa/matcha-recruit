import SwiftUI

struct ReviewsView: View {
    let site: CappeSite

    @State private var vm = ReviewsViewModel()

    var body: some View {
        Group {
            if vm.isLoading && vm.reviews.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.reviews.isEmpty {
                ContentUnavailableView("No reviews yet", systemImage: "star")
            } else {
                List {
                    ForEach(vm.reviews) { review in
                        ReviewRow(review: review, onModerate: { status in
                            Task { await vm.setStatus(siteId: site.id, reviewId: review.id, status: status) }
                        })
                    }
                    .onDelete { offsets in
                        for index in offsets {
                            let review = vm.reviews[index]
                            Task { await vm.delete(siteId: site.id, reviewId: review.id) }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Reviews")
        .task { await vm.load(siteId: site.id) }
        .refreshable { await vm.load(siteId: site.id) }
    }
}

private struct ReviewRow: View {
    let review: CappeReview
    let onModerate: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(review.author_name).font(.subheadline.bold())
                if let rating = review.rating {
                    HStack(spacing: 1) {
                        ForEach(0..<5, id: \.self) { i in
                            Image(systemName: i < rating ? "star.fill" : "star")
                                .font(.caption2)
                                .foregroundStyle(.yellow)
                        }
                    }
                }
                Spacer()
                Text(review.status.capitalized).font(.caption2).foregroundStyle(GummfitTheme.textDim)
            }
            Text(review.body).font(.caption)
            Picker("Moderate", selection: Binding(get: { review.status }, set: onModerate)) {
                Text("Approve").tag("approved")
                Text("Hide").tag("hidden")
                Text("Pending").tag("pending")
            }
            .pickerStyle(.segmented)
        }
        .padding(.vertical, 4)
    }
}
