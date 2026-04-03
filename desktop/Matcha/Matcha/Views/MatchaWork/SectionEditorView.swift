import SwiftUI

struct SectionEditorView: View {
    let section: MWProjectSection
    let onSave: (String?, String?) -> Void

    @State private var title: String = ""
    @State private var content: String = ""
    @State private var saveTimer: Timer?
    @State private var isSaved = false

    var body: some View {
        VStack(spacing: 0) {
            // Title
            TextField("Section title", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 24)
                .padding(.top, 20)
                .padding(.bottom, 8)
                .onChange(of: title) { scheduleSave() }

            Divider().opacity(0.2).padding(.horizontal, 20)

            // Content editor
            TextEditor(text: $content)
                .font(.system(size: 14))
                .foregroundColor(.white)
                .scrollContentBackground(.hidden)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .onChange(of: content) { scheduleSave() }

            // Toolbar
            HStack(spacing: 12) {
                Text("Markdown supported")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Spacer()
                if isSaved {
                    Text("Saved")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(.matcha500)
                        .transition(.opacity)
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 8)
            .background(Color.zinc800.opacity(0.3))
        }
        .background(Color(white: 0.11))
        .onAppear {
            title = section.title
            content = section.content ?? ""
        }
        .onChange(of: section.id) {
            title = section.title
            content = section.content ?? ""
            isSaved = false
        }
    }

    private func scheduleSave() {
        isSaved = false
        saveTimer?.invalidate()
        saveTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: false) { _ in
            let t = title.isEmpty ? nil : title
            let c = content
            onSave(t, c)
            Task { @MainActor in
                withAnimation { isSaved = true }
                try? await Task.sleep(for: .seconds(2))
                withAnimation { isSaved = false }
            }
        }
    }
}
