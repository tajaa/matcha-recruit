import SwiftUI

// MARK: - Presentation Theme

enum PresentationTheme: String, CaseIterable, Identifiable {
    case professional, minimal, bold

    var id: String { rawValue }
    var label: String { rawValue.capitalized }

    var backgroundColor: Color {
        switch self {
        case .professional: return Color(red: 0.1, green: 0.1, blue: 0.18)
        case .minimal: return .white
        case .bold: return Color(red: 0.1, green: 0.12, blue: 0.25)
        }
    }

    var accentColor: Color {
        switch self {
        case .professional: return .green
        case .minimal: return Color(white: 0.3)
        case .bold: return .orange
        }
    }

    var titleColor: Color {
        switch self {
        case .professional: return .white
        case .minimal: return .black
        case .bold: return .white
        }
    }

    var textColor: Color {
        switch self {
        case .professional: return .white.opacity(0.85)
        case .minimal: return Color(white: 0.25)
        case .bold: return .white.opacity(0.9)
        }
    }

    var cardBackground: Color {
        switch self {
        case .professional: return Color(white: 0.15)
        case .minimal: return Color(white: 0.96)
        case .bold: return Color(red: 0.12, green: 0.14, blue: 0.28)
        }
    }
}

struct PresentationPreview: View {
    let state: [String: AnyCodable]
    var threadId: String?
    @Binding var selectedSlideIndex: Int?
    @State private var isLoadingPdf = false
    @State private var hoveredSlideIndex: Int?
    @State private var theme: PresentationTheme = .professional
    @State private var showNotes = true

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
                    await MainActor.run { SafeURL.open(nsUrl) }
                }
            } catch {
                // Silently fail — user can retry
            }
        }
    }

    private func navigateSlide(by offset: Int) {
        guard !slides.isEmpty else { return }
        let current = selectedSlideIndex ?? -1
        let next = max(0, min(slides.count - 1, current + offset))
        selectedSlideIndex = next
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            HStack(spacing: 8) {
                // Theme picker
                Picker("Theme", selection: $theme) {
                    ForEach(PresentationTheme.allCases) { t in
                        Text(t.label).tag(t)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 240)

                Spacer()

                // Notes toggle
                Button {
                    showNotes.toggle()
                } label: {
                    Image(systemName: showNotes ? "text.bubble.fill" : "text.bubble")
                        .font(.system(size: 12))
                        .foregroundColor(showNotes ? .matcha500 : .secondary)
                }
                .buttonStyle(.plain)
                .help(showNotes ? "Hide speaker notes" : "Show speaker notes")

                // PDF button
                if threadId != nil && !slides.isEmpty {
                    Button(action: openPdf) {
                        HStack(spacing: 4) {
                            if isLoadingPdf {
                                ProgressView().controlSize(.small)
                            } else {
                                Image(systemName: "doc.richtext")
                                    .font(.system(size: 12))
                            }
                            Text("PDF")
                                .font(.system(size: 12, weight: .medium))
                        }
                        .foregroundColor(.matcha500)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.matcha500.opacity(0.12))
                        .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                    .disabled(isLoadingPdf)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color.zinc900)
            .overlay(
                Rectangle().fill(Color.white.opacity(0.08)).frame(height: 1),
                alignment: .bottom
            )

            Divider().opacity(0.3)

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

                    // Title
                    VStack(alignment: .leading, spacing: 4) {
                        Text(presentationTitle)
                            .font(.system(size: 18, weight: .bold))
                            .foregroundColor(theme.titleColor)
                        if !subtitle.isEmpty {
                            Text(subtitle)
                                .font(.system(size: 13))
                                .foregroundColor(theme.textColor.opacity(0.7))
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
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundColor(isSelected ? theme.accentColor : theme.textColor.opacity(0.5))
                                        .frame(width: 20, alignment: .center)
                                    Text(slide.title)
                                        .font(.system(size: 14, weight: .semibold))
                                        .foregroundColor(theme.titleColor)
                                    Spacer()
                                    if isSelected {
                                        Text("Editing")
                                            .font(.system(size: 10, weight: .medium))
                                            .foregroundColor(theme.accentColor)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(theme.accentColor.opacity(0.15))
                                            .cornerRadius(4)
                                    }
                                }
                                if !slide.bullets.isEmpty {
                                    VStack(alignment: .leading, spacing: 3) {
                                        ForEach(slide.bullets, id: \.self) { bullet in
                                            HStack(alignment: .top, spacing: 6) {
                                                Image(systemName: "arrowshape.right.fill")
                                                    .font(.system(size: 8))
                                                    .foregroundColor(theme.accentColor)
                                                    .padding(.top, 3)
                                                Text(bullet)
                                                    .font(.system(size: 12))
                                                    .foregroundColor(theme.textColor)
                                                    .lineSpacing(2)
                                            }
                                        }
                                    }
                                    .padding(.leading, 26)
                                }
                                if showNotes, let notes = slide.speakerNotes, !notes.isEmpty {
                                    Text(notes)
                                        .font(.system(size: 11))
                                        .foregroundColor(theme.textColor.opacity(0.5))
                                        .lineSpacing(2)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 5)
                                        .background(theme.textColor.opacity(0.04))
                                        .cornerRadius(4)
                                }
                            }
                            .padding(12)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(isSelected ? theme.accentColor.opacity(0.1) : theme.cardBackground)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 8)
                                            .stroke(isSelected ? theme.accentColor : (isHovered ? theme.textColor.opacity(0.1) : Color.clear), lineWidth: 2)
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
            .background(theme.backgroundColor)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onKeyPress(.downArrow) { navigateSlide(by: 1); return .handled }
        .onKeyPress(.upArrow) { navigateSlide(by: -1); return .handled }
        .onKeyPress(.rightArrow) { navigateSlide(by: 1); return .handled }
        .onKeyPress(.leftArrow) { navigateSlide(by: -1); return .handled }
    }
}
