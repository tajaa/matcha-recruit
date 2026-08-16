import SwiftUI

struct ShareCampaignSheet: View {
    let campaign: PromoCampaign
    let onPostedToLocals: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var isPosting = false
    @State private var isPushing = false
    @State private var error: String?
    @State private var confirmPush = false

    private var canPushNearby: Bool {
        campaign.campaign_type == "location" && campaign.push_sent_at == nil && campaign.status == "active"
    }

    private var canPostToLocals: Bool {
        campaign.campaign_type != "location"
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text(campaign.title).font(.interHeadline)
                    Text(campaign.reward_text).font(.interSubheadline).foregroundStyle(.secondary)
                }

                Section("Share") {
                    if canPostToLocals {
                        Button {
                            Task { await postToLocals() }
                        } label: {
                            Label("Post to Locals", systemImage: "person.3.fill")
                        }
                        .disabled(isPosting || isPushing)
                    } else {
                        Text("Location campaigns are sent only to nearby followers.")
                            .font(.interFootnote)
                            .foregroundStyle(.secondary)
                    }

                    if canPushNearby {
                        Button {
                            confirmPush = true
                        } label: {
                            Label("Push to nearby", systemImage: "location.fill")
                        }
                        .disabled(isPosting || isPushing)
                    }
                }

                if let error {
                    Section { Text(error).foregroundStyle(.red) }
                }
            }
            .overlay {
                if isPosting || isPushing { ProgressView() }
            }
            .navigationTitle("Share campaign")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium])
        .alert("Push this offer?", isPresented: $confirmPush) {
            Button("Cancel", role: .cancel) {}
            Button("Push") { Task { await pushNearby() } }
        } message: {
            Text("This sends once to followers within the configured radius. It cannot be undone.")
        }
    }

    private func postToLocals() async {
        isPosting = true
        error = nil
        do {
            _ = try await BoardManageService.shared.createPost(
                brandId: nil,
                BoardPostCreate(
                    kind: "promo", title: campaign.title, body: campaign.description ?? campaign.reward_text,
                    listing_id: nil, campaign_id: campaign.id, event_starts_at: nil, event_ends_at: nil
                )
            )
            onPostedToLocals()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
        isPosting = false
    }

    private func pushNearby() async {
        isPushing = true
        error = nil
        do {
            _ = try await PromoService.shared.pushCampaign(id: campaign.id)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
        isPushing = false
    }
}
