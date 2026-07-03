import SwiftUI

struct TranscriptBubbleView: View {
    let message: WSMessage

    var body: some View {
        HStack {
            if message.type == .user {
                Spacer(minLength: 40)
            }

            VStack(alignment: message.type == .user ? .trailing : .leading, spacing: 6) {
                if message.type != .system {
                    Text(labelText)
                        .font(.system(size: 9, weight: .bold))
                        .tracking(2)
                        .foregroundColor(labelColor)
                }

                Text(message.content)
                    .font(.system(size: 15))
                    .foregroundColor(textColor)
                    .multilineTextAlignment(message.type == .user ? .trailing : .leading)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(backgroundColor)
            .overlay(borderOverlay)

            if message.type == .assistant {
                Spacer(minLength: 40)
            }
        }
    }

    private var labelText: String {
        switch message.type {
        case .user:
            return "CANDIDATE"
        case .assistant:
            return "AI INTERVIEWER"
        default:
            return ""
        }
    }

    private var labelColor: Color {
        switch message.type {
        case .user:
            return .gray
        case .assistant:
            return Color(red: 0.2, green: 0.8, blue: 0.6)
        default:
            return .gray
        }
    }

    private var textColor: Color {
        switch message.type {
        case .user:
            return .white
        case .assistant:
            return Color(red: 0.85, green: 1.0, blue: 0.9)
        case .system, .status:
            return .gray
        }
    }

    private var backgroundColor: Color {
        switch message.type {
        case .user:
            return Color(white: 0.1)
        case .assistant:
            return Color(white: 0.05)
        case .system, .status:
            return .clear
        }
    }

    @ViewBuilder
    private var borderOverlay: some View {
        switch message.type {
        case .user:
            Rectangle()
                .stroke(Color(white: 0.25), lineWidth: 1)
        case .assistant:
            Rectangle()
                .stroke(Color(red: 0.2, green: 0.8, blue: 0.6).opacity(0.3), lineWidth: 1)
        case .system, .status:
            Rectangle()
                .stroke(style: StrokeStyle(lineWidth: 1, dash: [4]))
                .foregroundColor(Color(white: 0.2))
        }
    }
}

struct TranscriptListView: View {
    let messages: [WSMessage]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 16) {
                    ForEach(messages) { message in
                        TranscriptBubbleView(message: message)
                            .id(message.id)
                    }
                }
                .padding()
            }
            .onChange(of: messages.count) { _ in
                if let lastMessage = messages.last {
                    withAnimation(.easeOut(duration: 0.3)) {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
    }
}

#Preview {
    let messages = [
        WSMessage(type: .system, content: "Connected to interview"),
        WSMessage(type: .assistant, content: "Hello! Thank you for joining this practice interview. I'm going to ask you some questions about your experience and approach to work. Let's start with an easy one - can you tell me about yourself?"),
        WSMessage(type: .user, content: "Sure! I'm a software engineer with 5 years of experience, primarily focused on mobile development. I've worked at both startups and larger companies."),
        WSMessage(type: .assistant, content: "That's great background. Can you tell me about a challenging project you've worked on recently?"),
    ]

    TranscriptListView(messages: messages)
        .background(Color.black)
}
