import SwiftUI

/// A thread's document, framed by the asset canvas (header, actions, live
/// state, desk). `context` carries what only the thread knows — version,
/// history, streaming, focus — and defaults to nothing for callers without it.
struct PreviewPanelView: View {
    @Environment(AppState.self) private var appState
    let currentState: [String: AnyCodable]
    let pdfData: Data?
    /// Whether `pdfData` matches the version and status on show
    /// (`ThreadDetailViewModel.pdfIsCurrent`). Saving or opening the PDF
    /// elsewhere waits until it does.
    var pdfIsCurrent = false
    let isLoading: Bool
    let taskType: MWTaskType?
    var threadId: String?
    @Binding var selectedSlideIndex: Int?
    var context = AssetCanvasContext()

    private var exportablePDF: Data? { pdfIsCurrent ? pdfData : nil }

    private var resolvedTaskType: MWTaskType {
        taskType ?? inferMWTaskType(from: currentState)
    }

    var body: some View {
        let type = resolvedTaskType
        let kind = AssetKind(type)
        let title = kind.title(from: currentState) ?? context.threadTitle ?? kind.name
        AssetCanvasView(
            kind: kind,
            title: title,
            context: context,
            surface: isLoading ? .stage : Self.surface(for: type),
            copyText: AssetExport.copyText(type, state: currentState),
            download: AssetExport.download(type, state: currentState, title: title,
                                           threadId: threadId, pdfData: exportablePDF),
            openExternally: AssetExport.openExternally(type, title: title, pdfData: exportablePDF)
        ) {
            if isLoading {
                VStack(spacing: 12) {
                    ProgressView().controlSize(.small)
                    Text("Loading document…")
                        .font(.espresso(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                preview(type)
            }
        }
    }

    static func surface(for type: MWTaskType) -> AssetSurface {
        switch type {
        case .offerLetter: return .fullBleed
        case .presentation: return .stage
        case .resumeBatch, .inventory: return .panel
        default: return .paper
        }
    }

    @ViewBuilder
    private func preview(_ type: MWTaskType) -> some View {
        switch type {
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
        case .policy:
            PolicyPreview(state: currentState)
        case .resumeBatch:
            ResumeBatchPanelView(state: currentState, threadId: threadId)
        case .inventory:
            InventoryPanelView(state: currentState)
        case .chat, .project, .languageTutor, .blog:
            EmptyPreviewView()
        }
    }
}
