import SwiftUI

struct LogSessionSheet: View {
    @Bindable var viewModel: ProjectDetailViewModel
    var initialLinkedThreadId: String? = nil
    @Environment(\.dismiss) private var dismiss

    @State private var at = Date()
    @State private var durationMin: String = "30"
    @State private var notes = ""
    @State private var billable = true
    @State private var rateOverrideDollars = ""
    @State private var linkedThreadId: String? = nil
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private var threads: [MWProjectChat] {
        viewModel.project?.chats ?? []
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("log session")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.9))

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("date / time").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                    DatePicker("", selection: $at)
                        .labelsHidden()
                        .font(.system(size: 12))
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("duration (min)").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                    TextField("", text: $durationMin, prompt: Text("30").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.9))
                        .frame(width: 80)
                    Divider()
                }
                Spacer()
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("notes").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                TextEditor(text: $notes)
                    .font(.system(size: 12))
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 100)
                    .padding(6)
                    .background(Color.black.opacity(0.2))
                    .cornerRadius(6)
            }

            HStack {
                Toggle(isOn: $billable) {
                    Text("billable").font(.system(size: 11)).foregroundColor(.white.opacity(0.7))
                }
                .toggleStyle(.switch)
                .controlSize(.small)

                if billable {
                    HStack(spacing: 4) {
                        Text("rate override $").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                        TextField("", text: $rateOverrideDollars, prompt: Text("default").foregroundColor(.white.opacity(0.25)))
                            .textFieldStyle(.plain)
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.9))
                            .frame(width: 60)
                    }
                }
                Spacer()
            }

            if !threads.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("link to chat thread (optional)").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                    Picker("", selection: $linkedThreadId) {
                        Text("none").tag(String?.none)
                        ForEach(threads, id: \.id) { t in
                            Text(t.title).tag(Optional(t.id))
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.menu)
                }
            }

            if let errorMessage {
                Text(errorMessage).font(.system(size: 11)).foregroundColor(.red.opacity(0.8))
            }

            HStack {
                Button { dismiss() } label: {
                    Text("cancel").font(.system(size: 12)).foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
                Spacer()
                Button { Task { await submit() } } label: {
                    Text(isSubmitting ? "saving…" : "save")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(isSubmitting ? .white.opacity(0.4) : Color.matcha500)
                }
                .buttonStyle(.plain)
                .disabled(isSubmitting)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(20)
        .frame(width: 440)
        .background(Color.appBackground)
        .onAppear {
            linkedThreadId = initialLinkedThreadId
        }
    }

    private func submit() async {
        isSubmitting = true
        errorMessage = nil
        // Clear any stale error from a prior op so we can detect this call's outcome
        // without a false negative.
        viewModel.errorMessage = nil
        defer { isSubmitting = false }

        let minutes = Int(durationMin.trimmingCharacters(in: .whitespaces)) ?? 0
        let rateCents: Int? = {
            let trimmed = rateOverrideDollars.trimmingCharacters(in: .whitespaces)
            guard billable, let d = Double(trimmed), d > 0 else { return nil }
            return Int(d * 100)
        }()

        let iso = ISO8601DateFormatter().string(from: at)
        await viewModel.appendSession(
            at: iso,
            durationMin: minutes > 0 ? minutes : nil,
            notes: notes.isEmpty ? nil : notes,
            billable: billable,
            rateCentsOverride: rateCents,
            linkedThreadId: linkedThreadId
        )
        if viewModel.errorMessage == nil {
            dismiss()
        } else {
            errorMessage = viewModel.errorMessage
        }
    }
}
