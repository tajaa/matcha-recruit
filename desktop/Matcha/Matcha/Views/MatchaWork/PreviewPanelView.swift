import SwiftUI
import PDFKit

struct PreviewPanelView: View {
    let currentState: [String: AnyCodable]
    let pdfData: Data?
    let isLoading: Bool
    var threadId: String?
    @Binding var selectedSlideIndex: Int?

    private var inferredSkill: String {
        if currentState["candidate_name"] != nil || currentState["position_title"] != nil ||
           currentState["salary"] != nil {
            return "offer_letter"
        }
        if currentState["overall_rating"] != nil || currentState["review_title"] != nil { return "review" }
        if currentState["sections"] != nil || currentState["workbook_title"] != nil { return "workbook" }
        if currentState["presentation_title"] != nil || currentState["slides"] != nil { return "presentation" }
        if currentState["employees"] != nil { return "onboarding" }
        return "chat"
    }

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
                switch inferredSkill {
                case "offer_letter":
                    OfferLetterPreview(pdfData: pdfData)
                case "review":
                    ReviewPreview(state: currentState)
                case "workbook":
                    WorkbookPreview(state: currentState)
                case "presentation":
                    PresentationPreview(state: currentState, threadId: threadId, selectedSlideIndex: $selectedSlideIndex)
                case "onboarding":
                    OnboardingPreview(state: currentState)
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

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> PDFView {
        let pdfView = PDFView()
        pdfView.autoScales = true
        pdfView.displayMode = .singlePageContinuous
        pdfView.backgroundColor = NSColor(Color.zinc900)
        if let document = PDFDocument(data: data) {
            pdfView.document = document
            context.coordinator.loadedDataID = dataIdentity(data)
        }
        return pdfView
    }

    func updateNSView(_ nsView: PDFView, context: Context) {
        let newID = dataIdentity(data)
        guard newID != context.coordinator.loadedDataID else { return }
        if let document = PDFDocument(data: data) {
            nsView.document = document
            context.coordinator.loadedDataID = newID
        }
    }

    private func dataIdentity(_ data: Data) -> String {
        "\(data.count)-\(data.prefix(64).hashValue)"
    }

    class Coordinator {
        var loadedDataID: String?
    }
}

// MARK: - Review Preview

struct ReviewPreview: View {
    let state: [String: AnyCodable]

    var title: String { (state["review_title"]?.value as? String) ?? "Performance Review" }
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

// MARK: - Presentation Preview

struct PresentationPreview: View {
    let state: [String: AnyCodable]
    var threadId: String?
    @Binding var selectedSlideIndex: Int?
    @State private var isLoadingPdf = false
    @State private var hoveredSlideIndex: Int?

    struct SlideEntry: Identifiable {
        let id = UUID()
        let index: Int
        let title: String
        let bullets: [String]
        let speakerNotes: String?
    }

    var presentationTitle: String { (state["presentation_title"]?.value as? String) ?? "Presentation" }
    var subtitle: String { (state["subtitle"]?.value as? String) ?? "" }
    var coverImageUrl: String? { state["cover_image_url"]?.value as? String }

    var slides: [SlideEntry] {
        guard let raw = state["slides"]?.value as? [AnyCodable] else { return [] }
        return raw.enumerated().compactMap { index, item -> SlideEntry? in
            guard let dict = item.value as? [String: AnyCodable] else { return nil }
            let title = (dict["title"]?.value as? String) ?? ""
            let bullets = (dict["bullets"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? []
            let speakerNotes = dict["speaker_notes"]?.value as? String
            return SlideEntry(index: index + 1, title: title, bullets: bullets, speakerNotes: speakerNotes)
        }
    }

    private func openPdf() {
        guard let id = threadId else { return }
        isLoadingPdf = true
        Task {
            defer { Task { @MainActor in isLoadingPdf = false } }
            do {
                let url = try await MatchaWorkService.shared.getPresentationPdfUrl(threadId: id)
                if let nsUrl = URL(string: url) {
                    await MainActor.run { NSWorkspace.shared.open(nsUrl) }
                }
            } catch {
                // Silently fail — user can retry
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Cover image
                if let urlStr = coverImageUrl, let url = URL(string: urlStr) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                                .frame(maxHeight: 180)
                                .clipped()
                                .cornerRadius(8)
                        default:
                            EmptyView()
                        }
                    }
                }

                // Title + PDF button row
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(presentationTitle)
                            .font(.system(size: 18, weight: .bold))
                            .foregroundColor(.white)
                        if !subtitle.isEmpty {
                            Text(subtitle)
                                .font(.system(size: 13))
                                .foregroundColor(.secondary)
                        }
                    }
                    Spacer()
                    if threadId != nil && !slides.isEmpty {
                        Button(action: openPdf) {
                            HStack(spacing: 4) {
                                if isLoadingPdf {
                                    ProgressView().controlSize(.small)
                                } else {
                                    Image(systemName: "doc.richtext")
                                        .font(.system(size: 12))
                                }
                                Text("View PDF")
                                    .font(.system(size: 12, weight: .medium))
                            }
                            .foregroundColor(.matcha500)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(Color.matcha500.opacity(0.12))
                            .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .disabled(isLoadingPdf)
                    }
                }

                if slides.isEmpty {
                    EmptyPreviewView(message: "Slides in progress...", icon: "rectangle.on.rectangle")
                } else {
                    // Slide count
                    Text("\(slides.count) slides")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    ForEach(slides) { slide in
                        let zeroBasedIndex = slide.index - 1
                        let isSelected = selectedSlideIndex == zeroBasedIndex
                        let isHovered = hoveredSlideIndex == zeroBasedIndex
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                Text("\(slide.index)")
                                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                                    .foregroundColor(isSelected ? Color.matcha500 : .white.opacity(0.5))
                                    .frame(width: 20, alignment: .center)
                                Text(slide.title)
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundColor(.white)
                                Spacer()
                                if isSelected {
                                    Text("Editing")
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundColor(Color.matcha500)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.matcha500.opacity(0.15))
                                        .cornerRadius(4)
                                }
                            }
                            if !slide.bullets.isEmpty {
                                VStack(alignment: .leading, spacing: 3) {
                                    ForEach(slide.bullets, id: \.self) { bullet in
                                        HStack(alignment: .top, spacing: 6) {
                                            Text("•")
                                                .font(.system(size: 12))
                                                .foregroundColor(.secondary)
                                            Text(bullet)
                                                .font(.system(size: 12))
                                                .foregroundColor(.white.opacity(0.75))
                                                .lineSpacing(2)
                                        }
                                    }
                                }
                                .padding(.leading, 26)
                            }
                            if let notes = slide.speakerNotes, !notes.isEmpty {
                                Text(notes)
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)
                                    .lineSpacing(2)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 5)
                                    .background(Color.white.opacity(0.04))
                                    .cornerRadius(4)
                            }
                        }
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(isSelected ? Color.matcha500.opacity(0.1) : Color.zinc800)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(isSelected ? Color.matcha500 : (isHovered ? Color.white.opacity(0.1) : Color.clear), lineWidth: 2)
                                )
                        )
                        .onTapGesture {
                            if selectedSlideIndex == zeroBasedIndex {
                                selectedSlideIndex = nil
                            } else {
                                selectedSlideIndex = zeroBasedIndex
                            }
                        }
                        .onHover { hovering in
                            hoveredSlideIndex = hovering ? zeroBasedIndex : nil
                            if hovering {
                                NSCursor.pointingHand.push()
                            } else {
                                NSCursor.pop()
                            }
                        }
                    }
                }
            }
            .padding(20)
        }
    }
}

// MARK: - Onboarding Preview

struct OnboardingPreview: View {
    let state: [String: AnyCodable]

    struct EmployeeEntry: Identifiable {
        let id = UUID()
        let name: String
        let role: String
        let startDate: String
    }

    var employees: [EmployeeEntry] {
        guard let raw = state["employees"]?.value as? [AnyCodable] else { return [] }
        return raw.compactMap { item -> EmployeeEntry? in
            guard let dict = item.value as? [String: AnyCodable] else { return nil }
            let name = (dict["name"]?.value as? String) ?? (dict["full_name"]?.value as? String) ?? ""
            let role = (dict["role"]?.value as? String) ?? (dict["position"]?.value as? String) ?? ""
            let startDate = (dict["start_date"]?.value as? String) ?? ""
            guard !name.isEmpty else { return nil }
            return EmployeeEntry(name: name, role: role, startDate: startDate)
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Onboarding Plan")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.white)

                if employees.isEmpty {
                    EmptyPreviewView(message: "Onboarding in progress...", icon: "person.badge.plus")
                } else {
                    ForEach(employees) { employee in
                        HStack(spacing: 12) {
                            ZStack {
                                Circle()
                                    .fill(Color.zinc800)
                                    .frame(width: 36, height: 36)
                                Text(String(employee.name.prefix(1)).uppercased())
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundColor(.white)
                            }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(employee.name)
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(.white)
                                if !employee.role.isEmpty {
                                    Text(employee.role)
                                        .font(.system(size: 12))
                                        .foregroundColor(.secondary)
                                }
                                if !employee.startDate.isEmpty {
                                    Text("Starts \(employee.startDate)")
                                        .font(.system(size: 11))
                                        .foregroundColor(.secondary)
                                }
                            }
                            Spacer()
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
