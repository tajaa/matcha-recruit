import SwiftUI

/// Modal for creating a channel. Presented from both the sidebar section and the
/// full-pane Channels hub — split out of ChannelsSidebarView.swift, which owned
/// three unrelated top-level views.
struct CreateChannelSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState
    let onCreated: (ChannelDetail) -> Void

    @State private var name = ""
    @State private var description = ""
    @State private var visibility = "public"
    @State private var category: ChannelCategory = .general
    @State private var isPaid = false
    @State private var priceDollars = "5"
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @FocusState private var nameFocused: Bool

    // Paid/creator channels are for personal accounts only. Matches the
    // backend rule in /channels POST (role must be individual or admin)
    // and the web client's canCreatePaid gating.
    private var canCreatePaid: Bool {
        let role = appState.currentUser?.role ?? ""
        return role == "individual" || role == "admin"
    }

    private var nameIsBlank: Bool {
        name.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("create channel")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))

            nameField
            descriptionField
            categoryField

            HStack(spacing: 16) {
                visibilityButton(label: "public")
                visibilityButton(label: "private")
                Spacer()
            }

            paidSection

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.red.opacity(0.8))
            }

            footer
        }
        .padding(20)
        .frame(width: 360)
        .background(Color.appBackground)
    }

    // MARK: - Fields

    private var nameField: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("name")
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.4))
            HStack(spacing: 6) {
                TextField("", text: $name, prompt: Text("general").foregroundColor(.white.opacity(0.25)))
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.9))
                    .focused($nameFocused)
                EmojiPaletteButton { nameFocused = true }
            }
            Divider()
        }
    }

    private var descriptionField: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("description")
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.4))
            TextField("", text: $description, prompt: Text("optional").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.9))
                .lineLimit(1...3)
            Divider()
        }
    }

    private var categoryField: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("category")
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.4))
            Picker("", selection: $category) {
                ForEach(ChannelCategory.allCases) { cat in
                    Text(cat.label).tag(cat)
                }
            }
            .pickerStyle(.menu)
            .labelsHidden()
            Divider()
        }
    }

    /// Paid-channel toggle + price. Three states: hidden (role can't monetize),
    /// plan-locked upsell, or the live toggle.
    @ViewBuilder
    private var paidSection: some View {
        if canCreatePaid, !appState.canPaidChannels {
            // Role-eligible but plan-locked: creator monetization is Pro.
            Button {
                appState.presentPaywall(for: "paid_channels")
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 9))
                        .foregroundColor(.white.opacity(0.45))
                    Text("paid (subscribers only)")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.5))
                    Spacer()
                    Text("PRO")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(appState.themeAccent)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(appState.themeAccent.opacity(0.15))
                        .cornerRadius(4)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else if canCreatePaid {
            Toggle(isOn: $isPaid) {
                Text("paid (subscribers only)")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.7))
            }
            .toggleStyle(.switch)
            .controlSize(.small)

            if isPaid {
                VStack(alignment: .leading, spacing: 4) {
                    Text("price / month (usd)")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.4))
                    HStack(spacing: 4) {
                        Text("$")
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.5))
                        TextField("", text: $priceDollars, prompt: Text("5").foregroundColor(.white.opacity(0.25)))
                            .textFieldStyle(.plain)
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.9))
                    }
                    Divider()
                }
            }
        }
    }

    private var footer: some View {
        HStack {
            Button {
                dismiss()
            } label: {
                Text("cancel")
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.5))
            }
            .buttonStyle(.plain)
            Spacer()
            Button {
                Task { await create() }
            } label: {
                if isSubmitting {
                    Text("creating…")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.4))
                } else {
                    Text("create")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(nameIsBlank ? .white.opacity(0.25) : Color.matcha500)
                }
            }
            .buttonStyle(.plain)
            .disabled(nameIsBlank || isSubmitting)
            .keyboardShortcut(.return, modifiers: .command)
        }
    }

    private func visibilityButton(label: String) -> some View {
        let active = visibility == label
        return Button {
            visibility = label
        } label: {
            VStack(spacing: 2) {
                Text(label)
                    .font(.system(size: 11))
                    .foregroundColor(active ? Color.matcha500 : .white.opacity(0.5))
                Rectangle()
                    .fill(active ? Color.matcha500 : Color.clear)
                    .frame(height: 1)
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - Submit

    private func create() async {
        isSubmitting = true
        errorMessage = nil
        var paidConfig: ChannelsService.PaidChannelConfig? = nil
        if isPaid && canCreatePaid {
            guard let dollars = Double(priceDollars.trimmingCharacters(in: .whitespaces)), dollars > 0 else {
                errorMessage = "Enter a valid price"
                isSubmitting = false
                return
            }
            let cents = Int((dollars * 100).rounded())
            paidConfig = ChannelsService.PaidChannelConfig(
                priceCents: cents,
                currency: "usd",
                inactivityThresholdDays: nil,
                inactivityWarningDays: 3
            )
        }
        do {
            let channel = try await ChannelsService.shared.createChannel(
                name: name.trimmingCharacters(in: .whitespaces),
                description: description.isEmpty ? nil : description,
                visibility: visibility,
                category: category.rawValue,
                paidConfig: paidConfig
            )
            onCreated(channel)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            isSubmitting = false
        }
    }
}
