import SwiftUI
import AppKit

/// A person's private conversation with Espresso.
///
/// It is a channel underneath, so the messages, the cards and the quick
/// replies are the chat's own (`ChannelDetailView`). What this adds is the way
/// in (the conversation is created on first open) and the sheet where
/// abilities are switched on. Every message here is addressed to Espresso: no
/// mention is needed.
struct AssistantView: View {
    @Environment(AppState.self) private var appState
    @State private var channelId: String?
    @State private var errorMessage: String?
    @State private var showAbilities = false

    var body: some View {
        Group {
            if let channelId {
                ChannelDetailView(
                    channelId: channelId, isEmbedded: true, isAssistant: true,
                    onOpenAbilities: { showAbilities = true }
                )
            } else if let errorMessage {
                VStack(spacing: 10) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 22))
                        .foregroundColor(.red)
                    Text(errorMessage)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                    Button("Try again") { Task { await open() } }
                        .buttonStyle(.borderedProminent)
                        .tint(appState.themeAccent)
                        .controlSize(.small)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(appState.themeBg)
        .task { await open() }
        .sheet(isPresented: $showAbilities) {
            AssistantAbilitiesSheet()
                .environment(appState)
        }
    }

    private func open() async {
        errorMessage = nil
        do {
            channelId = try await MatchaWorkService.shared.ensureAssistantChannel()
        } catch let error as APIError {
            if let plan = error.planRequirement {
                appState.presentPaywall(for: plan.feature)
            }
            errorMessage = AssistantText.message(for: error)
        } catch {
            errorMessage = "Couldn't open your conversation with Espresso."
        }
    }
}

enum AssistantText {
    /// What the server said went wrong, as one line. FastAPI puts it in
    /// `detail`, either as a string or as `{ message }`.
    static func message(for error: APIError, fallback: String = "Something went wrong. Please try again.") -> String {
        guard case let .httpError(_, body) = error,
              let data = body.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return fallback
        }
        if let detail = json["detail"] as? String, !detail.isEmpty { return detail }
        if let detail = json["detail"] as? [String: Any],
           let text = detail["message"] as? String, !text.isEmpty {
            return text
        }
        return fallback
    }
}

/// What Espresso may do for this person. Looking things up is always on. An
/// ability that acts (send, invite, book) is switched on here, after the
/// person has read what it does with their data.
struct AssistantAbilitiesSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var data: AssistantAbilities?
    @State private var errorMessage: String?
    @State private var busyKey: String?
    @State private var consenting: AssistantAbility?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("What Espresso can do")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
            .padding(14)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if data?.isDryRun == true {
                        Label("Dry run: Espresso shows what it would send or book, and nothing leaves yet.",
                              systemImage: "exclamationmark.triangle.fill")
                            .font(.system(size: 11))
                            .foregroundColor(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let errorMessage {
                        Text(errorMessage)
                            .font(.system(size: 11))
                            .foregroundColor(.red)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if data == nil && errorMessage == nil {
                        ProgressView().controlSize(.small)
                    }
                    ForEach(data?.abilities ?? []) { ability in
                        row(ability)
                    }
                }
                .padding(14)
            }
        }
        .frame(width: 440, height: 480)
        .task { await load() }
        .onChange(of: appState.foregroundTick) {
            // Back from Google's consent in the browser: read the list again.
            Task { await load() }
        }
        .sheet(item: $consenting) { ability in
            AssistantConsentSheet(ability: ability) { contact in
                await accept(ability, contact: contact)
            }
            .environment(appState)
        }
    }

    @ViewBuilder
    private func row(_ ability: AssistantAbility) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(ability.label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
                if ability.alwaysOn {
                    Text("Always on").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                } else if ability.enabled {
                    Button("Switch off") { Task { await switchOff(ability) } }
                        .buttonStyle(.plain)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(appState.themeTextSecondary)
                        .disabled(busyKey == ability.key)
                } else {
                    Button(ability.consentOutdated ? "Review and switch on" : "Switch on") {
                        consenting = ability
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
                    .controlSize(.small)
                    .disabled(busyKey == ability.key)
                }
            }
            Label(ability.acts ? "Acts for you, only in this private conversation" : "Looks things up",
                  systemImage: ability.acts ? "lock.fill" : "magnifyingglass")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
            if ability.enabled && ability.available && !ability.needsConnection {
                Label("Ready", systemImage: "checkmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.green)
            }
            if ability.enabled, let reason = ability.reason {
                Text(reason)
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if ability.enabled && ability.needsConnection {
                Button(data?.google.connected == true ? "Reconnect Google" : "Connect Google") {
                    Task { await connect(ability) }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(busyKey == ability.key)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(appState.themeBorder, lineWidth: 1)
        )
    }

    private func load() async {
        do {
            data = try await MatchaWorkService.shared.assistantAbilities()
            errorMessage = nil
        } catch let error as APIError {
            errorMessage = AssistantText.message(for: error)
        } catch {
            errorMessage = "Couldn't load what Espresso can do."
        }
    }

    /// Returns what went wrong, or nil when the ability is now on.
    private func accept(_ ability: AssistantAbility, contact: AssistantContact?) async -> String? {
        busyKey = ability.key
        defer { busyKey = nil }
        do {
            try await MatchaWorkService.shared.enableAssistantAbility(
                ability.key, consentVersion: ability.disclosure?.version, contact: contact
            )
            consenting = nil
            await load()
            return nil
        } catch let error as APIError {
            return AssistantText.message(for: error)
        } catch {
            return "Something went wrong. Please try again."
        }
    }

    private func switchOff(_ ability: AssistantAbility) async {
        busyKey = ability.key
        defer { busyKey = nil }
        do {
            try await MatchaWorkService.shared.disableAssistantAbility(ability.key)
            await load()
        } catch let error as APIError {
            errorMessage = AssistantText.message(for: error)
        } catch {
            errorMessage = "Something went wrong. Please try again."
        }
    }

    private func connect(_ ability: AssistantAbility) async {
        busyKey = ability.key
        defer { busyKey = nil }
        do {
            let raw = try await MatchaWorkService.shared.connectGoogle(forAbility: ability.key)
            // Google's own consent page, and nothing else, is opened.
            guard let url = URL(string: raw), url.scheme == "https",
                  url.host() == "accounts.google.com" else {
                errorMessage = "Couldn't start Google's sign-in."
                return
            }
            NSWorkspace.shared.open(url)
        } catch let error as APIError {
            errorMessage = AssistantText.message(for: error)
        } catch {
            errorMessage = "Something went wrong. Please try again."
        }
    }
}

/// The disclosure for one ability. Nothing is switched on until it is accepted.
struct AssistantConsentSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    let ability: AssistantAbility
    /// Switches the ability on; returns what went wrong, or nil.
    let onAccept: (AssistantContact?) async -> String?

    @State private var contact = AssistantContact(name: "", phone: "", email: "")
    @State private var errorMessage: String?
    @State private var working = false

    private var needsContact: Bool { ability.key == "reservations" }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(ability.disclosure?.title ?? ability.label)
                .font(.system(size: 14, weight: .semibold))
            ForEach(ability.disclosure?.body ?? [], id: \.self) { line in
                Text(line)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if needsContact {
                Divider()
                Text("Book under").font(.system(size: 11, weight: .semibold))
                TextField("Full name", text: $contact.name)
                TextField("Phone", text: $contact.phone)
                TextField("Email", text: $contact.email)
            }
            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                Spacer()
                Button("Not now") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button {
                    Task {
                        working = true
                        errorMessage = await onAccept(needsContact ? contact : nil)
                        working = false
                    }
                } label: {
                    Text("I understand, switch it on")
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .disabled(working || (needsContact && !contact.isUsable))
            }
        }
        .textFieldStyle(.roundedBorder)
        .padding(16)
        .frame(width: 420)
        .onAppear {
            if let saved = ability.contact { contact = saved }
        }
    }
}
