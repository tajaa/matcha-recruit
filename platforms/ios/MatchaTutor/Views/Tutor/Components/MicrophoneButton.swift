import SwiftUI

struct MicrophoneButton: View {
    let isRecording: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: isRecording ? "stop.fill" : "mic.fill")
                    .font(.system(size: 18, weight: .semibold))

                Text(isRecording ? "STOP SPEAKING" : "START SPEAKING")
                    .font(.system(size: 12, weight: .bold))
                    .tracking(2)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 56)
            .background(isRecording ? Color.red : Color.white)
            .foregroundColor(isRecording ? .white : .black)
        }
        .animation(.easeInOut(duration: 0.2), value: isRecording)
    }
}

struct PulsingCircle: View {
    @State private var isAnimating = false

    var body: some View {
        Circle()
            .fill(Color.red.opacity(0.3))
            .scaleEffect(isAnimating ? 1.3 : 1.0)
            .opacity(isAnimating ? 0 : 1)
            .animation(
                .easeInOut(duration: 1.0)
                .repeatForever(autoreverses: false),
                value: isAnimating
            )
            .onAppear {
                isAnimating = true
            }
    }
}

#Preview {
    VStack(spacing: 20) {
        MicrophoneButton(isRecording: false) {}
        MicrophoneButton(isRecording: true) {}
    }
    .padding()
    .background(Color.black)
}
