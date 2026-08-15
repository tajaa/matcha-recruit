import SwiftUI

/// The consumer-facing Comms tab. A consumer always sees their own questions;
/// team members additionally see one entry per business inbox they have been
/// granted access to. We deliberately never expose a business's inbox to an
/// unrelated consumer.
struct CommsHubView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        List {
            Section("Your conversations") {
                NavigationLink {
                    MessagesListView(scope: .consumer)
                } label: {
                    Label("Messages with businesses", systemImage: "message")
                }
            }
            .listRowBackground(TU.inkRaised)

            if !appState.inboxBrands.isEmpty {
                Section("Business inboxes") {
                    ForEach(appState.inboxBrands) { brand in
                        NavigationLink {
                            MessagesListView(scope: .business(brandID: brand.brand_id))
                        } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(brand.name)
                                Text(brand.role.capitalized)
                                    .font(.interCaption)
                                    .foregroundStyle(TU.textDim)
                            }
                        }
                    }
                }
                .listRowBackground(TU.inkRaised)
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Comms")
    }
}
