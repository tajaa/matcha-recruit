import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// Sticky header bar for Discipline projects driving the meeting →
/// signature → close workflow. Shown above the standard project
/// layout when projectType == "discipline".
struct DisciplineWorkflowBar: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var showRefuseDialog = false
    @State private var refusalNotes = ""
    @State private var showEmailPrompt = false
    @State private var employeeEmail = ""
    @State private var workingState: String? = nil
    @State private var alertMessage: String? = nil

    var body: some View {
        let pdata = viewModel.project?.projectData
        let meetingHeldAt = (pdata?["meeting_held_at"]?.value as? String)
        let draftStatus = (pdata?["draft_status"]?.value as? String) ?? "drafting"
        let signature = (pdata?["signature"]?.value as? [String: AnyCodable]) ?? [:]
        let employeeBlock = (pdata?["employee"]?.value as? [String: AnyCodable]) ?? [:]
        let prefilledEmail = (employeeBlock["employee_email"]?.value as? String) ?? ""
        let level = (pdata?["level"]?.value as? String) ?? "(level not set)"

        VStack(spacing: 8) {
            HStack {
                Image(systemName: "exclamationmark.shield")
                    .foregroundColor(.orange)
                Text("Disciplinary Action")
                    .font(.system(size: 13, weight: .semibold))
                Text(prettyLevel(level))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.orange.opacity(0.15))
                    .cornerRadius(4)
                Spacer()
                statusChip(draftStatus, signature: signature)
            }

            HStack(spacing: 8) {
                if draftStatus == "signed" || draftStatus == "physically_signed" || draftStatus == "refused" {
                    Text(closedSummary(draftStatus, signature: signature))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                } else if meetingHeldAt == nil {
                    Button {
                        Task {
                            workingState = "meeting"
                            await viewModel.confirmDisciplineMeetingHeld()
                            workingState = nil
                        }
                    } label: {
                        Label("Confirm meeting was held", systemImage: "checkmark.circle")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(workingState != nil)
                    Text("Required before sending for signature.")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                } else if draftStatus == "pending_signature" {
                    Text("Awaiting signature from \(signature["recipient_email"]?.value as? String ?? "employee")")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                } else {
                    Button {
                        employeeEmail = prefilledEmail
                        showEmailPrompt = true
                    } label: {
                        Label("Send digitally", systemImage: "paperplane")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(workingState != nil)

                    Button {
                        showRefuseDialog = true
                    } label: {
                        Label("Mark as refused", systemImage: "xmark.circle")
                    }
                    .disabled(workingState != nil)

                    Button {
                        Task { await downloadPdfForPhysicalSigning() }
                    } label: {
                        Label("Download PDF", systemImage: "arrow.down.doc")
                    }
                    .disabled(workingState != nil)

                    Button {
                        Task { await uploadSignedScan() }
                    } label: {
                        Label("Upload signed scan", systemImage: "arrow.up.doc")
                    }
                    .disabled(workingState != nil)
                }
                Spacer()
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.zinc900.opacity(0.4))
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundColor(.secondary.opacity(0.2))
            , alignment: .bottom
        )
        .sheet(isPresented: $showRefuseDialog) {
            RefuseSheet(notes: $refusalNotes) {
                Task {
                    workingState = "refuse"
                    await viewModel.refuseDisciplineSignature(notes: refusalNotes)
                    refusalNotes = ""
                    showRefuseDialog = false
                    workingState = nil
                }
            }
        }
        .sheet(isPresented: $showEmailPrompt) {
            EmailPromptSheet(email: $employeeEmail) {
                Task {
                    workingState = "send"
                    await viewModel.requestDisciplineSignature(employeeEmail: employeeEmail)
                    showEmailPrompt = false
                    workingState = nil
                }
            }
        }
        .alert("Discipline workflow", isPresented: Binding(
            get: { alertMessage != nil },
            set: { if !$0 { alertMessage = nil } },
        )) {
            Button("OK") { alertMessage = nil }
        } message: {
            Text(alertMessage ?? "")
        }
    }

    @MainActor
    private func downloadPdfForPhysicalSigning() async {
        guard let data = await viewModel.exportProject(format: "pdf") else {
            alertMessage = viewModel.errorMessage ?? "Couldn't render PDF."
            return
        }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "\(viewModel.project?.title ?? "discipline").pdf"
        panel.allowedContentTypes = [.pdf]
        let window = NSApp.keyWindow ?? NSApp.mainWindow
        let handler: (NSApplication.ModalResponse) -> Void = { response in
            guard response == .OK, let url = panel.url else { return }
            do { try data.write(to: url) } catch {
                alertMessage = error.localizedDescription
            }
        }
        if let window {
            panel.beginSheetModal(for: window, completionHandler: handler)
        } else {
            panel.begin(completionHandler: handler)
        }
    }

    @MainActor
    private func uploadSignedScan() async {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.pdf]
        if panel.runModal() == .OK, let url = panel.url {
            workingState = "upload"
            await viewModel.uploadDisciplinePhysicalSignature(fileURL: url)
            workingState = nil
        }
    }

    private func prettyLevel(_ level: String) -> String {
        switch level {
        case "verbal_warning": return "Verbal Warning"
        case "written_warning": return "Written Warning"
        case "final_warning": return "Final Written Warning"
        case "termination_notice": return "Termination Notice"
        default: return "Pick a level"
        }
    }

    @ViewBuilder
    private func statusChip(_ draftStatus: String, signature: [String: AnyCodable]) -> some View {
        let (label, color) = chipStyle(draftStatus)
        Text(label)
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .cornerRadius(4)
    }

    private func chipStyle(_ s: String) -> (String, Color) {
        switch s {
        case "drafting":           return ("Draft", .secondary)
        case "pending_signature":  return ("Awaiting Signature", .orange)
        case "signed":             return ("Signed", .green)
        case "physically_signed":  return ("Physically Signed", .green)
        case "refused":            return ("Refused", .red)
        default:                   return (s.capitalized, .secondary)
        }
    }

    private func closedSummary(_ s: String, signature: [String: AnyCodable]) -> String {
        switch s {
        case "signed": return "Signed digitally on \(formatDate(signature["signed_at"]?.value as? String))."
        case "physically_signed": return "Physical signature uploaded on \(formatDate(signature["signed_at"]?.value as? String))."
        case "refused": return "Employee refused to sign on \(formatDate(signature["refused_at"]?.value as? String))."
        default: return ""
        }
    }

    private func formatDate(_ iso: String?) -> String {
        guard let iso, let date = ISO8601DateFormatter().date(from: iso) else { return iso ?? "(unknown)" }
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f.string(from: date)
    }
}


// MARK: - Sheets

private struct RefuseSheet: View {
    @Binding var notes: String
    var onConfirm: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Mark as Refused")
                .font(.system(size: 14, weight: .semibold))
            Text("Document why the employee refused to sign. The warning still counts; this just closes the project.")
                .font(.system(size: 12))
                .foregroundColor(.secondary)
            TextEditor(text: $notes)
                .frame(height: 100)
                .border(Color.secondary.opacity(0.3))
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Confirm refusal") { onConfirm() }
                    .buttonStyle(.borderedProminent)
                    .disabled(notes.trimmingCharacters(in: .whitespaces).count < 20)
            }
        }
        .padding(20)
        .frame(width: 480)
    }
}

private struct EmailPromptSheet: View {
    @Binding var email: String
    var onSend: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Send for digital signature")
                .font(.system(size: 14, weight: .semibold))
            Text("The employee will receive an email asking them to review and sign this document.")
                .font(.system(size: 12))
                .foregroundColor(.secondary)
            TextField("employee@example.com", text: $email)
                .textFieldStyle(.roundedBorder)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Send") { onSend() }
                    .buttonStyle(.borderedProminent)
                    .disabled(!email.contains("@"))
            }
        }
        .padding(20)
        .frame(width: 480)
    }
}
