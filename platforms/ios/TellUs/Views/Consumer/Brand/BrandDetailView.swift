import SwiftUI

/// Native replacement for the old "See reviews" Safari handoff
/// (PlacesView used to open `webOrigin + "/tellus/b/\(slug)"`). Serves both
/// claimed and unclaimed brands — GET /b/{slug} is public either way (every
/// unclaimed brand carries an active community-feedback link, per
/// tellus/CLAUDE.md's "Places / reviews on unclaimed businesses" invariant).
struct BrandDetailView: View {
    let slug: String
    @State private var vm: BrandDetailViewModel
    @State private var messageTarget: MessageTarget?
    @State private var openedThread: DmThread?

    init(slug: String) {
        self.slug = slug
        _vm = State(initialValue: BrandDetailViewModel(slug: slug))
    }

    var body: some View {
        Group {
            if let page = vm.page {
                List {
                    Section {
                        header(page)
                    }
                    .listRowBackground(TU.inkRaised)

                    if page.reviews.isEmpty {
                        EmptyState(icon: "bubble.left", title: "No reviews yet")
                            .listRowBackground(TU.inkRaised)
                    } else {
                        Section("Reviews") {
                            ForEach(page.reviews) { review in
                                ReviewRow(review: review)
                            }
                        }
                        .listRowBackground(TU.inkRaised)
                    }
                }
                .listStyle(.insetGrouped)
                .themedScreen()
            } else if vm.isLoading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                EmptyState(icon: "wifi.exclamationmark", title: "Couldn't load this business")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .themedContainer()
            }
        }
        .navigationTitle(vm.page?.brand_name ?? "Business")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
        .navigationDestination(isPresented: $vm.showIntake) {
            if let token = vm.page?.intake_token { IntakeLoaderView(token: token) }
        }
        .navigationDestination(isPresented: $vm.showBoard) {
            BoardFeedView(slug: slug, brandName: vm.page?.brand_name ?? "")
        }
        .sheet(item: $messageTarget) { target in
            CommsComposerSheet(slug: target.slug) { thread in openedThread = thread }
        }
        .navigationDestination(item: $openedThread) { thread in
            DmThreadView(vm: DmThreadViewModel(thread: thread))
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }

    @ViewBuilder
    private func header(_ page: TellusPublicBrandPage) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                if let rating = page.avg_rating {
                    Label(String(format: "%.1f", rating), systemImage: "star.fill")
                }
                Text("\(page.review_count) review\(page.review_count == 1 ? "" : "s")")
                    .foregroundStyle(TU.textDim)
            }
            .font(.interSubheadline)

            if let city = page.city {
                Text([city, page.state].compactMap { $0 }.joined(separator: ", "))
                    .font(.interFootnote).foregroundStyle(TU.textDim)
            }

            HStack(spacing: 8) {
                if page.claimed {
                    Button(vm.followed ? "Following" : "Follow") { Task { await vm.toggleFollow() } }
                        .buttonStyle(.bordered).tint(vm.followed ? TU.textDim : TU.ember)
                }
                if page.has_board {
                    Button("Request to join board") { vm.showBoard = true }
                        .buttonStyle(.bordered).tint(TU.textDim)
                }
                if page.messaging_enabled {
                    Button("Message") { messageTarget = MessageTarget(slug: slug) }
                        .buttonStyle(.bordered).tint(TU.textDim)
                }
                if !page.claimed, page.intake_token != nil {
                    Button("Leave feedback") { vm.showIntake = true }
                        .buttonStyle(.borderedProminent).tint(TU.ember)
                }
            }
            .font(.interCaption)
            .controlSize(.small)
        }
        .padding(.vertical, 4)
    }
}

private struct ReviewRow: View {
    let review: TellusPublicReview

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Label("\(review.rating)", systemImage: "star.fill")
                Text(review.reviewer_name).font(.interSubheadline.bold())
                Spacer()
                if let store = review.store_name {
                    Text(store).font(.interCaption2).foregroundStyle(TU.textDim)
                }
            }
            if let title = review.title { Text(title).font(.interSubheadline) }
            if let description = review.description { Text(description).font(.interFootnote) }
            if let reply = review.brand_reply {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Business reply").font(.interCaption2.bold()).foregroundStyle(TU.ember)
                    Text(reply).font(.interCaption)
                }
                .padding(8)
                .background(TU.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
        }
        .padding(.vertical, 4)
    }
}

private struct MessageTarget: Identifiable {
    let slug: String
    var id: String { slug }
}
