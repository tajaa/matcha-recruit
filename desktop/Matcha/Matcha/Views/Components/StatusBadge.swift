import SwiftUI

struct StatusBadge: View {
    let status: String

    var body: some View {
        Text(status.capitalized)
            .font(.system(size: 10, weight: .medium))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(backgroundColor)
            .foregroundColor(textColor)
            .cornerRadius(4)
    }

    private var backgroundColor: Color {
        switch status.lowercased() {
        case "active": return Color.green.opacity(0.2)
        case "finalized": return Color.blue.opacity(0.2)
        case "archived": return Color.gray.opacity(0.2)
        case "draft": return Color.yellow.opacity(0.2)
        default: return Color.gray.opacity(0.15)
        }
    }

    private var textColor: Color {
        switch status.lowercased() {
        case "active": return Color.green
        case "finalized": return Color.blue
        case "archived": return Color.gray
        case "draft": return Color.yellow
        default: return Color.secondary
        }
    }
}

struct VersionBadge: View {
    let version: Int

    var body: some View {
        Text("v\(version)")
            .font(.system(size: 11, design: .monospaced))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.zinc800)
            .foregroundColor(.white)
            .cornerRadius(4)
    }
}
