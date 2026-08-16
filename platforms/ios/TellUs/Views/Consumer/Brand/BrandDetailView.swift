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
        .sheet(item: $vm.shareItem) { item in
            InviteShareSheet(item: item).presentationDetents([.height(220)])
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }

    @ViewBuilder
    private func header(_ page: TellusPublicBrandPage) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let coverURL = page.cover_url.flatMap(URL.init) {
                AsyncImage(url: coverURL) { image in
                    image.resizable().aspectRatio(contentMode: .fill)
                } placeholder: {
                    Rectangle().fill(TU.surface)
                }
                .frame(height: 160)
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }

            if let tagline = page.tagline {
                Text(tagline).font(.interSubheadline).foregroundStyle(TU.textDim)
            }

            HStack(spacing: 6) {
                if let rating = page.avg_rating {
                    Label(String(format: "%.1f", rating), systemImage: "star.fill")
                }
                Text("\(page.review_count) review\(page.review_count == 1 ? "" : "s")")
                    .foregroundStyle(TU.textDim)
                if let category = page.category {
                    StatusChip(text: category, tint: TU.textDim)
                }
            }
            .font(.interSubheadline)

            if let city = page.city {
                Text([page.address, city, page.state].compactMap { $0 }.joined(separator: ", "))
                    .font(.interFootnote).foregroundStyle(TU.textDim)
            }

            if let website = page.website, let url = URL(string: website) {
                Link(website, destination: url)
                    .font(.interFootnote).foregroundStyle(TU.ember)
            }

            if let hours = page.hours, !hours.isEmpty {
                HoursDisclosure(hours: hours)
            }

            if let description = page.description {
                Text(description).font(.interFootnote)
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
                if !page.claimed {
                    Button(vm.isLoading ? "Inviting…" : "Invite") { Task { await vm.invite() } }
                        .buttonStyle(.bordered).tint(TU.textDim)
                        .disabled(vm.isLoading)
                }
            }
            .font(.interCaption)
            .controlSize(.small)

            if !page.claimed, page.invite_count > 0 {
                Text("\(page.invite_count) locals want them here")
                    .font(.interCaption2).foregroundStyle(TU.textDim)
            }
        }
        .padding(.vertical, 4)
    }
}

private struct HoursDisclosure: View {
    let hours: [String: String]
    @State private var expanded = false

    private static let dayOrder = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    var body: some View {
        DisclosureGroup("Hours", isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Self.dayOrder.filter { hours[$0] != nil }, id: \.self) { day in
                    HStack {
                        Text(day.capitalized).frame(width: 44, alignment: .leading)
                        Text(hours[day] ?? "")
                    }
                    .font(.interCaption).foregroundStyle(TU.textDim)
                }
            }
            .padding(.top, 4)
        }
        .font(.interFootnote)
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
