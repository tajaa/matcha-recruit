import SwiftUI

struct SessionTimerView: View {
    let timeRemaining: Int?
    let isWarning: Bool

    private var timeString: String {
        guard let seconds = timeRemaining else { return "--:--" }
        let mins = seconds / 60
        let secs = seconds % 60
        return String(format: "%d:%02d", mins, secs)
    }

    private var isLowTime: Bool {
        guard let seconds = timeRemaining else { return false }
        return seconds < 60
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "clock.fill")
                .font(.system(size: 14))
                .foregroundColor(.gray)

            Text(timeString)
                .font(.system(size: 20, weight: .bold, design: .monospaced))
                .foregroundColor(isLowTime ? .red : .white)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color(white: 0.1))
        .overlay(
            RoundedRectangle(cornerRadius: 0)
                .stroke(Color(white: 0.2), lineWidth: 1)
        )
        .opacity(isLowTime ? (isWarning ? 0.5 : 1.0) : 1.0)
        .animation(
            isLowTime ? .easeInOut(duration: 0.5).repeatForever(autoreverses: true) : .default,
            value: isLowTime
        )
    }
}

#Preview {
    VStack(spacing: 20) {
        SessionTimerView(timeRemaining: 300, isWarning: false)
        SessionTimerView(timeRemaining: 45, isWarning: false)
        SessionTimerView(timeRemaining: 30, isWarning: true)
        SessionTimerView(timeRemaining: nil, isWarning: false)
    }
    .padding()
    .background(Color.black)
}
