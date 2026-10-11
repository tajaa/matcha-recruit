import SwiftUI

struct WorkbookPreview: View {
    @Environment(AppState.self) private var appState
    let state: [String: AnyCodable]

    struct WorkbookSection: Identifiable {
        let id = UUID()
        let title: String
        let body: String
    }

    var sections: [WorkbookSection] {
        guard let raw = state["sections"]?.value as? [AnyCodable] else { return [] }
        return raw.compactMap { item -> WorkbookSection? in
            guard let dict = item.value as? [String: AnyCodable] else { return nil }
            let title = (dict["title"]?.value as? String) ?? ""
            let body = (dict["body"]?.value as? String) ?? (dict["content"]?.value as? String) ?? ""
            return WorkbookSection(title: title, body: body)
        }
    }

    var workbookTitle: String { (state["workbook_title"]?.value as? String) ?? "Workbook" }

    // Workbook presentation cover image
    var presentationCoverUrl: String? {
        guard let pres = state["presentation"]?.value as? [String: AnyCodable] else { return nil }
        return pres["cover_image_url"]?.value as? String
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Cover image from workbook presentation
            if let urlStr = presentationCoverUrl, let url = URL(string: urlStr) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(maxHeight: 180)
                            .clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                    default:
                        EmptyView()
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("WORKBOOK")
                    .font(.espresso(size: 10, weight: .semibold))
                    .tracking(1.2)
                    .foregroundColor(AssetKind(.workbook).tint)
                Text(workbookTitle)
                    .font(.espresso(size: 22, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .fixedSize(horizontal: false, vertical: true)
                if !sections.isEmpty {
                    Text("\(sections.count) section\(sections.count == 1 ? "" : "s")")
                        .font(.espresso(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                }
                Rectangle().fill(appState.themeBorder).frame(height: 0.5).padding(.top, 4)
            }

            if sections.isEmpty && !state.isEmpty {
                Text("Workbook content is being generated...")
                    .foregroundColor(appState.themeTextSecondary)
                    .font(.espresso(size: 13))
            } else if sections.isEmpty {
                EmptyPreviewView(message: "Workbook in progress...", icon: "book")
            } else {
                ForEach(Array(sections.enumerated()), id: \.element.id) { index, section in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(String(format: "%02d", index + 1))
                                .font(.espresso(size: 11, weight: .bold))
                                .foregroundColor(AssetKind(.workbook).tint)
                            Text(section.title)
                                .font(.espresso(size: 15, weight: .semibold))
                                .foregroundColor(appState.themeText)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if !section.body.isEmpty {
                            JournalContentView(
                                content: section.body,
                                fontFamily: "system",
                                fontSize: 13.5,
                                lineSpacing: 4,
                                baseColor: appState.themeText.opacity(0.88)
                            )
                            .textSelection(.enabled)
                        }
                    }
                    .padding(.bottom, 6)
                }
            }
        }
    }
}
