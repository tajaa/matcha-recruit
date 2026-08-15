import SwiftUI

struct CommsComposerSheet: View {
    let slug: String
    let onStarted: (DmThread) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var vm: CommsComposerViewModel

    init(slug: String, onStarted: @escaping (DmThread) -> Void = { _ in }) {
        self.slug = slug
        self.onStarted = onStarted
        _vm = State(initialValue: CommsComposerViewModel(slug: slug))
    }

    var body: some View {
        NavigationStack {
            Form {
                if vm.isLoading && vm.page == nil {
                    ProgressView("Loading business…")
                } else if let page = vm.page {
                    Section {
                        Label(page.brand_name, systemImage: "building.2")
                        if !page.claimed {
                            Text("This business has not claimed its TellUs profile yet.")
                                .font(.interFootnote).foregroundStyle(.secondary)
                        } else if !page.messaging_enabled {
                            Text("Messaging is currently unavailable for this business.")
                                .font(.interFootnote).foregroundStyle(.secondary)
                        }
                    }

                    if page.claimed && page.messaging_enabled {
                        if vm.needsStoreSelection {
                            Section("Location") {
                                Picker("Store", selection: $vm.selectedStoreID) {
                                    Text("Choose a location").tag(String?.none)
                                    ForEach(vm.stores) { store in
                                        Text(storeLabel(store)).tag(Optional(store.id))
                                    }
                                }
                            }
                        } else if let store = vm.stores.first {
                            Section("Location") { Text(storeLabel(store)) }
                        }

                        Section("Question") {
                            Picker("Topic", selection: $vm.topic) {
                                ForEach(DmTopic.allCases.filter { $0 != .unknown }, id: \.self) { topic in
                                    Text(topic.label).tag(topic)
                                }
                            }
                            TextEditor(text: Binding(
                                get: { vm.body },
                                set: { vm.setBody($0) }
                            ))
                            .frame(minHeight: 120)
                            Text("Ask about hours, availability, inventory, or anything else you need to know.")
                                .font(.interFootnote).foregroundStyle(.secondary)
                        }
                    }
                }

                if let error = vm.error {
                    Section { Text(error).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Message business")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task {
                            await vm.send()
                            if let thread = vm.startedThread {
                                onStarted(thread)
                                dismiss()
                            }
                        }
                    } label: {
                        if vm.isSending { ProgressView() } else { Text("Send") }
                    }
                    .disabled(!vm.canSend || vm.isSending)
                }
            }
            .task { await vm.load() }
        }
    }

    private func storeLabel(_ store: MessagingStore) -> String {
        [store.name, store.city, store.state].compactMap { $0 }.joined(separator: " · ")
    }
}

extension DmTopic {
    var label: String {
        switch self {
        case .hours: "Hours"
        case .availability: "Availability"
        case .inventory: "Inventory"
        case .order: "Order or reservation"
        case .service: "Service"
        case .accessibility: "Accessibility"
        case .other, .unknown: "Other"
        }
    }
}
