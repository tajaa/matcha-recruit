import SwiftUI

struct WorkbookPreview: View {
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
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Cover image from workbook presentation
                if let urlStr = presentationCoverUrl, let url = URL(string: urlStr) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                                .frame(maxHeight: 160)
                                .clipped()
                                .cornerRadius(8)
                        default:
                            EmptyView()
                        }
                    }
                }

                Text(workbookTitle)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.white)

                if sections.isEmpty && !state.isEmpty {
                    Text("Workbook content is being generated...")
                        .foregroundColor(.secondary)
                        .font(.system(size: 13))
                } else if sections.isEmpty {
                    EmptyPreviewView(message: "Workbook in progress...", icon: "book")
                } else {
                    ForEach(sections) { section in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(section.title)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.white)
                            Text(section.body)
                                .font(.system(size: 13))
                                .foregroundColor(.white.opacity(0.8))
                                .lineSpacing(4)
                        }
                        .padding(12)
                        .background(Color.zinc800)
                        .cornerRadius(8)
                    }
                }
            }
            .padding(20)
        }
    }
}
