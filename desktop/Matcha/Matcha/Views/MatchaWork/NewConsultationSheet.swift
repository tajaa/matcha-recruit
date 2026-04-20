import SwiftUI

struct NewConsultationSheet: View {
    let onCreated: (MWProject) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var clientName = ""
    @State private var org = ""
    @State private var contactName = ""
    @State private var contactEmail = ""
    @State private var contactPhone = ""
    @State private var stage = "active"
    @State private var pricingModel = "hourly"
    @State private var rateDollars = ""
    @State private var retainerDollars = ""
    @State private var fixedFeeDollars = ""
    @State private var tagsRaw = ""
    @State private var startDate = Date()
    @State private var hasStartDate = false

    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private let stages = ["lead", "proposal", "active"]
    private let pricingModels = ["hourly", "retainer", "fixed", "free"]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("new consultation")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))

            field(label: "client name", text: $clientName, placeholder: "Jane Doe")
            field(label: "organization (optional)", text: $org, placeholder: "Acme Corp")

            VStack(alignment: .leading, spacing: 4) {
                Text("primary contact").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                HStack(spacing: 6) {
                    TextField("", text: $contactName, prompt: Text("name").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(.white.opacity(0.9))
                    TextField("", text: $contactEmail, prompt: Text("email").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(.white.opacity(0.9))
                    TextField("", text: $contactPhone, prompt: Text("phone").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(.white.opacity(0.9))
                }
                Divider()
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("stage").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                HStack(spacing: 16) {
                    ForEach(stages, id: \.self) { s in
                        chipButton(label: s, selected: stage == s) { stage = s }
                    }
                    Spacer()
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("pricing").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                HStack(spacing: 16) {
                    ForEach(pricingModels, id: \.self) { p in
                        chipButton(label: p, selected: pricingModel == p) { pricingModel = p }
                    }
                    Spacer()
                }
                switch pricingModel {
                case "hourly":
                    dollarField(label: "rate ($/hr)", text: $rateDollars, placeholder: "200")
                case "retainer":
                    dollarField(label: "monthly retainer ($)", text: $retainerDollars, placeholder: "5000")
                case "fixed":
                    dollarField(label: "project fee ($)", text: $fixedFeeDollars, placeholder: "10000")
                default:
                    EmptyView()
                }
            }

            field(label: "tags (comma-separated, optional)", text: $tagsRaw, placeholder: "retainer, q2")

            VStack(alignment: .leading, spacing: 4) {
                Toggle(isOn: $hasStartDate) {
                    Text("set start date")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.7))
                }
                .toggleStyle(.switch)
                .controlSize(.small)
                if hasStartDate {
                    DatePicker("", selection: $startDate, displayedComponents: .date)
                        .labelsHidden()
                        .font(.system(size: 12))
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.red.opacity(0.8))
            }

            HStack {
                Button { dismiss() } label: {
                    Text("cancel").font(.system(size: 12)).foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button { Task { await submit() } } label: {
                    if isSubmitting {
                        Text("creating…").font(.system(size: 12)).foregroundColor(.white.opacity(0.4))
                    } else {
                        Text("create")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(
                                clientName.trimmingCharacters(in: .whitespaces).isEmpty
                                    ? .white.opacity(0.25)
                                    : Color.matcha500
                            )
                    }
                }
                .buttonStyle(.plain)
                .disabled(clientName.trimmingCharacters(in: .whitespaces).isEmpty || isSubmitting)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(20)
        .frame(width: 460)
        .background(Color.appBackground)
    }

    private func field(label: String, text: Binding<String>, placeholder: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
            TextField("", text: text, prompt: Text(placeholder).foregroundColor(.white.opacity(0.25)))
                .textFieldStyle(.plain).font(.system(size: 13)).foregroundColor(.white.opacity(0.9))
            Divider()
        }
    }

    private func dollarField(label: String, text: Binding<String>, placeholder: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
            HStack(spacing: 4) {
                Text("$").font(.system(size: 13)).foregroundColor(.white.opacity(0.5))
                TextField("", text: text, prompt: Text(placeholder).foregroundColor(.white.opacity(0.25)))
                    .textFieldStyle(.plain).font(.system(size: 13)).foregroundColor(.white.opacity(0.9))
            }
            Divider()
        }
    }

    private func chipButton(label: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 2) {
                Text(label)
                    .font(.system(size: 11))
                    .foregroundColor(selected ? Color.matcha500 : .white.opacity(0.5))
                Rectangle()
                    .fill(selected ? Color.matcha500 : Color.clear)
                    .frame(height: 1)
            }
        }
        .buttonStyle(.plain)
    }

    private func submit() async {
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }

        let name = clientName.trimmingCharacters(in: .whitespaces)
        let primaryContact = MWConsultationContact(
            name: contactName.isEmpty ? nil : contactName,
            email: contactEmail.isEmpty ? nil : contactEmail,
            phone: contactPhone.isEmpty ? nil : contactPhone,
            role: nil
        )
        let client = MWConsultationClient(
            name: name,
            org: org.isEmpty ? nil : org,
            website: nil,
            avatarUrl: nil,
            primaryContact: (contactName.isEmpty && contactEmail.isEmpty && contactPhone.isEmpty) ? nil : primaryContact,
            additionalContacts: nil
        )
        let rateCents = Int((Double(rateDollars.trimmingCharacters(in: .whitespaces)) ?? 0) * 100)
        let retainerCents = Int((Double(retainerDollars.trimmingCharacters(in: .whitespaces)) ?? 0) * 100)
        let fixedCents = Int((Double(fixedFeeDollars.trimmingCharacters(in: .whitespaces)) ?? 0) * 100)
        let startIso: String? = {
            guard hasStartDate else { return nil }
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withFullDate]
            return f.string(from: startDate)
        }()
        let engagement = MWEngagement(
            startDate: startIso,
            endDate: nil,
            pricingModel: pricingModel,
            rateCentsPerHour: (pricingModel == "hourly" && rateCents > 0) ? rateCents : nil,
            monthlyRetainerCents: (pricingModel == "retainer" && retainerCents > 0) ? retainerCents : nil,
            fixedFeeCents: (pricingModel == "fixed" && fixedCents > 0) ? fixedCents : nil,
            sowUrl: nil,
            contractSignedAt: nil
        )
        let tags = tagsRaw.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }

        do {
            var project = try await MatchaWorkService.shared.createConsultation(
                title: name, clientProfile: client, engagement: engagement, tags: tags
            )
            // Apply stage if non-default
            if stage != "active" {
                project = try await MatchaWorkService.shared.patchConsultation(id: project.id, stage: stage)
            }
            onCreated(project)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
