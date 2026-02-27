import SwiftUI

struct NewThreadView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @Bindable var viewModel: ThreadListViewModel
    @State private var title = ""
    @State private var initialMessage = ""
    @State private var isCreating = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("New Chat")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                        .frame(width: 24, height: 24)
                        .background(Color.zinc800)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
            .padding(20)

            Divider().opacity(0.3)

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Skills info — informational only
                    VStack(alignment: .leading, spacing: 8) {
                        Text("What I can help with")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)

                        VStack(alignment: .leading, spacing: 8) {
                            SkillRow(icon: "doc.text.fill",        label: "Offer Letters",        description: "Draft, refine, and send offer letters to candidates")
                            SkillRow(icon: "star.fill",            label: "Performance Reviews",   description: "Create structured, anonymized performance reviews")
                            SkillRow(icon: "book.fill",            label: "Workbooks",             description: "Build onboarding or training workbooks")
                            SkillRow(icon: "person.badge.plus.fill", label: "Onboarding",          description: "Manage employee onboarding flows")
                        }
                        .padding(12)
                        .background(Color.zinc800)
                        .cornerRadius(8)

                        Text("Just describe what you need — I'll figure out the rest.")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }

                    // Optional title
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Title (optional)")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)
                        TextField("e.g. Software Engineer offer for Jane", text: $title)
                            .textFieldStyle(.plain)
                            .font(.system(size: 13))
                            .foregroundColor(.white)
                            .padding(10)
                            .background(Color.zinc950)
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(Color.borderColor, lineWidth: 1)
                            )
                    }

                    // Optional first message
                    VStack(alignment: .leading, spacing: 6) {
                        Text("First message (optional)")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)
                        TextField("Describe what you need...", text: $initialMessage, axis: .vertical)
                            .textFieldStyle(.plain)
                            .font(.system(size: 13))
                            .foregroundColor(.white)
                            .lineLimit(3...6)
                            .padding(10)
                            .background(Color.zinc950)
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(Color.borderColor, lineWidth: 1)
                            )
                    }
                }
                .padding(20)
            }

            Divider().opacity(0.3)

            VStack(spacing: 8) {
                if let err = errorMessage {
                    Text(err)
                        .font(.system(size: 12))
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 20)
                        .padding(.top, 8)
                }
                HStack {
                    Button("Cancel") { dismiss() }
                        .buttonStyle(.plain)
                        .foregroundColor(.secondary)

                    Spacer()

                    Button {
                        Task {
                            isCreating = true
                            errorMessage = nil
                            let newTitle = title.isEmpty ? nil : title
                            let msg = initialMessage.isEmpty ? nil : initialMessage
                            // Pass a default task_type; backend detects the real type from the message
                            if let thread = await viewModel.createThread(
                                title: newTitle,
                                taskType: "offer_letter",
                                initialMessage: msg
                            ) {
                                await MainActor.run {
                                    appState.selectedThreadId = thread.id
                                    dismiss()
                                }
                            } else {
                                errorMessage = viewModel.errorMessage ?? "Failed to create thread. Is the server running?"
                            }
                            isCreating = false
                        }
                    } label: {
                        if isCreating {
                            ProgressView().controlSize(.small).tint(.white)
                        } else {
                            Text("Start")
                                .font(.system(size: 13, weight: .semibold))
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 7)
                    .background(Color.matcha600)
                    .foregroundColor(.white)
                    .cornerRadius(8)
                    .disabled(isCreating)
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 20)
            }
        }
        .background(Color.zinc900)
        .frame(width: 480)
    }
}

private struct SkillRow: View {
    let icon: String
    let label: String
    let description: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13))
                .foregroundColor(.matcha500)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 1) {
                Text(label)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white)
                Text(description)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
        }
    }
}
