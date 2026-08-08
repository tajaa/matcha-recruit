import SwiftUI

struct ModerateTabView: View {
    @Environment(AppState.self) private var appState
    @State private var selectedBrand: ModeratedBrand?

    var body: some View {
        Group {
            if appState.moderatedBrands.count == 1, let only = appState.moderatedBrands.first {
                BoardManageView(brandId: only.brand_id, slug: only.slug)
                    .id(only.brand_id)
                    .navigationTitle(only.name)
            } else {
                VStack {
                    Picker("Brand", selection: $selectedBrand) {
                        ForEach(appState.moderatedBrands) { brand in
                            Text(brand.name).tag(Optional(brand))
                        }
                    }
                    .pickerStyle(.menu)
                    .padding()

                    if let brand = selectedBrand {
                        BoardManageView(brandId: brand.brand_id, slug: brand.slug)
                            .id(brand.brand_id)
                    } else {
                        EmptyState(icon: "checkmark.shield", title: "Pick a brand to moderate")
                    }
                }
                .onAppear { if selectedBrand == nil { selectedBrand = appState.moderatedBrands.first } }
            }
        }
        .navigationTitle("Moderate")
    }
}
