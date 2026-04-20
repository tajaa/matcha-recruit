import SwiftUI

struct MarkdownPreviewView: View {
    let sections: [MWProjectSection]
    let title: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(title)
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(.white)
                    .padding(.bottom, 4)

                ForEach(sections) { section in
                    VStack(alignment: .leading, spacing: 8) {
                        if !section.title.isEmpty {
                            Text(section.title)
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.white)
                        }
                        if let content = section.content, !content.isEmpty {
                            if let attributed = try? AttributedString(markdown: content,
                                options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
                                Text(attributed)
                                    .font(.system(size: 13))
                                    .foregroundColor(Color(white: 0.85))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            } else {
                                Text(content)
                                    .font(.system(size: 13))
                                    .foregroundColor(Color(white: 0.85))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        } else {
                            Text("No content yet")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                                .italic()
                        }
                    }
                    if section.id != sections.last?.id {
                        Divider().opacity(0.2)
                    }
                }
            }
            .padding(24)
            .frame(maxWidth: 680, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(Color(white: 0.08))
    }
}
