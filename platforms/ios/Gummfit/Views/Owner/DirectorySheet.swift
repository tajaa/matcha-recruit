import SwiftUI

/// v1 Discover-listing sheet: read + `listed` toggle only. Category/tag/blurb
/// editing (server already supports it via the same PATCH endpoint) is a
/// later polish pass — see DirectoryViewModel's doc comment.
struct DirectorySheet: View {
    let siteId: String

    @Environment(\.dismiss) private var dismiss
    @State private var vm = DirectoryViewModel()

    var body: some View {
        NavigationStack {
            List {
                if let listing = vm.listing {
                    Section {
                        Toggle("List on Discover", isOn: Binding(
                            get: { listing.listed },
                            set: { _ in Task { await vm.toggleListed(siteId: siteId) } }
                        ))
                        .disabled(vm.isSaving)
                    }
                    if let blurb = listing.blurb, !blurb.isEmpty {
                        Section("Blurb") {
                            Text(blurb)
                        }
                    }
                    if !listing.tags.isEmpty {
                        Section("Tags") {
                            Text(listing.tags.joined(separator: ", "))
                                .font(.footnote)
                                .foregroundStyle(GummfitTheme.textDim)
                        }
                    }
                    if listing.blocked {
                        Section {
                            Label("This listing was blocked by Gummfit.", systemImage: "exclamationmark.triangle")
                                .foregroundStyle(GummfitTheme.danger)
                        }
                    } else if listing.listed && !listing.visible {
                        Section {
                            Label("Listing incomplete — finish your profile on web to appear in Discover.", systemImage: "info.circle")
                                .foregroundStyle(GummfitTheme.textDim)
                        }
                    }
                } else if vm.isLoading {
                    ProgressView().frame(maxWidth: .infinity)
                }
                ErrorBanner(message: vm.error)
            }
            .navigationTitle("Discover listing")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .task { await vm.load(siteId: siteId) }
        }
    }
}
