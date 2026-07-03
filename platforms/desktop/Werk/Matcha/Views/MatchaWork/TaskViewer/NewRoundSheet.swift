import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// Sheet for opening a new round on a ticket. Any collaborator can hit
/// "Start Next Round" → name the suggested fix → optionally add a
/// kick-off note + paste a screenshot → submit. The fix becomes the
/// new round's headline subtask AND the round's display title.
struct NewRoundSheet: View {
    let nextRoundIndex: Int
    /// The current round's still-open checklist items. The person starting a
    /// round must say which (if any) they actually finished before it rolls
    /// the rest forward.
    let openSubtasks: [MWSubtask]
    let onCancel: () -> Void
    /// Returns true if submit succeeded and the sheet should dismiss.
    let onSubmit: (_ suggestedFix: String, _ body: String, _ pending: [PendingAttachment], _ completedSubtaskIds: [String]) async -> Bool

    @State private var suggestedFix = ""
    @State private var noteBody = ""
    @State private var pending: [PendingAttachment] = []
    @State private var completedIds: Set<String> = []
    @State private var submitting = false
    @State private var error: String?

    private var canSubmit: Bool {
        !suggestedFix.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("START ROUND \(nextRoundIndex)")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.mwInkStrong)
                        .tracking(0.5)
                    Text("Chain a new sub-todo onto this ticket")
                        .font(.system(size: 12))
                        .foregroundColor(.mwInk.opacity(0.85))
                }
                Spacer()
                Button(action: onCancel) {
                    Image(systemName: "xmark")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            // Force the round-opener to account for the current checklist: tick
            // what's actually done (archives onto this round) — the rest rolls
            // forward. Only shown when there are open items to resolve.
            if !openSubtasks.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("DID YOU COMPLETE ANY OF THESE?")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.mwInkStrong)
                        .tracking(0.5)
                    Text("Check off what's done — it archives into this round; unchecked items carry into Round \(nextRoundIndex).")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                    ForEach(openSubtasks) { item in
                        Button {
                            if completedIds.contains(item.id) { completedIds.remove(item.id) }
                            else { completedIds.insert(item.id) }
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: completedIds.contains(item.id) ? "checkmark.circle.fill" : "circle")
                                    .font(.system(size: 13))
                                    .foregroundColor(completedIds.contains(item.id) ? .mwInkStrong : .secondary)
                                Text(item.title)
                                    .font(.system(size: 12))
                                    .foregroundColor(.mwInk.opacity(0.9))
                                    .strikethrough(completedIds.contains(item.id))
                                    .lineLimit(2)
                                Spacer(minLength: 0)
                            }
                            .padding(.vertical, 3)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.mwInkStrong.opacity(0.08))
                .cornerRadius(6)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("SUGGESTED FIX")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                TextField("e.g. Add EIN validation before export", text: $suggestedFix)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundColor(.mwInk)
                    .padding(8)
                    .background(Color.mwInk.opacity(0.06))
                    .cornerRadius(5)
                    .onSubmit {
                        if canSubmit { Task { await submit() } }
                    }
                Text("Becomes a new checklist item AND this round's title.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("KICK-OFF NOTE (optional)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                TextEditor(text: $noteBody)
                    .font(.system(size: 12))
                    .foregroundColor(.mwInk.opacity(0.9))
                    .scrollContentBackground(.hidden)
                    .padding(5)
                    .frame(height: 80)
                    .background(Color.mwInk.opacity(0.06))
                    .cornerRadius(5)
                HStack(spacing: 8) {
                    Button {
                        attachFileFromDisk()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "paperclip").font(.system(size: 11))
                            Text("Attach file").font(.system(size: 11))
                        }
                        .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    Button {
                        attachImageFromClipboard()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "doc.on.clipboard").font(.system(size: 11))
                            Text("Paste screenshot").font(.system(size: 11))
                        }
                        .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    Spacer()
                }
                if !pending.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(pending) { att in
                                PendingAttachmentChip(attachment: att) {
                                    pending.removeAll { $0.id == att.id }
                                }
                            }
                        }
                    }
                }
            }

            if let err = error {
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.mwAttention)
            }

            HStack {
                Spacer()
                Button("Cancel", action: onCancel)
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Button {
                    Task { await submit() }
                } label: {
                    if submitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Open Round \(nextRoundIndex)")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(canSubmit ? .mwInkStrong : .secondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canSubmit || submitting)
            }
        }
        .padding(18)
        .frame(width: 480)
        .background(Color.appBackground)
    }

    private func submit() async {
        let title = suggestedFix.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, !submitting else { return }
        submitting = true
        error = nil
        let ok = await onSubmit(title, noteBody, pending, Array(completedIds))
        if !ok {
            error = "Couldn't open the round. Try again."
        }
        submitting = false
    }

    private func attachFileFromDisk() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.image, .pdf]
        panel.begin { resp in
            guard resp == .OK else { return }
            for url in panel.urls {
                guard let data = try? Data(contentsOf: url) else { continue }
                let filename = url.lastPathComponent
                let ext = (filename as NSString).pathExtension.lowercased()
                let mime = (UTType(filenameExtension: ext)?.preferredMIMEType) ?? "application/octet-stream"
                pending.append(PendingAttachment(data: data, filename: filename, mimeType: mime))
            }
        }
    }

    private func attachImageFromClipboard() {
        let pb = NSPasteboard.general
        if let png = pb.data(forType: .png) {
            pending.append(PendingAttachment(data: png, filename: clipboardScreenshotName(ext: "png"), mimeType: "image/png"))
            return
        }
        if let tiff = pb.data(forType: .tiff),
           let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            pending.append(PendingAttachment(data: png, filename: clipboardScreenshotName(ext: "png"), mimeType: "image/png"))
            return
        }
        let jpegType = NSPasteboard.PasteboardType(UTType.jpeg.identifier)
        if let jpeg = pb.data(forType: jpegType) {
            pending.append(PendingAttachment(data: jpeg, filename: clipboardScreenshotName(ext: "jpg"), mimeType: "image/jpeg"))
        }
    }

    private func clipboardScreenshotName(ext: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd-HHmmss"
        return "screenshot-\(f.string(from: Date())).\(ext)"
    }
}
