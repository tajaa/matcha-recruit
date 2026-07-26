import SwiftUI

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
                case .resumeBatch:
                    ResumeBatchPanelView(state: currentState, threadId: threadId)
                case .inventory:
                    InventoryPanelView(state: currentState)
                case .chat, .policy, .project, .languageTutor, .blog:
                    EmptyPreviewView()
                }
            }
        }
    }
}
