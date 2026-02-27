import SwiftUI
import PDFKit

struct PreviewPanelView: View {
    let taskType: String
    let currentState: [String: AnyCodable]
    let pdfData: Data?
    let isLoading: Bool

    var body: some View {
        ZStack {
            Color.zinc900.ignoresSafeArea()

            if isLoading {
                VStack(spacing: 12) {
                    ProgressView().tint(.secondary)
                    Text("Loading document...")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                }
            } else {
                switch taskType {
                case "offer_letter":
                    OfferLetterPreview(pdfData: pdfData)
                case "review":
                    ReviewPreview(state: currentState)
                case "workbook":
                    WorkbookPreview(state: currentState)
                default:
                    EmptyPreviewView()
                }
            }
        }
    }
}

// MARK: - Offer Letter Preview

struct OfferLetterPreview: View {
    let pdfData: Data?

    var body: some View {
        if let data = pdfData {
            PDFKitView(data: data)
        } else {
            EmptyPreviewView(message: "No document yet", icon: "doc.text")
        }
    }
}

struct PDFKitView: NSViewRepresentable {
    let data: Data

    func makeNSView(context: Context) -> PDFView {
        let pdfView = PDFView()
        pdfView.autoScales = true
        pdfView.displayMode = .singlePageContinuous
        pdfView.backgroundColor = NSColor(Color.zinc900)
        if let document = PDFDocument(data: data) {
            pdfView.document = document
        }
        return pdfView
    }

    func updateNSView(_ nsView: PDFView, context: Context) {
        if let document = PDFDocument(data: data) {
            nsView.document = document
        }
    }
}

// MARK: - Review Preview

struct ReviewPreview: View {
    let state: [String: AnyCodable]

    var title: String { (state["title"]?.value as? String) ?? "Performance Review" }
    var overallRating: Int {
        if let v = state["overall_rating"]?.value as? Int { return v }
        if let v = state["overall_rating"]?.value as? Double { return Int(v) }
        return 0
    }
    var strengths: [String] { (state["strengths"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? [] }
    var growthAreas: [String] { (state["growth_areas"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? [] }
    var nextSteps: [String] { (state["next_steps"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? [] }
    var summary: String { (state["summary"]?.value as? String) ?? "" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    if overallRating > 0 {
                        HStack(spacing: 4) {
                            ForEach(1...5, id: \.self) { star in
                                Image(systemName: star <= overallRating ? "star.fill" : "star")
                                    .font(.system(size: 14))
                                    .foregroundColor(star <= overallRating ? .yellow : .secondary)
                            }
                            Text("(\(overallRating)/5)")
                                .font(.system(size: 13))
                                .foregroundColor(.secondary)
                        }
                    }
                }

                if !summary.isEmpty {
                    Text(summary)
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                        .lineSpacing(4)
                }

                if !strengths.isEmpty {
                    ReviewSection(title: "Strengths", items: strengths, icon: "checkmark.circle.fill", color: .green)
                }

                if !growthAreas.isEmpty {
                    ReviewSection(title: "Growth Areas", items: growthAreas, icon: "arrow.up.circle.fill", color: .blue)
                }

                if !nextSteps.isEmpty {
                    ReviewSection(title: "Next Steps", items: nextSteps, icon: "arrow.right.circle.fill", color: .orange, numbered: true)
                }

                if state.isEmpty {
                    EmptyPreviewView(message: "Review in progress...", icon: "star")
                }
            }
            .padding(20)
        }
    }
}

struct ReviewSection: View {
    let title: String
    let items: [String]
    let icon: String
    let color: Color
    var numbered: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white)

            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: 8) {
                        if numbered {
                            Text("\(index + 1).")
                                .font(.system(size: 12))
                                .foregroundColor(color)
                                .frame(width: 18, alignment: .trailing)
                        } else {
                            Image(systemName: icon)
                                .font(.system(size: 12))
                                .foregroundColor(color)
                                .frame(width: 18)
                        }
                        Text(item)
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.85))
                            .lineSpacing(3)
                    }
                }
            }
        }
        .padding(12)
        .background(Color.zinc800)
        .cornerRadius(8)
    }
}

// MARK: - Workbook Preview

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

    var workbookTitle: String { (state["title"]?.value as? String) ?? "Workbook" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
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

// MARK: - Empty Preview

struct EmptyPreviewView: View {
    var message = "No preview available"
    var icon = "doc"

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 40))
                .foregroundColor(.secondary)
            Text(message)
                .font(.system(size: 13))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
