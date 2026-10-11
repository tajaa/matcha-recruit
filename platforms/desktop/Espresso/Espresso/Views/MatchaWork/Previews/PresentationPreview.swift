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

/// The deck on a 16:9 stage with a filmstrip beneath it. The stage shows one
/// slide (or the cover); `selectedSlideIndex` is the slide locked for editing —
/// the next message is sent with it, and the chat shows the lock.
struct PresentationPreview: View {
    @Environment(AppState.self) private var appState
    let state: [String: AnyCodable]
    var threadId: String?
    @Binding var selectedSlideIndex: Int?
    @State private var theme: PresentationTheme = .professional
    @State private var showNotes = true
    /// The slide on the stage, 0-based; nil is the cover.
    @State private var shown: Int?

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

    private var tint: Color { AssetKind(.presentation).tint }

    /// Step the stage through cover → slides; a lock follows the stage.
    private func navigateSlide(by offset: Int) {
        let count = slides.count
        guard count > 0 else { return }
        let current = shown ?? -1
        let next = max(-1, min(count - 1, current + offset))
        show(next < 0 ? nil : next)
    }

    private func show(_ index: Int?) {
        withAnimation(.easeOut(duration: 0.18)) { shown = index }
        if selectedSlideIndex != nil, let index { selectedSlideIndex = index }
    }

    private func toggleLock() {
        guard let index = shown else { return }
        selectedSlideIndex = selectedSlideIndex == index ? nil : index
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            ScrollView {
                VStack(spacing: 12) {
                    stage
                    stageBar
                    if !slides.isEmpty { filmstrip }
                    if showNotes, let index = shown, index < slides.count,
                       let notes = slides[index].speakerNotes, !notes.isEmpty {
                        notesCard(notes)
                    }
                }
                .frame(maxWidth: 900)
                .padding(.horizontal, 20)
                .padding(.vertical, 18)
                .frame(maxWidth: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear { shown = selectedSlideIndex }
        .onChange(of: selectedSlideIndex) { _, locked in
            if let locked { withAnimation(.easeOut(duration: 0.18)) { shown = locked } }
        }
        .onChange(of: slides.count) { _, count in
            if let index = shown, index >= count { shown = count > 0 ? count - 1 : nil }
        }
        .onKeyPress(.downArrow) { navigateSlide(by: 1); return .handled }
        .onKeyPress(.upArrow) { navigateSlide(by: -1); return .handled }
        .onKeyPress(.rightArrow) { navigateSlide(by: 1); return .handled }
        .onKeyPress(.leftArrow) { navigateSlide(by: -1); return .handled }
    }

    // MARK: Toolbar

    private var toolbar: some View {
        HStack(spacing: 10) {
            Picker("Theme", selection: $theme) {
                ForEach(PresentationTheme.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 230)
            Spacer()
            if !slides.isEmpty {
                Text("\(slides.count) slide\(slides.count == 1 ? "" : "s")")
                    .font(.espresso(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
            Button { showNotes.toggle() } label: {
                Image(systemName: showNotes ? "text.bubble.fill" : "text.bubble")
                    .font(.system(size: 12))
                    .foregroundColor(showNotes ? tint : appState.themeTextSecondary)
            }
            .buttonStyle(.plain)
            .help(showNotes ? "Hide speaker notes" : "Show speaker notes")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(appState.themeBg.opacity(0.6))
        .overlay(Rectangle().fill(appState.themeBorder).frame(height: 0.5), alignment: .bottom)
    }

    // MARK: Stage

    private var stage: some View {
        let locked = shown != nil && selectedSlideIndex == shown
        return slideCanvas(shown)
        .aspectRatio(16.0 / 9.0, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(locked ? tint : appState.themeBorder, lineWidth: locked ? 2.5 : 0.5)
        )
        .shadow(color: .black.opacity(appState.isLightFamily ? 0.14 : 0.45), radius: 22, y: 10)
        .contentShape(Rectangle())
        .onTapGesture { toggleLock() }
        .help(shown == nil ? "" : (locked ? "Click to stop editing this slide" : "Click to edit this slide in the chat"))
    }

    @ViewBuilder
    private func slideCanvas(_ index: Int?) -> some View {
        if let index, index < slides.count {
            SlideCanvas(theme: theme, deckTitle: presentationTitle, slide: slides[index], total: slides.count)
        } else if slides.isEmpty && state["presentation_title"] == nil {
            ZStack {
                theme.backgroundColor
                VStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text("Slides in progress…")
                        .font(.espresso(size: 12))
                        .foregroundColor(theme.textColor.opacity(0.7))
                }
            }
        } else {
            SlideCoverCanvas(theme: theme, title: presentationTitle, subtitle: subtitle,
                             imageURL: coverImageUrl, slideCount: slides.count)
        }
    }

    /// Under the stage: step through the deck, where you are, and the lock.
    private var stageBar: some View {
        let locked = shown != nil && selectedSlideIndex == shown
        return HStack(spacing: 8) {
            stageButton("chevron.left", help: "Previous slide") { navigateSlide(by: -1) }
                .disabled(shown == nil)
            stageButton("chevron.right", help: "Next slide") { navigateSlide(by: 1) }
                .disabled(slides.isEmpty || shown == slides.count - 1)
            Text(shown.map { "Slide \($0 + 1) of \(slides.count)" } ?? "Cover")
                .font(.espresso(size: 11.5, weight: .medium))
                .foregroundColor(appState.themeTextSecondary)
                .padding(.leading, 2)
            Spacer()
            if let index = shown {
                Button(action: toggleLock) {
                    HStack(spacing: 5) {
                        Image(systemName: locked ? "pencil.circle.fill" : "pencil")
                            .font(.system(size: 10.5, weight: .semibold))
                        Text(locked ? "Editing slide \(index + 1)" : "Edit slide \(index + 1)")
                            .font(.espresso(size: 11.5, weight: .semibold))
                    }
                    .foregroundColor(locked ? .white : appState.themeText)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 5)
                    .background(Capsule().fill(locked ? tint : appState.themeText.opacity(0.07)))
                    .overlay(Capsule().strokeBorder(locked ? Color.clear : appState.themeBorder, lineWidth: 0.5))
                }
                .buttonStyle(.plain)
                .help(locked ? "Stop editing this slide" : "Lock this slide — your next message edits it")
            }
        }
    }

    private func stageButton(_ icon: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 10.5, weight: .bold))
                .foregroundColor(appState.themeText)
                .frame(width: 26, height: 26)
                .background(Circle().fill(appState.themeText.opacity(0.07)))
                .overlay(Circle().strokeBorder(appState.themeBorder, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
        .help(help)
    }

    // MARK: Filmstrip

    private var filmstrip: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    thumbnail(nil, label: "Cover")
                    ForEach(Array(slides.indices), id: \.self) { index in
                        thumbnail(index, label: "\(index + 1)")
                    }
                }
                .padding(.horizontal, 2)
                .padding(.vertical, 4)
            }
            .onChange(of: shown) { _, index in
                withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(index ?? -1, anchor: .center) }
            }
        }
    }

    private func thumbnail(_ index: Int?, label: String) -> some View {
        let isShown = shown == index
        let isLocked = index != nil && selectedSlideIndex == index
        return Button { show(index) } label: {
            VStack(spacing: 5) {
                slideCanvas(index)
                    .frame(width: 128, height: 72)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .stroke(isShown ? tint : appState.themeBorder, lineWidth: isShown ? 2 : 0.5)
                    )
                    .overlay(alignment: .topTrailing) {
                        if isLocked {
                            Image(systemName: "pencil.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(.white, tint)
                                .padding(4)
                        }
                    }
                Text(label)
                    .font(.espresso(size: 10, weight: isShown ? .semibold : .regular))
                    .foregroundColor(isShown ? appState.themeText : appState.themeTextSecondary)
            }
        }
        .buttonStyle(.plain)
        .id(index ?? -1)
    }

    private func notesCard(_ notes: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Speaker notes", systemImage: "text.bubble")
                .font(.espresso(size: 10, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
            Text(notes)
                .font(.espresso(size: 12.5))
                .foregroundColor(appState.themeText.opacity(0.85))
                .lineSpacing(3)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(appState.themeCard))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(appState.themeBorder, lineWidth: 0.5))
    }
}

// MARK: - Slide rendering

/// One slide drawn at any size: type scales with the width, so the same view
/// is the stage and a filmstrip thumbnail.
struct SlideCanvas: View {
    let theme: PresentationTheme
    let deckTitle: String
    let slide: PresentationPreview.SlideEntry
    let total: Int

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .topLeading) {
                theme.backgroundColor
                Rectangle()
                    .fill(theme.accentColor)
                    .frame(width: w * 0.008)
                VStack(alignment: .leading, spacing: w * 0.022) {
                    Text(slide.title.isEmpty ? "Slide \(slide.index)" : slide.title)
                        .font(.system(size: max(5, w * 0.048), weight: .bold))
                        .foregroundColor(theme.titleColor)
                        .lineLimit(2)
                        .minimumScaleFactor(0.6)
                    Rectangle()
                        .fill(theme.accentColor)
                        .frame(width: w * 0.06, height: max(1, w * 0.004))
                    VStack(alignment: .leading, spacing: w * 0.014) {
                        ForEach(Array(slide.bullets.prefix(7).enumerated()), id: \.offset) { _, bullet in
                            HStack(alignment: .firstTextBaseline, spacing: w * 0.014) {
                                Circle()
                                    .fill(theme.accentColor)
                                    .frame(width: max(2, w * 0.009), height: max(2, w * 0.009))
                                    .alignmentGuide(.firstTextBaseline) { d in d.height * 0.85 }
                                Text(bullet)
                                    .font(.system(size: max(4, w * 0.026)))
                                    .foregroundColor(theme.textColor)
                                    .lineLimit(2)
                            }
                        }
                    }
                    Spacer(minLength: 0)
                    HStack {
                        Text(deckTitle)
                            .lineLimit(1)
                        Spacer()
                        Text("\(slide.index) / \(total)")
                    }
                    .font(.system(size: max(3, w * 0.016), weight: .medium))
                    .foregroundColor(theme.textColor.opacity(0.55))
                }
                .padding(.horizontal, w * 0.065)
                .padding(.top, w * 0.06)
                .padding(.bottom, w * 0.035)
            }
        }
    }
}

/// The deck's cover: title, subtitle and the cover image when there is one.
struct SlideCoverCanvas: View {
    let theme: PresentationTheme
    let title: String
    let subtitle: String
    let imageURL: String?
    let slideCount: Int

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .bottomLeading) {
                theme.backgroundColor
                if let raw = imageURL, let url = URL(string: raw) {
                    AsyncImage(url: url) { phase in
                        if case .success(let image) = phase {
                            image.resizable().aspectRatio(contentMode: .fill)
                                .frame(width: geo.size.width, height: geo.size.height)
                                .clipped()
                                .overlay(
                                    LinearGradient(colors: [.clear, theme.backgroundColor.opacity(0.92)],
                                                   startPoint: .top, endPoint: .bottom)
                                )
                        }
                    }
                }
                LinearGradient(colors: [theme.accentColor.opacity(0.28), .clear],
                               startPoint: .topTrailing, endPoint: .center)
                VStack(alignment: .leading, spacing: w * 0.018) {
                    Rectangle()
                        .fill(theme.accentColor)
                        .frame(width: w * 0.08, height: max(1, w * 0.006))
                    Text(title)
                        .font(.system(size: max(6, w * 0.064), weight: .heavy))
                        .foregroundColor(theme.titleColor)
                        .lineLimit(3)
                        .minimumScaleFactor(0.6)
                    if !subtitle.isEmpty {
                        Text(subtitle)
                            .font(.system(size: max(4, w * 0.028)))
                            .foregroundColor(theme.textColor.opacity(0.8))
                            .lineLimit(2)
                    }
                    if slideCount > 0 {
                        Text("\(slideCount) slides")
                            .font(.system(size: max(3, w * 0.018), weight: .semibold))
                            .foregroundColor(theme.accentColor)
                            .padding(.top, w * 0.01)
                    }
                }
                .padding(w * 0.07)
            }
        }
    }
}
