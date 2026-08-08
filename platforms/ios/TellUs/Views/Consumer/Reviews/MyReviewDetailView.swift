import SwiftUI

struct MyReviewDetailView: View {
    let initialReview: MyReview
    @Bindable var vm: MyReviewsViewModel

    @State private var title: String
    @State private var description: String
    @State private var rating: Int
    @State private var showWithdrawConfirm = false
    @Environment(\.dismiss) private var dismiss

    /// vm.reviews is refetched by refetchOnceForExpiredMedia (and by
    /// save/withdraw) to re-mint media URLs — read live from the VM so this
    /// stays a struct constant only until the first refresh, instead of a
    /// permanently stale capture from the list row that pushed this view.
    private var review: MyReview {
        vm.reviews.first(where: { $0.id == initialReview.id }) ?? initialReview
    }

    init(review: MyReview, vm: MyReviewsViewModel) {
        self.initialReview = review
        self.vm = vm
        _title = State(initialValue: review.title ?? "")
        _description = State(initialValue: review.description ?? "")
        _rating = State(initialValue: review.rating ?? 0)
    }

    var body: some View {
        Form {
            Section {
                StatusChip(text: review.review_state.rawValue, tint: review.review_state == .published ? .green : .orange)
            }

            Section("Your review") {
                TextField("Title", text: $title).disabled(!review.isEditable)
                TextField("Description", text: $description, axis: .vertical).disabled(!review.isEditable)
                HStack {
                    ForEach(1...5, id: \.self) { star in
                        Image(systemName: star <= rating ? "star.fill" : "star")
                            .foregroundStyle(.yellow)
                            .onTapGesture { if review.isEditable { rating = star } }
                    }
                }
            }

            if !review.media.isEmpty {
                Section("Photos") {
                    ScrollView(.horizontal) {
                        HStack {
                            ForEach(review.media) { media in
                                Group {
                                    if media.media_type == .video {
                                        MediaVideoView(media: media) { vm.refetchOnceForExpiredMedia(reviewId: review.id) }
                                    } else {
                                        AsyncMediaImage(media: media) { vm.refetchOnceForExpiredMedia(reviewId: review.id) }
                                    }
                                }
                                .frame(width: 80, height: 80)
                            }
                        }
                    }
                }
            }

            if let reply = review.brand_public_reply {
                Section("Brand reply") { Text(reply) }
            }

            if let threadId = review.dm_thread_id {
                Section {
                    NavigationLink("Messages") { DmThreadView(vm: DmThreadViewModel(threadId: threadId)) }
                }
            }

            if review.hearted {
                Label("Hearted by the brand", systemImage: "heart.fill").foregroundStyle(.pink)
            }

            // Only a published review is likeable — the server 404s one still
            // inside its 48h hold, or withdrawn.
            if review.review_state == .published {
                Section {
                    LikeButton(
                        target: .report, id: review.id,
                        count: review.likeCount, liked: review.likedByMe,
                        onError: { vm.error = $0 }
                    )
                }
            }

            if review.isEditable {
                Section {
                    Button("Save changes") {
                        Task {
                            await vm.save(id: review.id, MyReviewUpdate(title: title, description: description, rating: rating))
                            dismiss()
                        }
                    }
                }
                Section {
                    Button("Withdraw review", role: .destructive) { showWithdrawConfirm = true }
                }
            }

            if let error = vm.error {
                Section { Text(error).foregroundStyle(.red).font(.footnote) }
            }
        }
        .navigationTitle(review.brand_name)
        .confirmationDialog("Withdraw this review?", isPresented: $showWithdrawConfirm, titleVisibility: .visible) {
            Button("Withdraw", role: .destructive) {
                Task { await vm.withdraw(id: review.id); dismiss() }
            }
        }
    }
}
