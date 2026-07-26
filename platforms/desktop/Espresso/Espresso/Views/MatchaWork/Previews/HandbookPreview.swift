import SwiftUI

struct HandbookPreview: View {
    let state: [String: AnyCodable]

    private var title: String { (state["handbook_title"]?.value as? String) ?? "Employee Handbook" }
    private var status: String { (state["handbook_status"]?.value as? String) ?? "collecting" }
    private var mode: String { (state["handbook_mode"]?.value as? String) ?? "" }
    private var industry: String { (state["handbook_industry"]?.value as? String) ?? "" }
    private var subIndustry: String { (state["handbook_sub_industry"]?.value as? String) ?? "" }
    private var legalName: String { (state["handbook_legal_name"]?.value as? String) ?? "" }
    private var dba: String { (state["handbook_dba"]?.value as? String) ?? "" }
    private var ceo: String { (state["handbook_ceo"]?.value as? String) ?? "" }
    private var headcount: Int? {
        if let v = state["handbook_headcount"]?.value as? Int { return v }
        if let v = state["handbook_headcount"]?.value as? Double { return Int(v) }
        return nil
    }
    private var errorMessage: String { (state["handbook_error"]?.value as? String) ?? "" }
    private var strengthScore: Int? {
        if let v = state["handbook_strength_score"]?.value as? Int { return v }
        if let v = state["handbook_strength_score"]?.value as? Double { return Int(v) }
        return nil
    }
    private var strengthLabel: String { (state["handbook_strength_label"]?.value as? String) ?? "" }

    private var states: [String] {
        (state["handbook_states"]?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? []
    }

    private var profileFlags: [(String, Bool)] {
        guard let raw = state["handbook_profile"]?.value as? [String: AnyCodable] else { return [] }
        let labels: [(String, String)] = [
            ("remote_workers", "Remote Workers"),
            ("minors", "Minors"),
            ("tipped_employees", "Tipped Employees"),
            ("tip_pooling", "Tip Pooling"),
            ("union_employees", "Union Employees"),
            ("federal_contracts", "Federal Contracts"),
            ("group_health_insurance", "Group Health Insurance"),
            ("background_checks", "Background Checks"),
            ("hourly_employees", "Hourly Employees"),
            ("salaried_employees", "Salaried Employees"),
            ("commissioned_employees", "Commissioned Employees"),
        ]
        return labels.compactMap { key, label in
            guard let val = raw[key]?.value as? Bool else { return nil }
            return (label, val)
        }
    }

    private var sections: [(key: String, title: String, content: String, type: String)] {
        guard let raw = state["handbook_sections"]?.value as? [AnyCodable] else { return [] }
        return raw.compactMap { item in
            guard let dict = item.value as? [String: AnyCodable] else { return nil }
            let key = (dict["section_key"]?.value as? String) ?? ""
            let title = (dict["title"]?.value as? String) ?? ""
            let content = (dict["content"]?.value as? String) ?? ""
            let type = (dict["section_type"]?.value as? String) ?? ""
            return (key, title, content, type)
        }
    }

    private var requiredFieldsFilled: Int {
        var count = 0
        if !title.isEmpty && title != "Employee Handbook" { count += 1 }
        if !states.isEmpty { count += 1 }
        if !legalName.isEmpty { count += 1 }
        if !ceo.isEmpty { count += 1 }
        return count
    }

    private var statusColor: Color {
        switch status {
        case "created": return .green
        case "generating": return .orange
        case "error": return .red
        case "ready": return .blue
        default: return .secondary
        }
    }

    private var scoreColor: Color {
        guard let score = strengthScore else { return .secondary }
        if score >= 80 { return .green }
        if score >= 50 { return .orange }
        return .red
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    HStack(spacing: 8) {
                        if !mode.isEmpty {
                            Text(mode == "multi_state" ? "Multi-State" : "Single State")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.white.opacity(0.7))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.zinc800)
                                .cornerRadius(4)
                        }
                        Text(status.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(statusColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(statusColor.opacity(0.12))
                            .cornerRadius(4)
                    }
                }

                // Error banner
                if !errorMessage.isEmpty {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red)
                            .font(.system(size: 12))
                        Text(errorMessage)
                            .font(.system(size: 12))
                            .foregroundColor(.red)
                            .lineLimit(3)
                    }
                    .padding(10)
                    .background(Color.red.opacity(0.1))
                    .cornerRadius(8)
                }

                // States
                if !states.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "map.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        ForEach(states, id: \.self) { st in
                            Text(st)
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.blue.opacity(0.2))
                                .cornerRadius(4)
                        }
                    }
                }

                // Industry
                if !industry.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "building.2.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Text(industry.capitalized)
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.85))
                        if !subIndustry.isEmpty {
                            Text("(\(subIndustry))")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                        }
                    }
                }

                // Company info
                if !legalName.isEmpty || !ceo.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        if !legalName.isEmpty {
                            HStack(spacing: 6) {
                                Text("Legal Name:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(legalName)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !dba.isEmpty {
                            HStack(spacing: 6) {
                                Text("DBA:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(dba)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !ceo.isEmpty {
                            HStack(spacing: 6) {
                                Text("CEO:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(ceo)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if let hc = headcount {
                            HStack(spacing: 6) {
                                Text("Headcount:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text("\(hc)")
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Profile flags
                if !profileFlags.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Company Profile")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white)

                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                            ForEach(profileFlags, id: \.0) { label, enabled in
                                HStack(spacing: 6) {
                                    Image(systemName: enabled ? "checkmark.circle.fill" : "xmark.circle")
                                        .font(.system(size: 11))
                                        .foregroundColor(enabled ? .green : .secondary.opacity(0.5))
                                    Text(label)
                                        .font(.system(size: 11))
                                        .foregroundColor(enabled ? .white.opacity(0.85) : .secondary.opacity(0.6))
                                    Spacer()
                                }
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Progress (before generation)
                if status != "created" && status != "error" {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Required Fields (\(requiredFieldsFilled)/4)")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)

                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.zinc800)
                                    .frame(height: 6)
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(requiredFieldsFilled == 4 ? Color.green : Color.matcha500)
                                    .frame(width: geo.size.width * CGFloat(requiredFieldsFilled) / 4.0, height: 6)
                            }
                        }
                        .frame(height: 6)
                    }
                }

                // Strength score (after creation)
                if let score = strengthScore {
                    HStack(spacing: 10) {
                        ZStack {
                            Circle()
                                .stroke(scoreColor.opacity(0.2), lineWidth: 4)
                                .frame(width: 44, height: 44)
                            Circle()
                                .trim(from: 0, to: CGFloat(score) / 100.0)
                                .stroke(scoreColor, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                                .frame(width: 44, height: 44)
                                .rotationEffect(.degrees(-90))
                            Text("\(score)")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(scoreColor)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Coverage Score")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                            Text(strengthLabel)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(scoreColor)
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Sections (after creation)
                if !sections.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("\(sections.count) Sections")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white)

                        ForEach(sections, id: \.key) { section in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(section.title)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundColor(.white)
                                if !section.content.isEmpty {
                                    Text(section.content)
                                        .font(.system(size: 12))
                                        .foregroundColor(.white.opacity(0.6))
                                        .lineLimit(3)
                                        .lineSpacing(2)
                                }
                            }
                            .padding(10)
                            .background(Color.zinc800)
                            .cornerRadius(6)
                        }
                    }
                }

                if state.isEmpty {
                    EmptyPreviewView(message: "Handbook in progress...", icon: "book.closed")
                }
            }
            .padding(20)
        }
    }
}
