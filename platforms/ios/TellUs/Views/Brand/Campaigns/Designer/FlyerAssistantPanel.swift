import SwiftUI

struct FlyerAssistantPanel: View {
    let campaignID: String
    let design: FlyerDesign
    let selectedLayer: DesignLayer?
    let assets: FlyerRenderAssets
    let assistant: FlyerAssistantViewModel
    let onDesign: (FlyerDesign) -> Void
    @State private var draft = ""

    private let quickPrompts = [
        "Make it feel warmer",
        "Make the headline bigger",
        "Give it a dark, high-contrast look",
        "Move the QR to the bottom right",
    ]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if assistant.messages.isEmpty {
                            Text("Ask for a change in plain language, or start from a generated idea. Each turn becomes one undo step.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                            quickPromptView
                        }

                        ForEach(assistant.messages) { message in
                            messageView(message)
                        }

                        if let error = assistant.error {
                            Text(error).font(.footnote).foregroundStyle(.red)
                        }
                    }
                    .padding()
                }

                Divider()
                ideas
                HStack(alignment: .bottom, spacing: 8) {
                    TextField(selectedLayer == nil ? "Ask for a change..." : "Change selected layer...", text: $draft, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                    Button {
                        send(draft)
                        draft = ""
                    } label: {
                        Image(systemName: assistant.isSending ? "hourglass" : "paperplane.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(assistant.isSending || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                .padding()
            }
            .navigationTitle("Design assistant")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var quickPromptView: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack {
                ForEach(quickPrompts, id: \.self) { prompt in
                    Button(prompt) { send(prompt) }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }
            }
        }
    }

    private func messageView(_ message: FlyerAssistantMessage) -> some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
            Text(message.content)
                .padding(9)
                .background(message.role == .user ? Color.accentColor.opacity(0.16) : Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
                .frame(maxWidth: .infinity, alignment: message.role == .user ? .trailing : .leading)
            ForEach(Array(message.results.enumerated()), id: \.offset) { _, result in
                Label(result.summary, systemImage: result.ok ? "checkmark" : "xmark")
                    .font(.caption)
                    .foregroundStyle(result.ok ? Color.secondary : Color.red)
            }
            ForEach(Array(message.rejected.enumerated()), id: \.offset) { _, rejection in
                Text("Skipped - \(rejection.reason)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var ideas: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Ideas").font(.subheadline.weight(.semibold))
                Spacer()
                Button(assistant.ideas.isEmpty ? "Generate" : "Regenerate") {
                    Task { await assistant.loadIdeas(campaignID: campaignID) }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(assistant.isSending || assistant.isLoadingIdeas)
            }
            if !assistant.ideas.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(assistant.ideas) { idea in
                            Button {
                                onDesign(assistant.applyIdea(idea))
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    FlyerCanvasView(
                                        design: idea.design,
                                        claimURL: "",
                                        assets: assets,
                                        selectedLayerID: nil,
                                        interactive: false,
                                        onSelect: { _ in },
                                        onLayerChange: { _, _ in }
                                    )
                                    .frame(width: 100, height: 100)
                                    Text(idea.label).font(.caption).lineLimit(1)
                                }
                                .frame(width: 110)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .padding(.horizontal)
        .padding(.top, 8)
    }

    private func send(_ text: String) {
        let selection: FlyerAiSelection?
        if let selectedLayer {
            let selectedText: String?
            if case .text(let layer) = selectedLayer {
                selectedText = layer.text
            } else {
                selectedText = nil
            }
            selection = FlyerAiSelection(layer: selectedLayer.id, kind: selectedLayer.kind, text: selectedText)
        } else {
            selection = nil
        }
        Task {
            if let next = await assistant.send(campaignID: campaignID, design: design, message: text, selection: selection) {
                onDesign(next)
            }
        }
    }
}
