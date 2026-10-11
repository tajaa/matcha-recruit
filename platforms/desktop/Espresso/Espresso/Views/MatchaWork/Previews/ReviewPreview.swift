import SwiftUI

struct ReviewPreview: View {
    @Environment(AppState.self) private var appState
    let state: [String: AnyCodable]

    var title: String { (state["review_title"]?.value as? String) ?? "Performance Review" }
    var overallRating: Int {
        if let v = state["overall_rating"]?.value as? Int { return v }
        if let v = state["overall_rating"]?.value as? Double { return Int(v) }
        return 0
    }
    var strengths: [String] { (state["strengths"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? [] }
    var growthAreas: [String] { (state["growth_areas"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? [] }
    var nextSteps: [String] { (state["next_steps"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? [] }
    var summary: String { (state["summary"]?.value as? String) ?? "" }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            // Header
            VStack(alignment: .leading, spacing: 8) {
                Text("PERFORMANCE REVIEW")
                    .font(.espresso(size: 10, weight: .semibold))
                    .tracking(1.2)
                    .foregroundColor(AssetKind(.review).tint)
                Text(title)
                    .font(.espresso(size: 22, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .fixedSize(horizontal: false, vertical: true)

                if overallRating > 0 {
                    HStack(spacing: 3) {
                        ForEach(1...5, id: \.self) { star in
                            Image(systemName: star <= overallRating ? "star.fill" : "star")
                                .font(.system(size: 13))
                                .foregroundColor(star <= overallRating ? AssetKind(.review).tint : appState.themeTextSecondary.opacity(0.5))
                        }
                        Text("\(overallRating) of 5")
                            .font(.espresso(size: 12, weight: .medium))
                            .foregroundColor(appState.themeTextSecondary)
                            .padding(.leading, 4)
                    }
                }
                Rectangle().fill(appState.themeBorder).frame(height: 0.5).padding(.top, 4)
            }

            if !summary.isEmpty {
                Text(summary)
                    .font(.espresso(size: 14))
                    .foregroundColor(appState.themeText.opacity(0.85))
                    .lineSpacing(5)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !strengths.isEmpty {
                ReviewSection(title: "Strengths", items: strengths, icon: "checkmark.circle.fill", color: .green)
            }

            if !growthAreas.isEmpty {
                ReviewSection(title: "Growth Areas", items: growthAreas, icon: "arrow.up.circle.fill", color: .blue)
            }

            if !nextSteps.isEmpty {
                ReviewSection(title: "Next Steps", items: nextSteps, icon: "arrow.right.circle.fill", color: .orange, numbered: true)
            }

            if state.isEmpty {
                EmptyPreviewView(message: "Review in progress...", icon: "star")
            }
        }
    }
}

struct ReviewSection: View {
    @Environment(AppState.self) private var appState
    let title: String
    let items: [String]
    let icon: String
    let color: Color
    var numbered: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 7) {
                RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 3, height: 14)
                Text(title)
                    .font(.espresso(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: 9) {
                        if numbered {
                            Text("\(index + 1)")
                                .font(.espresso(size: 10, weight: .bold))
                                .foregroundColor(color)
                                .frame(width: 18, height: 18)
                                .background(Circle().fill(color.opacity(0.14)))
                        } else {
                            Image(systemName: icon)
                                .font(.system(size: 12))
                                .foregroundColor(color)
                                .frame(width: 18, height: 18)
                        }
                        Text(item)
                            .font(.espresso(size: 13))
                            .foregroundColor(appState.themeText.opacity(0.85))
                            .lineSpacing(3)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(appState.assetWell))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(appState.themeBorder, lineWidth: 0.5))
    }
}
