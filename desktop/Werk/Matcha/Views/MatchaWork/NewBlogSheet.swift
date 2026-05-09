import SwiftUI

struct NewBlogSheet: View {
    var onCreate: (MWProject) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var audience = ""
    @State private var tone = "expert-casual"
    @State private var isCreating = false
    @State private var error: String?

    private let tones = ["expert-casual", "technical", "exec-brief", "conversational", "academic"]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("New Blog Post").font(.system(size: 14, weight: .semibold)).foregroundColor(.white)

            VStack(alignment: .leading, spacing: 4) {
                Text("Title").font(.system(size: 11, weight: .medium)).foregroundColor(.secondary)
                TextField("Working title…", text: $title)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white)
                    .padding(8)
                    .background(Color.zinc800)
                    .cornerRadius(6)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Audience").font(.system(size: 11, weight: .medium)).foregroundColor(.secondary)
                TextField("e.g. senior engineers, HR leaders…", text: $audience)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white)
                    .padding(8)
                    .background(Color.zinc800)
                    .cornerRadius(6)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Tone").font(.system(size: 11, weight: .medium)).foregroundColor(.secondary)
                Picker("", selection: $tone) {
                    ForEach(tones, id: \.self) { t in
                        Text(t).tag(t)
                    }
                }
                .pickerStyle(.menu)
                .labelsHidden()
            }

            if let err = error {
                Text(err).font(.system(size: 11)).foregroundColor(.red)
            }

            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                    .font(.system(size: 13))
                Button("Create") { create() }
                    .buttonStyle(.borderedProminent)
                    .tint(.matcha600)
                    .font(.system(size: 13))
                    .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty || isCreating)
            }
        }
        .padding(20)
        .frame(width: 340)
        .background(Color.appBackground)
    }

    private func create() {
        isCreating = true
        error = nil
        Task {
            do {
                let proj = try await MatchaWorkService.shared.createBlog(
                    title: title.trimmingCharacters(in: .whitespaces),
                    audience: audience.trimmingCharacters(in: .whitespaces),
                    tone: tone
                )
                await MainActor.run {
                    isCreating = false
                    onCreate(proj)
                    dismiss()
                }
            } catch {
                await MainActor.run {
                    self.error = error.localizedDescription
                    isCreating = false
                }
            }
        }
    }
}
