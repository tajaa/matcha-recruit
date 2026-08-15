import SwiftUI

/// v1 omits the `.deal` kind on CREATE — creating a deal post requires
/// picking a board-visibility Listing owned by this brand, and listings CRUD
/// only landed in commit 14. Deals created on web still show correctly in
/// the consumer BoardFeedView, and existing deal posts can still be edited
/// here (title/body/pin only — see below).
struct ComposePostSheet: View {
    @Bindable var vm: BoardManageViewModel
    @Environment(\.dismiss) private var dismiss

    /// nil = compose a new post; set = editing an existing one.
    let editing: BoardPost?

    @State private var kind: BoardPostKind = .update
    @State private var title = ""
    @State private var body_ = ""
    @State private var eventStart = Date()
    @State private var eventEnd = Date().addingTimeInterval(3600)
    @State private var isPinned = false

    private let composableKinds: [BoardPostKind] = [.update, .event, .question]
    private static let iso = ISO8601DateFormatter()

    private var eventRangeInvalid: Bool { kind == .event && eventEnd <= eventStart }
    private var isEditing: Bool { editing != nil }

    init(vm: BoardManageViewModel, editing: BoardPost? = nil) {
        self.vm = vm
        self.editing = editing
        _kind = State(initialValue: editing?.kind ?? .update)
        _title = State(initialValue: editing?.title ?? "")
        _body_ = State(initialValue: editing?.body ?? "")
        _isPinned = State(initialValue: editing?.is_pinned ?? false)
    }

    var body: some View {
        NavigationStack {
            Form {
                // Kind + event scheduling are set at creation server-side
                // (BoardPostUpdate carries only title/body/is_pinned) —
                // fixed, not editable, once a post exists.
                if isEditing {
                    LabeledContent("Type", value: kind.rawValue.capitalized)
                } else {
                    Picker("Type", selection: $kind) {
                        ForEach(composableKinds, id: \.self) { Text($0.rawValue.capitalized).tag($0) }
                    }
                }
                TextField("Title", text: $title)
                TextField("Body", text: $body_, axis: .vertical)
                if kind == .event && !isEditing {
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
            .scrollContentBackground(.hidden)
            .background(EmberBackground())
            .navigationTitle(isEditing ? "Edit post" : "New post")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isEditing ? "Save" : "Post") {
                        Task {
                            if let editing {
                                await vm.updatePost(editing.id, BoardPostUpdate(
                                    title: title, body: body_.isEmpty ? nil : body_, is_pinned: isPinned
                                ))
                            } else {
                                await vm.createPost(BoardPostCreate(
                                    kind: kind.rawValue, title: title, body: body_.isEmpty ? nil : body_,
                                    listing_id: nil,
                                    event_starts_at: kind == .event ? Self.iso.string(from: eventStart) : nil,
                                    event_ends_at: kind == .event ? Self.iso.string(from: eventEnd) : nil
                                ))
                            }
                            dismiss()
                        }
                    }
                    .disabled(title.isEmpty || (!isEditing && eventRangeInvalid))
                }
            }
        }
    }
}
