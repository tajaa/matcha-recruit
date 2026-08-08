import SwiftUI

enum Formatters {
    private static let isoWithFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    private static let relative: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f
    }()

    /// FastAPI emits ISO8601 with or without fractional seconds — try both.
    static func date(from iso8601: String?) -> Date? {
        guard let iso8601 else { return nil }
        return isoWithFractional.date(from: iso8601) ?? Formatters.iso.date(from: iso8601)
    }

    static func relativeString(from iso8601: String?) -> String {
        guard let d = date(from: iso8601) else { return "" }
        return relative.localizedString(for: d, relativeTo: Date())
    }
}

struct PointsPill: View {
    let points: Int
    var body: some View {
        Label("\(points)", systemImage: "sparkles")
            .font(.footnote.bold())
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(.tint.opacity(0.15), in: Capsule())
            .foregroundStyle(.tint)
    }
}

struct LevelProgressBar: View {
    let progress: Double
    let level: Int
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Level \(level)").font(.caption.bold())
            ProgressView(value: min(max(progress, 0), 1))
                .tint(.accentColor)
        }
    }
}

struct SentimentBadge: View {
    let sentiment: Sentiment
    var body: some View {
        Text(sentiment.rawValue.capitalized)
            .font(.caption2.bold())
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }
    private var color: Color {
        switch sentiment {
        case .positive: return .green
        case .neutral: return .gray
        case .negative: return .red
        }
    }
}

struct StatusChip: View {
    let text: String
    var tint: Color = .secondary
    var body: some View {
        Text(text.replacingOccurrences(of: "_", with: " ").capitalized)
            .font(.caption2.bold())
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(tint.opacity(0.15), in: Capsule())
            .foregroundStyle(tint)
    }
}

struct EmptyState: View {
    let icon: String
    let title: String
    var hint: String? = nil
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon).font(.system(size: 36)).foregroundStyle(.secondary)
            Text(title).font(.headline)
            if let hint { Text(hint).font(.footnote).foregroundStyle(.secondary) }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }
}
