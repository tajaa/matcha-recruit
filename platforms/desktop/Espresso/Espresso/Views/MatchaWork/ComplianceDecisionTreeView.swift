import SwiftUI

/// Native SwiftUI compliance decision tree visualization.
/// Renders AI reasoning steps and jurisdiction levels as expandable cards in a vertical flow.
struct ComplianceDecisionTreeView: View {
    let aiSteps: [MWAIReasoningStep]
    let categories: [MWComplianceReasoningCategory]

    @State private var expandedStep: Int?
    @State private var expandedLevel: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "arrow.triangle.branch")
                    .font(.system(size: 11))
                    .foregroundColor(.cyan)
                Text("Decision Tree")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white)
            }
            .padding(.bottom, 8)

            // AI Reasoning Steps
            if !aiSteps.isEmpty {
                Text("REASONING STEPS")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                    .padding(.bottom, 4)

                ForEach(aiSteps, id: \.step) { step in
                    StepNode(
                        step: step,
                        isExpanded: expandedStep == step.step,
                        onToggle: {
                            withAnimation(.easeOut(duration: 0.15)) {
                                expandedStep = expandedStep == step.step ? nil : step.step
                            }
                        }
                    )

                    // Connector line
                    if step.step < aiSteps.count {
                        HStack {
                            Rectangle()
                                .fill(Color.cyan.opacity(0.3))
                                .frame(width: 2, height: 16)
                                .padding(.leading, 14)
                            Spacer()
                        }
                    }
                }
            }

            // Jurisdiction Levels
            if !categories.isEmpty {
                Text("JURISDICTION LEVELS")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                    .padding(.top, 12)
                    .padding(.bottom, 4)

                ForEach(categories, id: \.category) { cat in
                    ForEach(cat.allLevels, id: \.jurisdictionLevel) { level in
                        LevelNode(
                            level: level,
                            category: cat.category,
                            precedenceType: cat.precedenceType,
                            isExpanded: expandedLevel == "\(cat.category):\(level.jurisdictionLevel)",
                            onToggle: {
                                let key = "\(cat.category):\(level.jurisdictionLevel)"
                                withAnimation(.easeOut(duration: 0.15)) {
                                    expandedLevel = expandedLevel == key ? nil : key
                                }
                            }
                        )
                    }
                }
            }
        }
        .padding(12)
    }
}

// MARK: - Step Node

private struct StepNode: View {
    let step: MWAIReasoningStep
    let isExpanded: Bool
    let onToggle: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button(action: onToggle) {
                HStack(spacing: 8) {
                    Circle()
                        .fill(Color.cyan)
                        .frame(width: 24, height: 24)
                        .overlay(
                            Text("\(step.step)")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(.white)
                        )
                    Text(step.question)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.white)
                        .lineLimit(isExpanded ? nil : 2)
                        .multilineTextAlignment(.leading)
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }
            .buttonStyle(.plain)
            .padding(8)

            if isExpanded {
                VStack(alignment: .leading, spacing: 6) {
                    Label(step.answer, systemImage: "text.quote")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)

                    HStack(spacing: 4) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 10))
                            .foregroundColor(.green)
                        Text(step.conclusion)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(.green)
                    }

                    if let sources = step.sources, !sources.isEmpty {
                        ForEach(sources, id: \.self) { source in
                            HStack(spacing: 4) {
                                Image(systemName: "link")
                                    .font(.system(size: 8))
                                    .foregroundColor(.cyan)
                                Text(source)
                                    .font(.system(size: 9))
                                    .foregroundColor(.cyan)
                                    .lineLimit(1)
                            }
                        }
                    }
                }
                .padding(.horizontal, 40)
                .padding(.bottom, 8)
                .transition(.opacity)
            }
        }
        .background(Color.zinc800.opacity(0.4))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.cyan.opacity(0.2), lineWidth: 1)
        )
    }
}

// MARK: - Level Node

private struct LevelNode: View {
    let level: MWComplianceReasoningLevel
    let category: String
    let precedenceType: String?
    let isExpanded: Bool
    let onToggle: () -> Void

    private var borderColor: Color {
        if level.isGoverning { return .cyan }
        switch precedenceType {
        case "floor": return .green
        case "ceiling": return .orange
        case "supersede": return .red
        case "additive": return .blue
        default: return Color.secondary.opacity(0.3)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button(action: onToggle) {
                HStack(spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(level.jurisdictionName)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.white)
                        Text(level.jurisdictionLevel.uppercased())
                            .font(.system(size: 8, weight: .medium))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    if level.isGoverning {
                        Text("GOVERNING")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundColor(.cyan)
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .background(Color.cyan.opacity(0.15))
                            .cornerRadius(3)
                    }
                    if let val = level.currentValue {
                        Text(val)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(.white)
                            .lineLimit(1)
                    }
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }
            .buttonStyle(.plain)
            .padding(8)

            if isExpanded {
                VStack(alignment: .leading, spacing: 4) {
                    if let date = level.effectiveDate {
                        Label("Effective: \(date)", systemImage: "calendar").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    if let citation = level.statuteCitation {
                        Label(citation, systemImage: "building.columns").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    if let penalty = level.penaltySummary {
                        Label(penalty, systemImage: "exclamationmark.triangle").font(.system(size: 10)).foregroundColor(.red)
                    }
                    if let agency = level.enforcingAgency {
                        Label(agency, systemImage: "shield").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    if let url = level.sourceUrl {
                        HStack(spacing: 4) {
                            Image(systemName: "link").font(.system(size: 8)).foregroundColor(.cyan)
                            Text(url).font(.system(size: 9)).foregroundColor(.cyan).lineLimit(1)
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
                .transition(.opacity)
            }
        }
        .background(Color.zinc800.opacity(0.3))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(borderColor.opacity(level.isGoverning ? 0.6 : 0.25), lineWidth: level.isGoverning ? 2 : 1)
        )
        .padding(.vertical, 2)
    }
}
