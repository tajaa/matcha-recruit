#!/usr/bin/env python3
"""Offline native smoke checks + component previews (not a signed-in app test).

Compiles production typography, brief, discussion row and report entry views.
Usage: python3 scripts/tests/test_espresso_ticket_design.py [output-directory]
No account, API, network images or production application state is used.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "platforms/desktop/Espresso/Espresso"
VIEWS = APP / "Views/MatchaWork/TaskViewer"

STUBS = r'''
import SwiftUI
import AppKit
final class AppState {
    var themeText: Color = .primary
    var themeTextSecondary: Color = .secondary
}
extension Color {
    static let mwInk = Color.primary
    static let mwInkStrong = Color.primary
    static let zinc800 = Color.gray.opacity(0.15)
}
struct MWTaskHistoryEntry {
    var metadata: [String: String]?
    var actorUserId: String?
    var actorName: String?
    var actorAvatarUrl: String? = nil
    var createdAt = "2026-09-10T20:00:00Z"
    var attachmentIds: [String]? = nil
}
struct MWProjectFile: Identifiable {
    var id = "report"
    var filename = "research-report-ems-r1.md"
    var storageUrl = ""
    var isImage = false
}
struct ChannelAvatarView: View {
    let senderId: String
    let payloadURL: String?
    let name: String
    let size: CGFloat
    var body: some View {
        Text(String(name.prefix(1))).font(.ticket(size: 11))
            .frame(width: size, height: size).background(.primary.opacity(0.07)).clipShape(Circle())
    }
}
enum PacificDateFormatter {
    static func absolute(_ value: String) -> String? { "Sep 10, 1:00 PM PT" }
}
struct TaskViewerSheet: View {
    @State var previewFile: MWProjectFile?
    let appState = AppState()
    struct LiveTask { var category = "research"; var autoprClaimedAt: String? = nil }
    let liveAutoPRTask = LiveTask()
    let autoPRIsQueueCandidate = false
    let researchReportAttachment: MWProjectFile? = MWProjectFile()
    var body: some View { researchReportSection }
}
let human = MWTaskHistoryEntry(metadata: ["body": "The report reads well. Could you include screenshots of the sources too?"], actorUserId: "human", actorName: "Haley")
let bot = MWTaskHistoryEntry(metadata: ["body": "I’ll add source screenshots and captions to the report.", "reply_to_name": "Haley", "reply_to_excerpt": "Could you include screenshots of the sources too?"], actorUserId: "bot", actorName: "Untrusted display name")
struct TicketComponents: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Text("Ticket components · native preview").font(.ticket(size: 11)).foregroundStyle(.secondary)
                Spacer()
                Text("Edit   ···   ×").font(.ticket(size: 11)).foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 12) {
                Text("What documentation does our EMS handle — and what’s missing?")
                    .font(.ticket(size: 23)).fixedSize(horizontal: false, vertical: true)
                Text("◉ In review     Medium     Haley     Review today")
                    .font(.ticket(size: 11)).foregroundStyle(.secondary)
            }
            Divider().opacity(0.5)
            VStack(alignment: .leading, spacing: 10) {
                TicketSectionHeading(title: "Contributor brief", detail: "Haley")
                TicketBriefText(text: "## Subject\nThe most valuable documentation sources for our EMS.\n\n## Expected output\nA concise report with data, graphs, and screenshots from the research.")
            }
            VStack(alignment: .leading, spacing: 8) {
                TicketSectionHeading(title: "matcha-autopr", detail: "Automated · ready for review")
                Text("EMS captures structured events but lacks governed evidence attachments. Prioritize an Evidence Pack.")
                    .font(.ticket(size: 13)).lineSpacing(3)
            }
            TaskViewerSheet()
            Divider().opacity(0.5)
            TicketSectionHeading(title: "Discussion", detail: "2")
            NoteRow(entry: human, files: [], autoPRBotUserId: "bot", onPreview: { _ in }, onReply: {})
            NoteRow(entry: bot, files: [], autoPRBotUserId: "bot", onPreview: { _ in }, onReply: {})
            Text("Write a comment…").font(.ticket(size: 13)).foregroundStyle(.secondary)
                .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                .background(.primary.opacity(0.035)).cornerRadius(6)
        }
        .padding(24).frame(width: 700)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}
@main struct DesignSmoke {
    @MainActor static func main() throws {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        precondition(TicketTypography.native(size: 13).familyName == "Inter", "Bundled Inter must register, not silently fall back")
        for scheme in [ColorScheme.dark, .light] {
            let row = NSHostingView(rootView: NoteRow(entry: bot, files: [], autoPRBotUserId: "bot", onPreview: { _ in })
                .frame(width: 620).preferredColorScheme(scheme))
            let height = row.fittingSize.height
            precondition(height > 45 && height < 150, "Quoted reply must remain content-sized: \(height)")
            let empty = NSHostingView(rootView: NoteRow(entry: MWTaskHistoryEntry(metadata: nil, actorUserId: nil, actorName: nil), files: [], onPreview: { _ in }))
            precondition(empty.fittingSize.height == 0, "Empty notes should not add whitespace")
            let brief = NSHostingView(rootView: TicketBriefText(text: "# Subject\nCafé ☕\n\n### Details\nOne\nTwo\n\nNot a heading: #tag").frame(width: 620))
            precondition(brief.fittingSize.height > 80 && brief.fittingSize.height < 220)
            guard CommandLine.arguments.count > 1 else { continue }
            let view = NSHostingView(rootView: TicketComponents().preferredColorScheme(scheme))
            let size = view.fittingSize
            let window = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.borderless], backing: .buffered, defer: false)
            window.contentView = view
            window.orderFront(nil)
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            view.layoutSubtreeIfNeeded()
            let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let name = scheme == .dark ? "ticket-dark.png" : "ticket-light.png"
            let url = URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent(name)
            try bitmap.representation(using: .png, properties: [:])!.write(to: url)
            window.orderOut(nil)
        }
        print("PASS: bundled Inter, content-sized replies, empty notes, Markdown headings; dark/light native renders")
    }
}
'''


def main():
    report = (VIEWS / "TaskViewerSheet+Sections.swift").read_text().split("    // MARK: - Attachments", 1)[0]
    report += "\n}\n"
    with tempfile.TemporaryDirectory(prefix="espresso-ticket-design-") as directory:
        root = Path(directory)
        bundle = root / "TicketDesign.app/Contents"
        binary = bundle / "MacOS/smoke"
        binary.parent.mkdir(parents=True)
        shutil.copytree(APP / "Resources/Fonts", bundle / "Resources/Fonts")
        source = root / "Smoke.swift"
        source.write_text((VIEWS / "TicketDesign.swift").read_text()
                          + (VIEWS / "NoteRow.swift").read_text() + report + STUBS)
        subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-module-cache-path", str(root / "cache"),
                        str(source), "-o", str(binary)], check=True)
        if len(sys.argv) > 1:
            Path(sys.argv[1]).mkdir(parents=True, exist_ok=True)
        subprocess.run([str(binary), *sys.argv[1:]], check=True)
    icon = APP / "Resources/Assets.xcassets/AppIcon.appiconset"
    for entry in json.loads((icon / "Contents.json").read_text())["images"]:
        assert (icon / entry["filename"]).is_file()
    print("PASS: icon catalog references resolve")


if __name__ == "__main__":
    main()
