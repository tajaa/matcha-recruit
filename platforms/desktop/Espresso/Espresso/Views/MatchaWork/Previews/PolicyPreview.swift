import SwiftUI

/// A policy the policy skill is building: the brief while it collects what it
/// needs, a drafting skeleton while it writes, then the policy itself
/// (`policy_content`, markdown).
struct PolicyPreview: View {
    @Environment(AppState.self) private var appState
    let state: [String: AnyCodable]

    private enum Phase { case collecting, generating, created }

    private var phase: Phase {
        switch (state["policy_status"]?.value as? String)?.lowercased() {
        case "created": return .created
        case "generating": return .generating
        default: return content == nil ? .collecting : .created
        }
    }

    private var content: String? {
        guard let raw = state["policy_content"]?.value as? String,
              !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return raw
    }

    private var title: String { text("policy_title") ?? "Untitled policy" }

    private var locations: [String] {
        if let list = state["policy_location_names"]?.value as? [AnyCodable] {
            return list.compactMap { $0.value as? String }
        }
        return text("policy_location_names").map { [$0] } ?? []
    }

    private func text(_ key: String) -> String? {
        guard let raw = state[key]?.value as? String else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            masthead
            switch phase {
            case .created:
                if let content {
                    JournalContentView(
                        content: content,
                        fontFamily: "system",
                        fontSize: 14,
                        lineSpacing: 5,
                        baseColor: appState.themeText
                    )
                    .textSelection(.enabled)
                } else {
                    drafting
                }
            case .generating:
                drafting
            case .collecting:
                brief
            }
        }
    }

    // MARK: Pieces

    private var masthead: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("POLICY")
                .font(.espresso(size: 10, weight: .semibold))
                .tracking(1.2)
                .foregroundColor(AssetKind(.policy).tint)
            Text(title)
                .font(.espresso(size: 22, weight: .bold))
                .foregroundColor(appState.themeText)
                .fixedSize(horizontal: false, vertical: true)
            if text("policy_type") != nil || !locations.isEmpty {
                HStack(spacing: 6) {
                    if let type = text("policy_type") {
                        chip(type.replacingOccurrences(of: "_", with: " ").capitalized, icon: "tag")
                    }
                    ForEach(locations.prefix(3), id: \.self) { chip($0, icon: "mappin") }
                    if locations.count > 3 { chip("+\(locations.count - 3)", icon: nil) }
                }
            }
            Rectangle().fill(appState.themeBorder).frame(height: 0.5).padding(.top, 4)
        }
    }

    private func chip(_ label: String, icon: String?) -> some View {
        HStack(spacing: 4) {
            if let icon { Image(systemName: icon).font(.system(size: 9)) }
            Text(label).font(.espresso(size: 11)).lineLimit(1)
        }
        .foregroundColor(appState.themeTextSecondary)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Capsule().fill(appState.assetWell))
        .overlay(Capsule().strokeBorder(appState.themeBorder, lineWidth: 0.5))
    }

    /// While the skill writes: the policy's shape, shimmering.
    private var drafting: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Drafting your policy…")
                    .font(.espresso(size: 12, weight: .medium))
                    .foregroundColor(appState.themeTextSecondary)
            }
            ForEach(0..<3, id: \.self) { block in
                VStack(alignment: .leading, spacing: 8) {
                    SkeletonBar(width: block == 0 ? 220 : 170, height: 14)
                    SkeletonBar(height: 10)
                    SkeletonBar(height: 10)
                    SkeletonBar(width: block == 1 ? 260 : 320, height: 10)
                }
                .padding(.top, 6)
            }
        }
        .shimmer()
    }

    /// While the skill is still asking: what it knows so far.
    private var brief: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("The brief so far")
                .font(.espresso(size: 12, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
            briefRow("Policy", value: text("policy_title"))
            briefRow("Type", value: text("policy_type")?.replacingOccurrences(of: "_", with: " ").capitalized)
            briefRow("Applies to", value: locations.isEmpty ? nil : locations.joined(separator: ", "))
            briefRow("Context", value: text("policy_additional_context"))
            Text("Answer in the chat and the draft appears here.")
                .font(.espresso(size: 11))
                .foregroundColor(appState.themeTextSecondary.opacity(0.8))
                .padding(.top, 4)
        }
    }

    private func briefRow(_ label: String, value: String?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: value == nil ? "circle.dashed" : "checkmark.circle.fill")
                .font(.system(size: 12))
                .foregroundColor(value == nil ? appState.themeTextSecondary.opacity(0.6) : AssetKind(.policy).tint)
            Text(label)
                .font(.espresso(size: 12, weight: .medium))
                .foregroundColor(appState.themeText)
                .frame(width: 78, alignment: .leading)
            Text(value ?? "Not yet")
                .font(.espresso(size: 12))
                .foregroundColor(value == nil ? appState.themeTextSecondary.opacity(0.7) : appState.themeText.opacity(0.85))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(appState.assetWell))
    }
}
