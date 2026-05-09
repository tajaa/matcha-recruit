import SwiftUI

struct LoadingDots: View {
    @State private var animating = false

    private let dotCount = 3
    private let dotSize: CGFloat = 7
    private let spacing: CGFloat = 5

    var body: some View {
        HStack(spacing: spacing) {
            ForEach(0..<dotCount, id: \.self) { index in
                Circle()
                    .fill(Color.secondary)
                    .frame(width: dotSize, height: dotSize)
                    .scaleEffect(animating ? 1.0 : 0.5)
                    .animation(
                        .easeInOut(duration: 0.5)
                            .repeatForever(autoreverses: true)
                            .delay(Double(index) * 0.15),
                        value: animating
                    )
            }
        }
        .onAppear { animating = true }
        .onDisappear { animating = false }
    }
}
