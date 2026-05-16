import SwiftUI

struct OnboardingPreview: View {
    let state: [String: AnyCodable]

    struct EmployeeEntry: Identifiable {
        let id = UUID()
        let firstName: String
        let lastName: String
        let name: String
        let role: String
        let workEmail: String
        let personalEmail: String
        let workState: String
        let employmentType: String
        let startDate: String
        let status: String
        let error: String
        let employeeId: String
        let provisioningResults: [String: String]

        var initials: String {
            let parts = name.split(separator: " ")
            if parts.count >= 2 {
                return "\(parts[0].prefix(1))\(parts[1].prefix(1))".uppercased()
            }
            return String(name.prefix(2)).uppercased()
        }
    }

    // MARK: - Parsed data

    var employees: [EmployeeEntry] {
        guard let raw = state["employees"]?.value as? [AnyCodable] else { return [] }
        return raw.compactMap { item -> EmployeeEntry? in
            guard let dict = item.value as? [String: AnyCodable] else { return nil }
            let firstName = (dict["first_name"]?.value as? String) ?? ""
            let lastName = (dict["last_name"]?.value as? String) ?? ""
            let composedName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
            let displayName = composedName.isEmpty
                ? (dict["name"]?.value as? String) ?? (dict["full_name"]?.value as? String) ?? ""
                : composedName
            guard !displayName.isEmpty else { return nil }
            let role = (dict["role"]?.value as? String) ?? (dict["position"]?.value as? String) ?? ""
            let workEmail = (dict["work_email"]?.value as? String) ?? ""
            let personalEmail = (dict["personal_email"]?.value as? String) ?? ""
            let workState = (dict["work_state"]?.value as? String) ?? ""
            let employmentType = (dict["employment_type"]?.value as? String) ?? ""
            let startDate = (dict["start_date"]?.value as? String) ?? ""
            let status = (dict["status"]?.value as? String) ?? "pending"
            let error = (dict["error"]?.value as? String) ?? ""
            let employeeId = (dict["employee_id"]?.value as? String) ?? ""
            var provResults: [String: String] = [:]
            if let pr = dict["provisioning_results"]?.value as? [String: AnyCodable] {
                for (k, v) in pr {
                    provResults[k] = v.value as? String ?? ""
                }
            }
            return EmployeeEntry(
                firstName: firstName, lastName: lastName, name: displayName,
                role: role, workEmail: workEmail, personalEmail: personalEmail,
                workState: workState, employmentType: employmentType, startDate: startDate,
                status: status, error: error, employeeId: employeeId,
                provisioningResults: provResults
            )
        }
    }

    // MARK: - Batch-level properties

    private var batchStatus: String { (state["batch_status"]?.value as? String) ?? "" }
    private var companyName: String { (state["company_name"]?.value as? String) ?? "" }
    private var defaultStartDate: String { (state["default_start_date"]?.value as? String) ?? "" }
    private var defaultEmploymentType: String { (state["default_employment_type"]?.value as? String) ?? "" }
    private var defaultWorkState: String { (state["default_work_state"]?.value as? String) ?? "" }

    // MARK: - Summary stats

    private var createdCount: Int {
        employees.filter {
            let status = resolvedEmployeeStatus(for: $0)
            return status == "created" || status == "done"
        }.count
    }

    private var errorCount: Int {
        employees.filter { resolvedEmployeeStatus(for: $0) == "error" }.count
    }

    private var batchStatusColor: Color {
        switch batchStatus {
        case "ready": return .orange
        case "processing": return .blue
        case "complete": return .green
        default: return .secondary
        }
    }

    private func hasProvisioningFailure(_ employee: EmployeeEntry) -> Bool {
        employee.provisioningResults.values.contains { result in
            let normalized = result.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            return normalized.contains("error")
                || normalized.contains("fail")
                || normalized.contains("needs_action")
        }
    }

    private func resolvedEmployeeStatus(for employee: EmployeeEntry) -> String {
        let status = employee.status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if status == "error" || hasProvisioningFailure(employee) {
            return "error"
        }
        return status.isEmpty ? "pending" : status
    }

    private func employeeStatusColor(_ status: String) -> Color {
        switch status {
        case "created", "done": return .green
        case "provisioning": return .blue
        case "error": return .red
        default: return .secondary
        }
    }

    // MARK: - Body

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 6) {
                    Text("Onboarding Plan")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    HStack(spacing: 8) {
                        if !batchStatus.isEmpty {
                            Text(batchStatus.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(batchStatusColor)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(batchStatusColor.opacity(0.12))
                                .cornerRadius(4)
                        }
                        if !companyName.isEmpty {
                            Text(companyName)
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                        }
                    }

                    if !employees.isEmpty {
                        HStack(spacing: 6) {
                            Text("\(employees.count) employee\(employees.count == 1 ? "" : "s")")
                                .foregroundColor(.white.opacity(0.7))
                            if createdCount > 0 {
                                Text("·")
                                    .foregroundColor(.secondary)
                                Text("\(createdCount) created")
                                    .foregroundColor(.green)
                            }
                            if errorCount > 0 {
                                Text("·")
                                    .foregroundColor(.secondary)
                                Text("\(errorCount) error\(errorCount == 1 ? "" : "s")")
                                    .foregroundColor(.red)
                            }
                        }
                        .font(.system(size: 12, weight: .medium))
                    }
                }

                // Defaults card
                if !defaultStartDate.isEmpty || !defaultEmploymentType.isEmpty || !defaultWorkState.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        if !defaultStartDate.isEmpty {
                            HStack(spacing: 6) {
                                Text("Start Date:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(defaultStartDate)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !defaultEmploymentType.isEmpty {
                            HStack(spacing: 6) {
                                Text("Employment:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(defaultEmploymentType.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                        if !defaultWorkState.isEmpty {
                            HStack(spacing: 6) {
                                Text("Work State:")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.secondary)
                                Text(defaultWorkState)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.zinc800)
                    .cornerRadius(8)
                }

                // Employee cards
                if employees.isEmpty {
                    if !batchStatus.isEmpty {
                        EmptyPreviewView(message: "Collecting employee details...", icon: "person.badge.plus")
                    } else {
                        EmptyPreviewView(message: "Describe the employees you'd like to onboard...", icon: "person.badge.plus")
                    }
                } else {
                    ForEach(employees) { employee in
                        let resolvedStatus = resolvedEmployeeStatus(for: employee)
                        VStack(alignment: .leading, spacing: 8) {
                            // Top row: avatar + name/role + status badge
                            HStack(spacing: 10) {
                                ZStack {
                                    Circle()
                                        .fill(employeeStatusColor(resolvedStatus).opacity(0.15))
                                        .frame(width: 36, height: 36)
                                    Text(employee.initials)
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundColor(employeeStatusColor(resolvedStatus))
                                }
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(employee.name)
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundColor(.white)
                                    if !employee.role.isEmpty {
                                        Text(employee.role)
                                            .font(.system(size: 12))
                                            .foregroundColor(.secondary)
                                    }
                                }
                                Spacer()
                                Text(resolvedStatus.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(employeeStatusColor(resolvedStatus))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(employeeStatusColor(resolvedStatus).opacity(0.12))
                                    .cornerRadius(4)
                            }

                            // Detail rows (indented past avatar)
                            VStack(alignment: .leading, spacing: 4) {
                                if !employee.workEmail.isEmpty {
                                    HStack(spacing: 6) {
                                        Image(systemName: "envelope.fill")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                        Text(employee.workEmail)
                                            .font(.system(size: 11))
                                            .foregroundColor(.white.opacity(0.75))
                                    }
                                }
                                if !employee.personalEmail.isEmpty {
                                    HStack(spacing: 6) {
                                        Image(systemName: "envelope")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                        Text(employee.personalEmail)
                                            .font(.system(size: 11))
                                            .foregroundColor(.white.opacity(0.6))
                                    }
                                }
                                if !employee.employmentType.isEmpty || !employee.workState.isEmpty {
                                    HStack(spacing: 6) {
                                        if !employee.employmentType.isEmpty {
                                            Text(employee.employmentType.replacingOccurrences(of: "_", with: " ").capitalized)
                                                .font(.system(size: 10, weight: .medium))
                                                .foregroundColor(.purple)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(Color.purple.opacity(0.12))
                                                .cornerRadius(3)
                                        }
                                        if !employee.workState.isEmpty {
                                            Text(employee.workState)
                                                .font(.system(size: 10, weight: .medium))
                                                .foregroundColor(.blue)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(Color.blue.opacity(0.12))
                                                .cornerRadius(3)
                                        }
                                    }
                                }
                                if !employee.startDate.isEmpty {
                                    HStack(spacing: 6) {
                                        Image(systemName: "calendar")
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                        Text("Starts \(employee.startDate)")
                                            .font(.system(size: 11))
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding(.leading, 46)

                            // Error banner
                            if resolvedStatus == "error" && !employee.error.isEmpty {
                                HStack(spacing: 6) {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .font(.system(size: 11))
                                        .foregroundColor(.red)
                                    Text(employee.error)
                                        .font(.system(size: 11))
                                        .foregroundColor(.red)
                                        .lineLimit(3)
                                }
                                .padding(8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.red.opacity(0.1))
                                .cornerRadius(6)
                            }

                            // Provisioning results
                            if !employee.provisioningResults.isEmpty {
                                HStack(spacing: 12) {
                                    ForEach(Array(employee.provisioningResults.sorted(by: { $0.key < $1.key })), id: \.key) { service, result in
                                        HStack(spacing: 4) {
                                            Image(systemName: provisioningIcon(for: service))
                                                .font(.system(size: 10))
                                                .foregroundColor(provisioningColor(for: result))
                                            Text("\(provisioningLabel(for: service)): \(result)")
                                                .font(.system(size: 10))
                                                .foregroundColor(provisioningColor(for: result))
                                        }
                                    }
                                }
                                .padding(.leading, 46)
                            }
                        }
                        .padding(12)
                        .background(Color.zinc800)
                        .cornerRadius(8)
                    }
                }
            }
            .padding(20)
        }
    }

    // MARK: - Provisioning helpers

    private func provisioningIcon(for service: String) -> String {
        switch service {
        case "google_workspace": return "envelope.badge.person.crop"
        case "slack": return "number"
        default: return "gearshape"
        }
    }

    private func provisioningLabel(for service: String) -> String {
        switch service {
        case "google_workspace": return "Google"
        case "slack": return "Slack"
        default: return service.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func provisioningColor(for result: String) -> Color {
        if result.contains("error") || result.contains("fail") { return .red }
        return .green
    }
}
