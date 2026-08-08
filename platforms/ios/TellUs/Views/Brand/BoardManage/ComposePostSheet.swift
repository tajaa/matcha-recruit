import SwiftUI

/// v1 omits the `.deal` kind — creating a deal post requires picking a
/// board-visibility Listing owned by this brand, and listings CRUD is a
/// web-only feature (see plan §7 out-of-scope). Deals created on web still
/// show correctly in the consumer BoardFeedView.
struct ComposePostSheet: View {
    @Bindable var vm: BoardManageViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var kind: BoardPostKind = .update
    @State private var title = ""
    @State private var body_ = ""
    @State private var eventStart = Date()
    @State private var eventEnd = Date().addingTimeInterval(3600)
    @State private var isPinned = false

    private let composableKinds: [BoardPostKind] = [.update, .event, .question]
    private static let iso = ISO8601DateFormatter()

    private var eventRangeInvalid: Bool { kind == .event && eventEnd <= eventStart }

    var body: some View {
        NavigationStack {
            Form {
                Picker("Type", selection: $kind) {
                    ForEach(composableKinds, id: \.self) { Text($0.rawValue.capitalized).tag($0) }
                }
                TextField("Title", text: $title)
                TextField("Body", text: $body_, axis: .vertical)
                if kind == .event {
                    DatePicker("Starts", selection: $eventStart)
                    DatePicker("Ends", selection: $eventEnd)
                    if eventRangeInvalid {
                        Text("End time must be after the start time.").foregroundStyle(.red).font(.footnote)
                    }
                }
                Toggle("Pin to top", isOn: $isPinned)

                if let error = vm.error {
                    Text(error).foregroundStyle(.red).font(.footnote)
                }
            }
            .navigationTitle("New post")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Post") {
                        Task {
                            await vm.createPost(BoardPostCreate(
                                kind: kind.rawValue, title: title, body: body_.isEmpty ? nil : body_,
                                listing_id: nil,
                                event_starts_at: kind == .event ? Self.iso.string(from: eventStart) : nil,
                                event_ends_at: kind == .event ? Self.iso.string(from: eventEnd) : nil
                            ))
                            dismiss()
                        }
                    }
                    .disabled(title.isEmpty || eventRangeInvalid)
                }
            }
        }
    }
}
