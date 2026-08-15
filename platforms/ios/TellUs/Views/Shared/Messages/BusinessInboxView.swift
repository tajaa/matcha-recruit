import SwiftUI

struct BusinessInboxView: View {
    let brands: [InboxBrand]

    var body: some View {
        Group {
            if brands.count == 1, let brand = brands.first {
                MessagesListView(scope: .business(brandID: brand.brand_id))
            } else {
                List(brands) { brand in
                    NavigationLink {
                        MessagesListView(scope: .business(brandID: brand.brand_id))
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(brand.name)
                            Text(brand.role.capitalized)
                                .font(.interCaption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle(brands.count == 1 ? "Business inbox" : "Choose business")
    }
}
