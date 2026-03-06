import SwiftUI
import PDFKit

struct PreviewPanelView: View {
    let currentState: [String: AnyCodable]
    let pdfData: Data?
    let isLoading: Bool
    let taskType: MWTaskType?
    var threadId: String?
    @Binding var selectedSlideIndex: Int?

    private var resolvedTaskType: MWTaskType {
        taskType ?? inferMWTaskType(from: currentState)
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
                switch resolvedTaskType {
                case .offerLetter:
                    OfferLetterPreview(pdfData: pdfData)
                case .review:
                    ReviewPreview(state: currentState)
                case .workbook:
                    WorkbookPreview(state: currentState)
                case .presentation:
                    PresentationPreview(state: currentState, threadId: threadId, selectedSlideIndex: $selectedSlideIndex)
                case .onboarding:
                    OnboardingPreview(state: currentState)
                case .handbook:
                    HandbookPreview(state: currentState)
                case .chat:
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

// MARK: - Handbook Preview

struct HandbookPreview: View {
    let state: [String: AnyCodable]

    private var title: String { (state["handbook_title"]?.value as? String) ?? "Employee Handbook" }
    private var status: String { (state["handbook_status"]?.value as? String) ?? "collecting" }
    private var mode: String { (state["handbook_mode"]?.value as? String) ?? "" }
    private var industry: String { (state["handbook_industry"]?.value as? String) ?? "" }
    private var subIndustry: String { (state["handbook_sub_industry"]?.value as? String) ?? "" }
    private var legalName: String { (state["handbook_legal_name"]?.value as? String) ?? "" }
    private var dba: String { (state["handbook_dba"]?.value as? String) ?? "" }
    private var ceo: String { (state["handbook_ceo"]?.value as? String) ?? "" }
    private var headcount: Int? {
        if let v = state["handbook_headcount"]?.value as? Int { return v }
        if let v = state["handbook_headcount"]?.value as? Double { return Int(v) }
        return nil
    }
    private var errorMessage: String { (state["handbook_error"]?.value as? String) ?? "" }
    private var strengthScore: Int? {
        if let v = state["handbook_strength_score"]?.value as? Int { return v }
        if let v = state["handbook_strength_score"]?.value as? Double { return Int(v) }
        return nil
    }
    private var strengthLabel: String { (state["handbook_strength_label"]?.value as? String) ?? "" }

    private var states: [String] {
        (state["handbook_states"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? []
    }

    private var profileFlags: [(String, Bool)] {
        guard let raw = state["handbook_profile"]?.value as? [String: AnyCodable] else { return [] }
        let labels: [(String, String)] = [
            ("remote_workers", "Remote Workers"),
            ("minors", "Minors"),
            ("tipped_employees", "Tipped Employees"),
            ("tip_pooling", "Tip Pooling"),
            ("union_employees", "Union Employees"),
            ("federal_contracts", "Federal Contracts"),
            ("group_health_insurance", "Group Health Insurance"),
            ("background_checks", "Background Checks"),
            ("hourly_employees", "Hourly Employees"),
            ("salaried_employees", "Salaried Employees"),
            ("commissioned_employees", "Commissioned Employees"),
        ]
        return labels.compactMap { key, label in
            guard let val = raw[key]?.value as? Bool else { return nil }
            return (label, val)
        }
    }

    private var sections: [(key: String, title: String, content: String, type: String)] {
        guard let raw = state["handbook_sections"]?.value as? [AnyCodable] else { return [] }
        return raw.compactMap { item in
            guard let dict = item.value as? [String: AnyCodable] else { return nil }
            let key = (dict["section_key"]?.value as? String) ?? ""
            let title = (dict["title"]?.value as? String) ?? ""
            let content = (dict["content"]?.value as? String) ?? ""
            let type = (dict["section_type"]?.value as? String) ?? ""
            return (key, title, content, type)
        }
    }

    private var requiredFieldsFilled: Int {
        var count = 0
        if !title.isEmpty && title != "Employee Handbook" { count += 1 }
        if !states.isEmpty { count += 1 }
        if !legalName.isEmpty { count += 1 }
        if !ceo.isEmpty { count += 1 }
        return count
    }

    private var statusColor: Color {
        switch status {
        case "created": return .green
        case "generating": return .orange
        case "error": return .red
        case "ready": return .blue
        default: return .secondary
        }
    }

    private var scoreColor: Color {
        guard let score = strengthScore else { return .secondary }
        if score >= 80 { return .green }
        if score >= 50 { return .orange }
        return .red
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    HStack(spacing: 8) {
                        if !mode.isEmpty {
                            Text(mode == "multi_state" ? "Multi-State" : "Single State")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.white.opacity(0.7))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.zinc800)
                                .cornerRadius(4)
                        }
                        Text(status.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(statusColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(statusColor.opacity(0.12))
                            .cornerRadius(4)
                    }
                }

                // Error banner
                if !errorMessage.isEmpty {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red)
                            .font(.system(size: 12))
                        Text(errorMessage)
                            .font(.system(size: 12))
                            .foregroundColor(.red)
                            .lineLimit(3)
                    }
                    .padding(10)
                    .background(Color.red.opacity(0.1))
                    .cornerRadius(8)
                }

                // States
                if !states.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "map.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        ForEach(states, id: \.self) { st in
                            Text(st)
                                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                                .foregroundColor(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.blue.opacity(0.2))
                                .cornerRadius(4)
                        }
                    }
                }

                // Industry
                if !industry.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "building.2.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Text(industry.capitalized)
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.85))
                        if !subIndustry.isEmpty {
                            Text("(\(subIndustry))")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                        }
                    }
                }

                // Company info
                if !legalName.isEmpty || !ceo.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        if !legalName.isEmpty {
                            HStack(spacing: 6) {
                                Text("Legal Name:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(legalName)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !dba.isEmpty {
                            HStack(spacing: 6) {
                                Text("DBA:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(dba)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !ceo.isEmpty {
                            HStack(spacing: 6) {
                                Text("CEO:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(ceo)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if let hc = headcount {
                            HStack(spacing: 6) {
                                Text("Headcount:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text("\(hc)")
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Profile flags
                if !profileFlags.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Company Profile")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white)

                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                            ForEach(profileFlags, id: \.0) { label, enabled in
                                HStack(spacing: 6) {
                                    Image(systemName: enabled ? "checkmark.circle.fill" : "xmark.circle")
                                        .font(.system(size: 11))
                                        .foregroundColor(enabled ? .green : .secondary.opacity(0.5))
                                    Text(label)
                                        .font(.system(size: 11))
                                        .foregroundColor(enabled ? .white.opacity(0.85) : .secondary.opacity(0.6))
                                    Spacer()
                                }
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Progress (before generation)
                if status != "created" && status != "error" {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Required Fields (\(requiredFieldsFilled)/4)")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)

                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.zinc800)
                                    .frame(height: 6)
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(requiredFieldsFilled == 4 ? Color.green : Color.matcha500)
                                    .frame(width: geo.size.width * CGFloat(requiredFieldsFilled) / 4.0, height: 6)
                            }
                        }
                        .frame(height: 6)
                    }
                }

                // Strength score (after creation)
                if let score = strengthScore {
                    HStack(spacing: 10) {
                        ZStack {
                            Circle()
                                .stroke(scoreColor.opacity(0.2), lineWidth: 4)
                                .frame(width: 44, height: 44)
                            Circle()
                                .trim(from: 0, to: CGFloat(score) / 100.0)
                                .stroke(scoreColor, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                                .frame(width: 44, height: 44)
                                .rotationEffect(.degrees(-90))
                            Text("\(score)")
                                .font(.system(size: 14, weight: .bold, design: .monospaced))
                                .foregroundColor(scoreColor)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Coverage Score")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                            Text(strengthLabel)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(scoreColor)
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Sections (after creation)
                if !sections.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("\(sections.count) Sections")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white)

                        ForEach(sections, id: \.key) { section in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(section.title)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundColor(.white)
                                if !section.content.isEmpty {
                                    Text(section.content)
                                        .font(.system(size: 12))
                                        .foregroundColor(.white.opacity(0.6))
                                        .lineLimit(3)
                                        .lineSpacing(2)
                                }
                            }
                            .padding(10)
                            .background(Color.zinc800)
                            .cornerRadius(6)
                        }
                    }
                }

                if state.isEmpty {
                    EmptyPreviewView(message: "Handbook in progress...", icon: "book.closed")
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
        let firstName: String
        let lastName: String
        let name: String
        let role: String
        let workEmail: String
        let personalEmail: String
        let workState: String
        let employmentType: String
        let startDate: String
        let status: String
        let error: String
        let employeeId: String
        let provisioningResults: [String: String]

        var initials: String {
            let parts = name.split(separator: " ")
            if parts.count >= 2 {
                return "\(parts[0].prefix(1))\(parts[1].prefix(1))".uppercased()
            }
            return String(name.prefix(2)).uppercased()
        }
    }

    // MARK: - Parsed data

    var employees: [EmployeeEntry] {
        guard let raw = state["employees"]?.value as? [AnyCodable] else { return [] }
        return raw.compactMap { item -> EmployeeEntry? in
            guard let dict = item.value as? [String: AnyCodable] else { return nil }
            let firstName = (dict["first_name"]?.value as? String) ?? ""
            let lastName = (dict["last_name"]?.value as? String) ?? ""
            let composedName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
            let displayName = composedName.isEmpty
                ? (dict["name"]?.value as? String) ?? (dict["full_name"]?.value as? String) ?? ""
                : composedName
            guard !displayName.isEmpty else { return nil }
            let role = (dict["role"]?.value as? String) ?? (dict["position"]?.value as? String) ?? ""
            let workEmail = (dict["work_email"]?.value as? String) ?? ""
            let personalEmail = (dict["personal_email"]?.value as? String) ?? ""
            let workState = (dict["work_state"]?.value as? String) ?? ""
            let employmentType = (dict["employment_type"]?.value as? String) ?? ""
            let startDate = (dict["start_date"]?.value as? String) ?? ""
            let status = (dict["status"]?.value as? String) ?? "pending"
            let error = (dict["error"]?.value as? String) ?? ""
            let employeeId = (dict["employee_id"]?.value as? String) ?? ""
            var provResults: [String: String] = [:]
            if let pr = dict["provisioning_results"]?.value as? [String: AnyCodable] {
                for (k, v) in pr {
                    provResults[k] = v.value as? String ?? ""
                }
            }
            return EmployeeEntry(
                firstName: firstName, lastName: lastName, name: displayName,
                role: role, workEmail: workEmail, personalEmail: personalEmail,
                workState: workState, employmentType: employmentType, startDate: startDate,
                status: status, error: error, employeeId: employeeId,
                provisioningResults: provResults
            )
        }
    }

    // MARK: - Batch-level properties

    private var batchStatus: String { (state["batch_status"]?.value as? String) ?? "" }
    private var companyName: String { (state["company_name"]?.value as? String) ?? "" }
    private var defaultStartDate: String { (state["default_start_date"]?.value as? String) ?? "" }
    private var defaultEmploymentType: String { (state["default_employment_type"]?.value as? String) ?? "" }
    private var defaultWorkState: String { (state["default_work_state"]?.value as? String) ?? "" }

    // MARK: - Summary stats

    private var createdCount: Int {
        employees.filter {
            let status = resolvedEmployeeStatus(for: $0)
            return status == "created" || status == "done"
        }.count
    }

    private var errorCount: Int {
        employees.filter { resolvedEmployeeStatus(for: $0) == "error" }.count
    }

    private var batchStatusColor: Color {
        switch batchStatus {
        case "ready": return .orange
        case "processing": return .blue
        case "complete": return .green
        default: return .secondary
        }
    }

    private func hasProvisioningFailure(_ employee: EmployeeEntry) -> Bool {
        employee.provisioningResults.values.contains { result in
            let normalized = result.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return normalized.contains("error")
                || normalized.contains("fail")
                || normalized.contains("needs_action")
        }
    }

    private func resolvedEmployeeStatus(for employee: EmployeeEntry) -> String {
        let status = employee.status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if status == "error" || hasProvisioningFailure(employee) {
            return "error"
        }
        return status.isEmpty ? "pending" : status
    }

    private func employeeStatusColor(_ status: String) -> Color {
        switch status {
        case "created", "done": return .green
        case "provisioning": return .blue
        case "error": return .red
        default: return .secondary
        }
    }

    // MARK: - Body

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 6) {
                    Text("Onboarding Plan")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    HStack(spacing: 8) {
                        if !batchStatus.isEmpty {
                            Text(batchStatus.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(batchStatusColor)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(batchStatusColor.opacity(0.12))
                                .cornerRadius(4)
                        }
                        if !companyName.isEmpty {
                            Text(companyName)
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                        }
                    }

                    if !employees.isEmpty {
                        HStack(spacing: 6) {
                            Text("\(employees.count) employee\(employees.count == 1 ? "" : "s")")
                                .foregroundColor(.white.opacity(0.7))
                            if createdCount > 0 {
                                Text("·")
                                    .foregroundColor(.secondary)
                                Text("\(createdCount) created")
                                    .foregroundColor(.green)
                            }
                            if errorCount > 0 {
                                Text("·")
                                    .foregroundColor(.secondary)
                                Text("\(errorCount) error\(errorCount == 1 ? "" : "s")")
                                    .foregroundColor(.red)
                            }
                        }
                        .font(.system(size: 12, weight: .medium))
                    }
                }

                // Defaults card
                if !defaultStartDate.isEmpty || !defaultEmploymentType.isEmpty || !defaultWorkState.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        if !defaultStartDate.isEmpty {
                            HStack(spacing: 6) {
                                Text("Start Date:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(defaultStartDate)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !defaultEmploymentType.isEmpty {
                            HStack(spacing: 6) {
                                Text("Employment:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(defaultEmploymentType.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !defaultWorkState.isEmpty {
                            HStack(spacing: 6) {
                                Text("Work State:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(defaultWorkState)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Employee cards
                if employees.isEmpty {
                    if !batchStatus.isEmpty {
                        EmptyPreviewView(message: "Collecting employee details...", icon: "person.badge.plus")
                    } else {
                        EmptyPreviewView(message: "Describe the employees you'd like to onboard...", icon: "person.badge.plus")
                    }
                } else {
                    ForEach(employees) { employee in
                        let resolvedStatus = resolvedEmployeeStatus(for: employee)
                        VStack(alignment: .leading, spacing: 8) {
                            // Top row: avatar + name/role + status badge
                            HStack(spacing: 10) {
                                ZStack {
                                    Circle()
                                        .fill(employeeStatusColor(resolvedStatus).opacity(0.15))
                                        .frame(width: 36, height: 36)
                                    Text(employee.initials)
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundColor(employeeStatusColor(resolvedStatus))
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
                                }
                                Spacer()
                                Text(resolvedStatus.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(employeeStatusColor(resolvedStatus))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(employeeStatusColor(resolvedStatus).opacity(0.12))
                                    .cornerRadius(4)
                            }

                            // Detail rows (indented past avatar)
                            VStack(alignment: .leading, spacing: 4) {
                                if !employee.workEmail.isEmpty {
                                    HStack(spacing: 6) {
                                        Image(systemName: "envelope.fill")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                        Text(employee.workEmail)
                                            .font(.system(size: 11, design: .monospaced))
                                            .foregroundColor(.white.opacity(0.75))
                                    }
                                }
                                if !employee.personalEmail.isEmpty {
                                    HStack(spacing: 6) {
                                        Image(systemName: "envelope")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                        Text(employee.personalEmail)
                                            .font(.system(size: 11))
                                            .foregroundColor(.white.opacity(0.6))
                                    }
                                }
                                if !employee.employmentType.isEmpty || !employee.workState.isEmpty {
                                    HStack(spacing: 6) {
                                        if !employee.employmentType.isEmpty {
                                            Text(employee.employmentType.replacingOccurrences(of: "_", with: " ").capitalized)
                                                .font(.system(size: 10, weight: .medium))
                                                .foregroundColor(.purple)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(Color.purple.opacity(0.12))
                                                .cornerRadius(3)
                                        }
                                        if !employee.workState.isEmpty {
                                            Text(employee.workState)
                                                .font(.system(size: 10, weight: .medium))
                                                .foregroundColor(.blue)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(Color.blue.opacity(0.12))
                                                .cornerRadius(3)
                                        }
                                    }
                                }
                                if !employee.startDate.isEmpty {
                                    HStack(spacing: 6) {
                                        Image(systemName: "calendar")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                        Text("Starts \(employee.startDate)")
                                            .font(.system(size: 11))
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding(.leading, 46)

                            // Error banner
                            if resolvedStatus == "error" && !employee.error.isEmpty {
                                HStack(spacing: 6) {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .font(.system(size: 11))
                                        .foregroundColor(.red)
                                    Text(employee.error)
                                        .font(.system(size: 11))
                                        .foregroundColor(.red)
                                        .lineLimit(3)
                                }
                                .padding(8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.red.opacity(0.1))
                                .cornerRadius(6)
                            }

                            // Provisioning results
                            if !employee.provisioningResults.isEmpty {
                                HStack(spacing: 12) {
                                    ForEach(Array(employee.provisioningResults.sorted(by: { $0.key < $1.key })), id: \.key) { service, result in
                                        HStack(spacing: 4) {
                                            Image(systemName: provisioningIcon(for: service))
                                                .font(.system(size: 10))
                                                .foregroundColor(provisioningColor(for: result))
                                            Text("\(provisioningLabel(for: service)): \(result)")
                                                .font(.system(size: 10))
                                                .foregroundColor(provisioningColor(for: result))
                                        }
                                    }
                                }
                                .padding(.leading, 46)
                            }
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

    // MARK: - Provisioning helpers

    private func provisioningIcon(for service: String) -> String {
        switch service {
        case "google_workspace": return "envelope.badge.person.crop"
        case "slack": return "number"
        default: return "gearshape"
        }
    }

    private func provisioningLabel(for service: String) -> String {
        switch service {
        case "google_workspace": return "Google"
        case "slack": return "Slack"
        default: return service.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func provisioningColor(for result: String) -> Color {
        if result.contains("error") || result.contains("fail") { return .red }
        return .green
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
