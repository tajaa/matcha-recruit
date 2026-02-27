import SwiftUI

struct NewThreadView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @Bindable var viewModel: ThreadListViewModel
    @State private var selectedTaskType = "offer_letter"
    @State private var title = ""
    @State private var initialMessage = ""
    @State private var isCreating = false

    struct TaskTypeOption {
        let id: String
        let label: String
        let icon: String
        let description: String
    }

    let taskTypes: [TaskTypeOption] = [
        TaskTypeOption(id: "offer_letter", label: "Offer Letter", icon: "doc.text.fill", description: "Generate offer letters for candidates"),
        TaskTypeOption(id: "review", label: "Performance Review", icon: "star.fill", description: "Create structured performance reviews"),
        TaskTypeOption(id: "workbook", label: "Workbook", icon: "book.fill", description: "Build onboarding or training workbooks"),
        TaskTypeOption(id: "onboarding", label: "Onboarding", icon: "person.badge.plus.fill", description: "Manage employee onboarding")
    ]

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
                    // Task type
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Type")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)

                        ForEach(taskTypes, id: \.id) { option in
                            Button {
                                selectedTaskType = option.id
                            } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: option.icon)
                                        .font(.system(size: 16))
                                        .foregroundColor(selectedTaskType == option.id ? .matcha500 : .secondary)
                                        .frame(width: 28)

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(option.label)
                                            .font(.system(size: 13, weight: .medium))
                                            .foregroundColor(.white)
                                        Text(option.description)
                                            .font(.system(size: 11))
                                            .foregroundColor(.secondary)
                                    }

                                    Spacer()

                                    if selectedTaskType == option.id {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundColor(.matcha500)
                                    }
                                }
                                .padding(10)
                                .background(selectedTaskType == option.id ? Color.matcha600.opacity(0.15) : Color.zinc800)
                                .cornerRadius(8)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(selectedTaskType == option.id ? Color.matcha500.opacity(0.5) : Color.clear, lineWidth: 1)
                                )
                            }
                            .buttonStyle(.plain)
                        }
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

            // Footer buttons
            HStack {
                Button("Cancel") { dismiss() }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)

                Spacer()

                Button {
                    Task {
                        isCreating = true
                        let newTitle = title.isEmpty ? nil : title
                        let msg = initialMessage.isEmpty ? nil : initialMessage
                        if let thread = await viewModel.createThread(
                            title: newTitle,
                            taskType: selectedTaskType,
                            initialMessage: msg
                        ) {
                            await MainActor.run {
                                appState.selectedThreadId = thread.id
                                dismiss()
                            }
                        }
                        isCreating = false
                    }
                } label: {
                    if isCreating {
                        ProgressView().controlSize(.small).tint(.white)
                    } else {
                        Text("Create")
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
            .padding(20)
        }
        .background(Color.zinc900)
        .frame(width: 480)
    }
}
