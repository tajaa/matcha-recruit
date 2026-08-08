import SwiftUI

/// Catalog tab root — products list, matching HomeView's top-level NavigationStack shape.
struct CatalogRootView: View {
    let site: CappeSite

    var body: some View {
        NavigationStack {
            ProductListView(site: site)
        }
    }
}
