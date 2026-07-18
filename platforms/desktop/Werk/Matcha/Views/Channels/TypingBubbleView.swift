import SwiftUI

// MARK: - Typing bubble

struct TypingBubbleView: View {
    @State private var phase: Int = 0

    private let dotSize: CGFloat = 5
    private let dotColor = Color.borderColor

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(dotColor)
                    .frame(width: dotSize, height: dotSize)
                    .scaleEffect(phase == i ? 1.4 : 0.8)
                    .animation(
                        .easeInOut(duration: 0.4)
                            .repeatForever(autoreverses: true)
                            .delay(Double(i) * 0.15),
                        value: phase
                    )
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(Color.cardBackground)
        .cornerRadius(10)
        .onAppear {
            phase = 0
            withAnimation { phase = 2 }
        }
    }
}
