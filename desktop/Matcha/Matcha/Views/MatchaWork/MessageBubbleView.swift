import SwiftUI

// Process-wide cache so re-renders (or scrolling past the same message twice)
// don't re-parse the markdown. Keyed by raw content; bounded to keep memory in
// check on long threads.
private final class MarkdownCache {
    static let shared = MarkdownCache()
    private let cache = NSCache<NSString, NSAttributedString>()
    private init() { cache.countLimit = 500 }

    func attributed(for content: String) -> AttributedString {
        let key = content as NSString
        if let cached = cache.object(forKey: key) {
            return AttributedString(cached)
        }
        let parsed = (try? AttributedString(
            markdown: content,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(content)
        cache.setObject(NSAttributedString(parsed), forKey: key)
        return parsed
    }
}

struct MessageBubbleView: View {
    let message: MWMessage
    var lightMode: Bool = false

    var body: some View {
        VStack(alignment: message.role == "user" ? .trailing : .leading, spacing: 4) {
            if message.role == "system" {
                systemMessage
            } else {
                HStack {
                    if message.role == "user" { Spacer(minLength: 60) }
                    VStack(alignment: message.role == "user" ? .trailing : .leading, spacing: 4) {
                        VStack(alignment: .leading, spacing: 0) {
                            // Attachment images (user messages may carry screenshots)
                            if let atts = message.metadata?.attachments, !atts.isEmpty {
                                attachmentStrip(atts)
                                    .padding(.horizontal, 8)
                                    .padding(.top, 8)
                            }

                            // Message content
                            if message.role == "assistant" {
                                markdownContent
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                            } else if !message.content.isEmpty {
                                Text(message.content)
                                    .font(.system(size: 14))
                                    .foregroundColor(.white)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                            }

                            // Metadata panels (assistant only)
                            if message.role == "assistant", let meta = message.metadata {
                                metadataPanels(meta)
                            }
                        }
                        .background(bubbleBackground)
                        .cornerRadius(12)

                        if let version = message.versionCreated, message.role == "assistant" {
                            Text("Document updated — v\(version)")
                                .font(.system(size: 11))
                                .foregroundColor(.matcha500)
                                .padding(.leading, 4)
                        }
                    }
                    if message.role == "assistant" { Spacer(minLength: 60) }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: message.role == "user" ? .trailing : .leading)
    }

    private var bubbleBackground: Color {
        if message.role == "user" {
            return Color.matcha600
        }
        return lightMode ? Color(white: 0.96) : Color.zinc800
    }

    @ViewBuilder
    private func attachmentStrip(_ attachments: [MWMessageAttachment]) -> some View {
        let images = attachments.filter { ($0.kind ?? "image") == "image" }
        if !images.isEmpty {
            let columns = min(images.count, 3)
            LazyVGrid(
                columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: columns),
                spacing: 6
            ) {
                ForEach(images, id: \.url) { att in
                    AsyncImage(url: URL(string: att.url)) { phase in
                        switch phase {
                        case .success(let img):
                            img.resizable().scaledToFill()
                        case .failure:
                            Image(systemName: "photo")
                                .foregroundColor(.white.opacity(0.4))
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                                .background(Color.black.opacity(0.15))
                        default:
                            ProgressView()
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                                .background(Color.black.opacity(0.15))
                        }
                    }
                    .frame(height: 120)
                    .clipped()
                    .cornerRadius(8)
                }
            }
            .frame(maxWidth: 320)
        }
    }

    private var markdownContent: some View {
        Text(MarkdownCache.shared.attributed(for: message.content))
            .font(.system(size: 14))
            .foregroundColor(lightMode ? .primary : .white)
            .textSelection(.enabled)
    }

    @ViewBuilder
    private func metadataPanels(_ meta: MWMessageMetadata) -> some View {
        let dividerColor = lightMode ? Color(white: 0.88) : Color.white.opacity(0.1)

        // Compliance Evidence
        if let reasoning = meta.complianceReasoning,
           !reasoning.isEmpty,
           (meta.referencedCategories?.isEmpty == false || meta.aiReasoningSteps?.isEmpty == false) {
            Divider().overlay(dividerColor)
            ComplianceEvidencePanel(
                locations: reasoning,
                referencedCategories: meta.referencedCategories,
                referencedLocations: meta.referencedLocations,
                lightMode: lightMode
            )
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }

        // Affected Employees
        if let employees = meta.affectedEmployees, !employees.isEmpty {
            Divider().overlay(dividerColor)
            AffectedEmployeesPanel(groups: employees, lightMode: lightMode)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
        }

        // Policy Gaps
        if let gaps = meta.complianceGaps, !gaps.isEmpty {
            let refCats = Set(meta.referencedCategories ?? [])
            if !refCats.isEmpty {
                let filtered = gaps.filter { refCats.contains($0.category) }
                if !filtered.isEmpty {
                    Divider().overlay(dividerColor)
                    PolicyGapsPanel(gaps: filtered, lightMode: lightMode)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                }
            }
        }

        // Enforcement Risk
        if let reasoning = meta.complianceReasoning, !reasoning.isEmpty {
            let penalties = extractPenalties(reasoning: reasoning, referencedCategories: meta.referencedCategories, referencedLocations: meta.referencedLocations)
            if !penalties.isEmpty {
                Divider().overlay(dividerColor)
                EnforcementRiskPanel(penalties: penalties, lightMode: lightMode)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
            }
        }

        // Payer Sources
        if let sources = meta.payerSources, !sources.isEmpty {
            Divider().overlay(dividerColor)
            PayerSourcesPanel(sources: sources, lightMode: lightMode)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
        }
    }

    private func extractPenalties(
        reasoning: [MWComplianceReasoningLocation],
        referencedCategories: [String]?,
        referencedLocations: [String]?
    ) -> [(category: String, summary: String, agency: String)] {
        let refCats = Set(referencedCategories ?? [])
        guard !refCats.isEmpty else { return [] }
        let refLocs = Set(referencedLocations ?? [])
        var seen = Set<String>()
        var results: [(category: String, summary: String, agency: String)] = []

        for loc in reasoning {
            if !refLocs.isEmpty &&
               !refLocs.contains(loc.locationLabel) &&
               !refLocs.contains(where: { loc.locationLabel.contains($0) || $0.contains(loc.locationLabel.split(separator: "(").first.map(String.init) ?? "") }) {
                continue
            }
            for cat in loc.categories {
                guard !seen.contains(cat.category), refCats.contains(cat.category) else { continue }
                if let gov = cat.allLevels.first(where: { $0.isGoverning }), let penalty = gov.penaltySummary {
                    seen.insert(cat.category)
                    results.append((
                        category: cat.category.replacingOccurrences(of: "_", with: " "),
                        summary: penalty,
                        agency: gov.enforcingAgency ?? ""
                    ))
                }
            }
        }
        return results
    }

    private var systemMessage: some View {
        Text(message.content)
            .font(.system(size: 12))
            .italic()
            .foregroundColor(.secondary)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, 4)
    }
}

// MARK: - Compliance Evidence Panel

struct ComplianceEvidencePanel: View {
    let locations: [MWComplianceReasoningLocation]
    let referencedCategories: [String]?
    let referencedLocations: [String]?
    var lightMode: Bool = false

    @State private var expanded = false
    @State private var selectedLocation = 0
    @State private var selectedCategory = 0

    private var filteredLocations: [MWComplianceReasoningLocation] {
        var filtered = locations
        if let refLocs = referencedLocations, !refLocs.isEmpty {
            let matched = locations.filter { loc in
                refLocs.contains(where: { loc.locationLabel == $0 || loc.locationLabel.contains($0) })
            }
            if !matched.isEmpty { filtered = matched }
        }
        if let refCats = referencedCategories, !refCats.isEmpty {
            let refSet = Set(refCats)
            filtered = filtered.compactMap { loc in
                let cats = loc.categories.filter { refSet.contains($0.category) }
                guard !cats.isEmpty else { return nil }
                return MWComplianceReasoningLocation(
                    locationId: loc.locationId,
                    locationLabel: loc.locationLabel,
                    facilityAttributes: loc.facilityAttributes,
                    activatedProfiles: loc.activatedProfiles,
                    categories: cats
                )
            }
        }
        return filtered.isEmpty ? locations : filtered
    }

    private var totalCategories: Int {
        filteredLocations.reduce(0) { $0 + $1.categories.count }
    }

    private var currentLocation: MWComplianceReasoningLocation? {
        guard selectedLocation < filteredLocations.count else { return nil }
        return filteredLocations[selectedLocation]
    }

    private var currentCategory: MWComplianceReasoningCategory? {
        guard let loc = currentLocation, selectedCategory < loc.categories.count else { return nil }
        return loc.categories[selectedCategory]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Collapsed summary bar
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "shield")
                        .font(.system(size: 11))
                        .foregroundColor(.cyan)
                    Text("Compliance Evidence")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(lightMode ? .primary : .white)
                    Text("— \(totalCategories) categor\(totalCategories == 1 ? "y" : "ies") across \(filteredLocations.count) location\(filteredLocations.count == 1 ? "" : "s")")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .rotationEffect(.degrees(expanded ? 180 : 0))
                }
            }
            .buttonStyle(.plain)

            if expanded {
                VStack(alignment: .leading, spacing: 8) {
                    // Location selector
                    if filteredLocations.count > 1 {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 4) {
                                ForEach(Array(filteredLocations.enumerated()), id: \.offset) { i, loc in
                                    Button {
                                        selectedLocation = i
                                        selectedCategory = 0
                                    } label: {
                                        HStack(spacing: 3) {
                                            Image(systemName: "mappin")
                                                .font(.system(size: 9))
                                            Text(loc.locationLabel)
                                                .font(.system(size: 10))
                                        }
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(i == selectedLocation ? Color.cyan.opacity(0.2) : Color.zinc800)
                                        .foregroundColor(i == selectedLocation ? .cyan : .secondary)
                                        .cornerRadius(6)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 6)
                                                .stroke(i == selectedLocation ? Color.cyan.opacity(0.4) : Color.clear, lineWidth: 1)
                                        )
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }

                    // Activated profiles
                    if let loc = currentLocation, !loc.activatedProfiles.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 4) {
                                ForEach(loc.activatedProfiles, id: \.label) { profile in
                                    Text("\(profile.label) — \(profile.categories.count) triggered")
                                        .font(.system(size: 10))
                                        .foregroundColor(.purple)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 3)
                                        .background(Color.purple.opacity(0.15))
                                        .cornerRadius(4)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 4)
                                                .stroke(Color.purple.opacity(0.3), lineWidth: 1)
                                        )
                                }
                            }
                        }
                    }

                    // Category selector
                    if let loc = currentLocation, !loc.categories.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 4) {
                                ForEach(Array(loc.categories.enumerated()), id: \.offset) { i, cat in
                                    Button {
                                        selectedCategory = i
                                    } label: {
                                        HStack(spacing: 3) {
                                            Text(cat.category.replacingOccurrences(of: "_", with: " "))
                                                .font(.system(size: 10))
                                            if let prec = cat.precedenceType {
                                                Text("(\(prec))")
                                                    .font(.system(size: 9))
                                                    .opacity(0.6)
                                            }
                                        }
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(i == selectedCategory ? Color.zinc800 : Color.zinc800.opacity(0.5))
                                        .foregroundColor(i == selectedCategory ? precedenceColor(cat.precedenceType) : .secondary)
                                        .cornerRadius(6)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 6)
                                                .stroke(i == selectedCategory ? precedenceColor(cat.precedenceType).opacity(0.5) : Color.clear, lineWidth: 1)
                                        )
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }

                    // Reasoning text
                    if let text = currentCategory?.reasoningText, !text.isEmpty {
                        Text(text)
                            .font(.system(size: 11))
                            .foregroundColor(lightMode ? .secondary : Color(white: 0.65))
                            .padding(8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(lightMode ? Color(white: 0.94) : Color.zinc800.opacity(0.5))
                            .cornerRadius(6)
                    }

                    // Data freshness
                    if let cat = currentCategory {
                        let dates = cat.allLevels.compactMap { $0.lastVerifiedAt }.compactMap { parseMWDate($0) }
                        if let latest = dates.max() {
                            HStack(spacing: 4) {
                                Text("Data last verified:")
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                                Text(latest, style: .date)
                                    .font(.system(size: 10))
                                    .foregroundColor(lightMode ? .primary : Color(white: 0.7))
                            }
                        }
                    }
                }
                .padding(.top, 8)
            }
        }
    }

    private func precedenceColor(_ type: String?) -> Color {
        switch type {
        case "floor": return .green
        case "ceiling": return .orange
        case "supersede": return .red
        case "additive": return .blue
        default: return lightMode ? .primary : .white
        }
    }
}

// MARK: - Affected Employees Panel

struct AffectedEmployeesPanel: View {
    let groups: [MWAffectedEmployeeGroup]
    var lightMode: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("AFFECTED EMPLOYEES (\(groups.reduce(0) { $0 + $1.count }))")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.secondary)
                .tracking(0.5)

            FlowLayout(spacing: 4) {
                ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                    HStack(spacing: 4) {
                        Text("\(group.count)")
                            .font(.system(size: 11, weight: .medium))
                        Text("in")
                            .font(.system(size: 11))
                            .foregroundColor(.purple.opacity(0.7))
                        Text(group.location)
                            .font(.system(size: 11))
                    }
                    .foregroundColor(.purple)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.purple.opacity(lightMode ? 0.1 : 0.15))
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.purple.opacity(lightMode ? 0.25 : 0.3), lineWidth: 1)
                    )
                }
            }
        }
    }
}

// MARK: - Policy Gaps Panel

struct PolicyGapsPanel: View {
    let gaps: [MWComplianceGap]
    var lightMode: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("POLICY GAPS (\(gaps.count))")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.orange)
                .tracking(0.5)

            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(gaps.enumerated()), id: \.offset) { _, gap in
                    HStack(spacing: 0) {
                        Text("No written policy found for ")
                            .font(.system(size: 11))
                        Text(gap.label)
                            .font(.system(size: 11, weight: .medium))
                        Text(" — required by governing jurisdiction")
                            .font(.system(size: 11))
                    }
                    .foregroundColor(lightMode ? Color.orange.opacity(0.8) : Color.orange.opacity(0.7))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.orange.opacity(lightMode ? 0.08 : 0.1))
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.orange.opacity(0.2), lineWidth: 1)
                    )
                }
            }
        }
    }
}

// MARK: - Enforcement Risk Panel

struct EnforcementRiskPanel: View {
    let penalties: [(category: String, summary: String, agency: String)]
    var lightMode: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("ENFORCEMENT RISK (\(penalties.count))")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(lightMode ? .red : .red.opacity(0.7))
                .tracking(0.5)

            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(penalties.enumerated()), id: \.offset) { _, p in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 0) {
                            Text(p.category)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(lightMode ? .red : Color.red.opacity(0.8))
                            Text(" — \(p.summary)")
                                .font(.system(size: 11))
                                .foregroundColor(lightMode ? Color.red.opacity(0.7) : Color.red.opacity(0.6))
                        }
                        if !p.agency.isEmpty {
                            Text("(\(p.agency))")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.red.opacity(lightMode ? 0.06 : 0.08))
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.red.opacity(0.15), lineWidth: 1)
                    )
                }
            }
        }
    }
}

// MARK: - Payer Sources Panel

struct PayerSourcesPanel: View {
    let sources: [MWPayerPolicySource]
    var lightMode: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("SOURCES (\(sources.count))")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.secondary)
                .tracking(0.5)

            FlowLayout(spacing: 4) {
                ForEach(Array(sources.enumerated()), id: \.offset) { _, source in
                    HStack(spacing: 4) {
                        Text(source.payerName)
                            .font(.system(size: 11))
                            .foregroundColor(.green)
                        if let num = source.policyNumber {
                            Text("|")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary.opacity(0.5))
                            Text(num)
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                        }
                        if let url = source.sourceUrl, let nsUrl = URL(string: url) {
                            Link("view", destination: nsUrl)
                                .font(.system(size: 11))
                                .foregroundColor(.green)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(lightMode ? Color(white: 0.94) : Color.zinc800)
                    .cornerRadius(4)
                }
            }
        }
    }
}

// MARK: - Flow Layout (horizontal wrap)

struct FlowLayout: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = layout(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = layout(proposal: proposal, subviews: subviews)
        for (index, offset) in result.offsets.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + offset.x, y: bounds.minY + offset.y), proposal: .unspecified)
        }
    }

    private func layout(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, offsets: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var offsets: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            offsets.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            totalHeight = y + rowHeight
        }

        return (CGSize(width: maxWidth, height: totalHeight), offsets)
    }
}

// MARK: - Streaming Bubble

struct StreamingBubbleView: View {
    let content: String

    var body: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                if content.isEmpty {
                    LoadingDots()
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(Color.zinc800)
                        .cornerRadius(12)
                } else {
                    Text(content)
                        .font(.system(size: 14))
                        .foregroundColor(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.zinc800)
                        .cornerRadius(12)
                }
            }
            Spacer(minLength: 60)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
