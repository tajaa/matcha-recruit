import SwiftUI

struct MessageBubbleView: View {
    let message: MWMessage

    var body: some View {
        VStack(alignment: message.role == "user" ? .trailing : .leading, spacing: 4) {
            if message.role == "system" {
                systemMessage
            } else {
                HStack {
                    if message.role == "user" { Spacer(minLength: 60) }
                    VStack(alignment: message.role == "user" ? .trailing : .leading, spacing: 4) {
                        Text(message.content)
                            .font(.system(size: 14))
                            .foregroundColor(.white)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(message.role == "user" ? Color.matcha600 : Color.zinc800)
                            .cornerRadius(12)

                        if let version = message.versionCreated, message.role == "assistant" {
                            Text("Document updated — v\(version)")
                                .font(.system(size: 11))
                                .foregroundColor(.matcha500)
                                .padding(.leading, 4)
                        }
                    }
                    if message.role == "assistant" { Spacer(minLength: 60) }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: message.role == "user" ? .trailing : .leading)
    }

    private var systemMessage: some View {
        Text(message.content)
            .font(.system(size: 12))
            .italic()
            .foregroundColor(.secondary)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, 4)
    }
}

struct StreamingBubbleView: View {
    let content: String

    var body: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                if content.isEmpty {
                    LoadingDots()
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(Color.zinc800)
                        .cornerRadius(12)
                } else {
                    Text(content)
                        .font(.system(size: 14))
                        .foregroundColor(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.zinc800)
                        .cornerRadius(12)
                }
            }
            Spacer(minLength: 60)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
