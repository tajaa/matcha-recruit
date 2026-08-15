import SwiftUI

struct IntakeFormView: View {
    @Bindable var vm: IntakeViewModel

    var body: some View {
        if let result = vm.result {
            IntakeSuccessView(result: result)
        } else if let config = vm.config {
            Form {
                Section {
                    Text(config.brand_name).font(.interHeadline)
                    if let store = config.store_name { Text(store).font(.interSubheadline).foregroundStyle(.secondary) }
                }

                Section("Category") {
                    Picker("Category", selection: $vm.category) {
                        ForEach(config.categories, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                }

                Section("How was it?") {
                    Picker("Sentiment", selection: $vm.sentiment) {
                        ForEach(Sentiment.allCases, id: \.self) { Text($0.rawValue.capitalized).tag($0) }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Details") {
                    TextField("Title (optional)", text: $vm.title)
                    TextField("What happened?", text: $vm.description, axis: .vertical)
                        .lineLimit(3...8)
                }

                if !config.prompts.isEmpty {
                    Section("A few more questions") {
                        ForEach(config.prompts) { prompt in
                            TextField(prompt.prompt, text: Binding(
                                get: { vm.answers[prompt.id] ?? "" },
                                set: { vm.answers[prompt.id] = $0 }
                            ), axis: .vertical)
                        }
                    }
                }

                Section {
                    IntakeMediaSection(vm: vm)
                }

                // Web gates this on `loggedIn || !claimed` (Intake.tsx:77-78)
                // — in-app the submitter is always signed in (bearer-attached),
                // so it's always shown. Gating on `!config.claimed` instead
                // hid the rating control for the common (claimed-brand) case
                // while canSubmit still required rating > 0, permanently
                // disabling Submit.
                Section {
                    Toggle("Post as a public review", isOn: $vm.postAsReview)
                    if vm.postAsReview {
                        HStack {
                            ForEach(1...5, id: \.self) { star in
                                Image(systemName: star <= vm.rating ? "star.fill" : "star")
                                    .foregroundStyle(.yellow)
                                    .onTapGesture { vm.rating = star }
                            }
                        }
                    }
                }

                if let error = vm.submitError {
                    Section { Text(error).foregroundStyle(.red).font(.interFootnote) }
                }

                Section {
                    Button {
                        Task { await vm.submit() }
                    } label: {
                        if vm.isSubmitting { ProgressView() } else { Text("Submit").bold() }
                    }
                    .disabled(!vm.canSubmit)
                }
            }
        }
    }
}
