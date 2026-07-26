import SwiftUI

/// Small pill rendered in the project toolbar showing who's currently in
/// the project. Each member is a colored circle with their initial; up to
/// 4 are stacked horizontally with a slight overlap, with "+N" at the end
/// if there are more. Color matches the cursor color so the user reads as
/// the same individual across pill / cursor / caret.
struct PresencePillContent: View {
    let members: [ProjectWebSocket.PresenceMember]

    private let maxVisible = 4
    private let dot: CGFloat = 18
    private let overlap: CGFloat = 6

    var body: some View {
        let visible = Array(members.prefix(maxVisible))
        let hidden = max(0, members.count - maxVisible)
        return HStack(spacing: -overlap) {
            ForEach(visible) { m in
                memberDot(member: m)
            }
            if hidden > 0 {
                Text("+\(hidden)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.white.opacity(0.7))
                    .frame(width: dot, height: dot)
                    .background(Circle().fill(Color.zinc800))
                    .overlay(Circle().stroke(Color.appBackground, lineWidth: 1.5))
            }
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 2)
    }

    private func memberDot(member: ProjectWebSocket.PresenceMember) -> some View {
        let initial = String(member.name.prefix(1)).uppercased()
        let color = UserColor.forUserId(member.id)
        return ZStack {
            Circle().fill(color)
            Text(initial)
                .font(.system(size: 9, weight: .bold))
                .foregroundColor(.white)
        }
        .frame(width: dot, height: dot)
        .overlay(Circle().stroke(Color.appBackground, lineWidth: 1.5))
        .help(member.name)
    }
}
