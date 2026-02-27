import SwiftUI

struct ChatPanelView: View {
    @Bindable var viewModel: ThreadDetailViewModel
    @State private var inputText = ""
    @State private var scrollProxy: ScrollViewProxy?

    private func send() {
        let content = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !viewModel.isStreaming else { return }
        inputText = ""
        Task { await viewModel.sendMessage(content: content) }
    }

    var body: some View {
        VStack(spacing: 0) {
            if viewModel.isLoadingThread {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else {
                // Messages
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(viewModel.messages) { message in
                                MessageBubbleView(message: message)
                                    .id(message.id)
                            }

                            // Streaming bubble
                            if viewModel.isStreaming {
                                StreamingBubbleView(content: viewModel.streamingContent)
                                    .id("streaming")
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                    }
                    .onChange(of: viewModel.messages.count) {
                        if let lastId = viewModel.messages.last?.id {
                            withAnimation(.easeOut(duration: 0.2)) {
                                proxy.scrollTo(lastId, anchor: .bottom)
                            }
                        }
                    }
                    .onChange(of: viewModel.isStreaming) {
                        if viewModel.isStreaming {
                            withAnimation { proxy.scrollTo("streaming", anchor: .bottom) }
                        }
                    }
                }

                Divider().opacity(0.3)

                // Error banner
                if let err = viewModel.errorMessage {
                    Text(err)
                        .font(.system(size: 12))
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .background(Color.red.opacity(0.1))
                }

                // Input area
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Message...", text: $inputText, axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .foregroundColor(.white)
                        .lineLimit(1...6)
                        .padding(.vertical, 8)
                        .onSubmit {
                            send()
                        }

                    Button { send() } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 28))
                            .foregroundColor(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? .secondary : .matcha500)
                    }
                    .buttonStyle(.plain)
                    .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isStreaming)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color.zinc900)
            }
        }
        .background(Color.appBackground)
    }
}
