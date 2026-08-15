import SwiftUI

struct MyReviewsView: View {
    @State private var vm = MyReviewsViewModel()

    var body: some View {
        Group {
            if vm.reviews.isEmpty && !vm.isLoading {
                EmptyState(icon: "star.bubble", title: "No reviews yet")
            } else {
                List(vm.reviews) { review in
                    NavigationLink {
                        MyReviewDetailView(review: review, vm: vm)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(review.brand_name).font(.interHeadline)
                            if let title = review.title { Text(title).font(.interSubheadline) }
                            HStack {
                                StatusChip(text: review.review_state.rawValue, tint: review.review_state == .published ? .green : .orange)
                                Spacer()
                                if let rating = review.rating {
                                    Label("\(rating)", systemImage: "star.fill").font(.interCaption).foregroundStyle(.yellow)
                                }
                            }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("My Reviews")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
