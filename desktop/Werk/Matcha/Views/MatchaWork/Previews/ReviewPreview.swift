import SwiftUI

struct ReviewPreview: View {
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
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    if overallRating > 0 {
                        HStack(spacing: 4) {
                            ForEach(1...5, id: \.self) { star in
                                Image(systemName: star <= overallRating ? "star.fill" : "star")
                                    .font(.system(size: 14))
                                    .foregroundColor(star <= overallRating ? .yellow : .secondary)
                            }
                            Text("(\(overallRating)/5)")
                                .font(.system(size: 13))
                                .foregroundColor(.secondary)
                        }
                    }
                }

                if !summary.isEmpty {
                    Text(summary)
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                        .lineSpacing(4)
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
            .padding(20)
        }
    }
}

struct ReviewSection: View {
    let title: String
    let items: [String]
    let icon: String
    let color: Color
    var numbered: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white)

            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: 8) {
                        if numbered {
                            Text("\(index + 1).")
                                .font(.system(size: 12))
                                .foregroundColor(color)
                                .frame(width: 18, alignment: .trailing)
                        } else {
                            Image(systemName: icon)
                                .font(.system(size: 12))
                                .foregroundColor(color)
                                .frame(width: 18)
                        }
                        Text(item)
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.85))
                            .lineSpacing(3)
                    }
                }
            }
        }
        .padding(12)
        .background(Color.zinc800)
        .cornerRadius(8)
    }
}
