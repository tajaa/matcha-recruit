import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ProfileSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState

    @State private var name: String = ""
    @State private var phone: String = ""
    @State private var avatarUrl: String?
    @State private var avatarImage: NSImage?
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var isUploadingAvatar = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("profile")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))

            if isLoading {
                HStack { Spacer(); ProgressView().controlSize(.small); Spacer() }
                    .frame(height: 180)
            } else {
                HStack(alignment: .top, spacing: 16) {
                    avatarSection
                    VStack(alignment: .leading, spacing: 14) {
                        field(label: "name", text: $name, placeholder: "your name")
                        field(label: "phone", text: $phone, placeholder: "optional")
                        VStack(alignment: .leading, spacing: 4) {
                            Text("email")
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.4))
                            Text(appState.currentUser?.email ?? "")
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.55))
                        }
                    }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 10))
                    .foregroundColor(.red.opacity(0.8))
            }

            HStack {
                Button { dismiss() } label: {
                    Text("cancel")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    Task { await save() }
                } label: {
                    Text(isSaving ? "saving…" : "save")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(isSaving ? .white.opacity(0.35) : Color.matcha500)
                }
                .buttonStyle(.plain)
                .disabled(isSaving || isLoading)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(20)
        .frame(width: 440)
        .background(.ultraThinMaterial)
        .task { await load() }
    }

    private var avatarSection: some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .fill(Color.white.opacity(0.05))
                    .frame(width: 88, height: 88)
                if let avatarImage {
                    Image(nsImage: avatarImage)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 88, height: 88)
                        .clipShape(Circle())
                } else if let avatarUrl, let url = URL(string: avatarUrl) {
                    AsyncImage(url: url) { image in
                        image.resizable().scaledToFill()
                    } placeholder: {
                        Text(initials)
                            .font(.system(size: 22, weight: .medium))
                            .foregroundColor(.white.opacity(0.55))
                    }
                    .frame(width: 88, height: 88)
                    .clipShape(Circle())
                } else {
                    Text(initials)
                        .font(.system(size: 22, weight: .medium))
                        .foregroundColor(.white.opacity(0.55))
                }
                if isUploadingAvatar {
                    Circle()
                        .fill(Color.black.opacity(0.55))
                        .frame(width: 88, height: 88)
                    ProgressView().controlSize(.small)
                }
            }
            Button { pickAvatar() } label: {
                Text(avatarUrl != nil || avatarImage != nil ? "change" : "add photo")
                    .font(.system(size: 10))
                    .foregroundColor(Color.matcha500)
            }
            .buttonStyle(.plain)
            .disabled(isUploadingAvatar)
        }
    }

    private func field(label: String, text: Binding<String>, placeholder: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.4))
            TextField("", text: text, prompt: Text(placeholder).foregroundColor(.white.opacity(0.25)))
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.9))
            Divider()
        }
    }

    private var initials: String {
        let source = !name.isEmpty ? name : (appState.currentUser?.email ?? "?")
        let parts = source.split(separator: " ")
        if parts.count >= 2 {
            return String((parts[0].first ?? " ")) + String((parts[1].first ?? " "))
        }
        return String(source.prefix(2)).uppercased()
    }

    // MARK: - Actions

    private func load() async {
        isLoading = true
        errorMessage = nil
        do {
            let me = try await AuthService.shared.fetchMe()
            name = me.profile?.name ?? ""
            phone = me.profile?.phone ?? ""
            avatarUrl = me.user.avatarUrl
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    private func save() async {
        isSaving = true
        errorMessage = nil
        do {
            try await AuthService.shared.updateProfile(
                name: name.trimmingCharacters(in: .whitespaces).isEmpty ? nil : name,
                phone: phone.trimmingCharacters(in: .whitespaces).isEmpty ? nil : phone
            )
            // Push local name into AppState so the toolbar reflects it immediately
            if var user = appState.currentUser {
                user.avatarUrl = avatarUrl
                user.phone = phone.isEmpty ? nil : phone
                appState.currentUser = user
            }
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            isSaving = false
        }
    }

    private func pickAvatar() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.jpeg, .png, .webP]
        panel.begin { response in
            guard response == .OK, let url = panel.url,
                  let data = try? Data(contentsOf: url) else { return }
            let ext = url.pathExtension.lowercased()
            let mime: String
            switch ext {
            case "png": mime = "image/png"
            case "webp": mime = "image/webp"
            default: mime = "image/jpeg"
            }
            if data.count > 5 * 1024 * 1024 {
                errorMessage = "image must be under 5 MB"
                return
            }
            avatarImage = NSImage(data: data)
            Task {
                isUploadingAvatar = true
                defer { isUploadingAvatar = false }
                do {
                    let newUrl = try await AuthService.shared.uploadAvatar(
                        data: data,
                        filename: url.lastPathComponent,
                        mimeType: mime
                    )
                    avatarUrl = newUrl
                    if var user = appState.currentUser {
                        user.avatarUrl = newUrl
                        appState.currentUser = user
                    }
                } catch {
                    errorMessage = error.localizedDescription
                    avatarImage = nil
                }
            }
        }
    }
}
