#!/usr/bin/env python3
"""Offline native smoke checks + component previews (not a signed-in app test).

Compiles production typography, brief, discussion row and report entry views,
then renders ticket and workspace-chrome design fixtures.
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
struct PreviewAppMark: View {
    var body: some View {
        let url = Bundle.main.url(forResource: "app_icon_512", withExtension: "png")!
        Image(nsImage: NSImage(contentsOf: url)!)
            .resizable().interpolation(.high).scaledToFit()
            .frame(width: 34, height: 34).clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
struct PreviewSidebarRow: View {
    let icon: String
    let label: String
    var active = false
    var railOnly = false
    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: icon).frame(width: 15)
            Text(label).font(.espresso(size: 12, weight: active ? .medium : .regular))
            Spacer()
        }
        .foregroundStyle(active ? Color.orange : Color.primary.opacity(0.72))
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(RoundedRectangle(cornerRadius: 6).fill(active && !railOnly ? Color.orange.opacity(0.075) : .clear))
        .overlay(alignment: .leading) {
            if active { Capsule().fill(Color.orange).frame(width: 2, height: 16) }
        }
    }
}
struct PreviewSidebar: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                PreviewAppMark()
                Text("Espresso").font(.espresso(size: 15, weight: .medium))
                Spacer()
            }.padding(.bottom, 15)
            PreviewSidebarRow(icon: "house", label: "Home")
            HStack {
                Image(systemName: "magnifyingglass")
                Text("Filter sidebar…")
                Spacer()
            }
            .font(.espresso(size: 11)).foregroundStyle(.secondary)
            .padding(.horizontal, 9).padding(.vertical, 7)
            .background(.primary.opacity(0.045)).clipShape(RoundedRectangle(cornerRadius: 7))
            .padding(.vertical, 12)
            Text("Tabs").font(.espresso(size: 11)).foregroundStyle(.secondary)
                .padding(.horizontal, 10).padding(.bottom, 5)
            PreviewSidebarRow(icon: "square.grid.2x2", label: "WorkWork")
            PreviewSidebarRow(icon: "square.grid.2x2", label: "Collab", active: true, railOnly: true)
            PreviewSidebarRow(icon: "square.grid.2x2", label: "Beetlejuice")
            PreviewSidebarRow(icon: "square.grid.2x2", label: "Gummfit")
            Spacer().frame(height: 12)
            PreviewSidebarRow(icon: "square.grid.2x2", label: "Workspaces", active: true)
            PreviewSidebarRow(icon: "number", label: "Channels")
            PreviewSidebarRow(icon: "book.closed", label: "Journals")
            PreviewSidebarRow(icon: "bubble.left.and.bubble.right", label: "Threads")
            PreviewSidebarRow(icon: "checklist", label: "Productivity")
            PreviewSidebarRow(icon: "envelope", label: "Email")
            Spacer()
            Divider().opacity(0.45)
            HStack {
                Label("Inbox", systemImage: "envelope")
                Spacer()
                Label("People", systemImage: "person.2")
            }.font(.espresso(size: 11)).foregroundStyle(.secondary).padding(.top, 12)
        }
        .padding(16).frame(width: 220)
        .background(Color.primary.opacity(0.025))
    }
}
struct PreviewBoardCard: View {
    let title: String
    var queue = false
    var progress: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if queue {
                Label("In queue · Waiting for matcha-autopr", systemImage: "clock.arrow.circlepath")
                    .font(.espresso(size: 9)).foregroundStyle(.blue)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.blue.opacity(0.06))
            }
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "circle").foregroundStyle(.secondary)
                Text(title).font(.espresso(size: 13)).fixedSize(horizontal: false, vertical: true)
            }.padding(.horizontal, 10).padding(.top, 10).padding(.bottom, 7)
            if let progress {
                Label(progress, systemImage: "location.north.line")
                    .font(.espresso(size: 10)).foregroundStyle(.secondary).lineLimit(1)
                    .padding(.horizontal, 10).padding(.bottom, 7)
            }
            HStack(spacing: 7) {
                Label("Engineering", systemImage: "hammer")
                    .foregroundStyle(.blue)
                Text("Haley").foregroundStyle(.secondary)
                Spacer()
                Text("2h").foregroundStyle(.secondary)
                Image(systemName: "ellipsis").foregroundStyle(.secondary)
            }.font(.espresso(size: 9)).padding(.horizontal, 10).padding(.bottom, 9)
        }
        .background(RoundedRectangle(cornerRadius: 8).fill(Color(nsColor: .controlBackgroundColor)))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.primary.opacity(0.12), lineWidth: 0.7))
        .overlay(alignment: .topTrailing) { Circle().fill(.orange).frame(width: 6, height: 6).padding(7) }
    }
}
struct PreviewColumn: View {
    let title: String
    let cards: [(String, Bool, String?)]
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 6) {
                Text(title).font(.espresso(size: 12))
                Text("\(cards.count)").font(.espresso(size: 10)).foregroundStyle(.secondary)
                Spacer()
                Image(systemName: "plus").foregroundStyle(.secondary)
            }.padding(.horizontal, 8).padding(.top, 8)
            ForEach(Array(cards.enumerated()), id: \.offset) { entry in
                PreviewBoardCard(title: entry.element.0, queue: entry.element.1, progress: entry.element.2)
            }
            Spacer()
        }
        .padding(.horizontal, 6).padding(.bottom, 7)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.02)))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.primary.opacity(0.08), lineWidth: 0.5))
    }
}
struct WorkspaceChromePreview: View {
    var body: some View {
        HStack(spacing: 0) {
            PreviewSidebar()
            Divider().opacity(0.45)
            VStack(alignment: .leading, spacing: 14) {
                Text("Collab").font(.espresso(size: 20, weight: .medium))
                HStack(alignment: .top, spacing: 8) {
                    PreviewColumn(title: "Todo", cards: [
                        ("Harden production test passwords", false, nil),
                        ("Create broker-specific tier information", true, nil),
                    ])
                    PreviewColumn(title: "In progress", cards: [
                        ("Add source screenshots to the research report", false, "Researching source examples"),
                    ])
                    PreviewColumn(title: "Review", cards: [
                        ("Refine the EMS documentation brief", false, nil),
                    ])
                }
            }.padding(18)
        }
        .frame(width: 900, height: 550)
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

            let workspace = NSHostingView(rootView: WorkspaceChromePreview().preferredColorScheme(scheme))
            let workspaceSize = workspace.fittingSize
            let workspaceWindow = NSWindow(contentRect: NSRect(origin: .zero, size: workspaceSize), styleMask: [.borderless], backing: .buffered, defer: false)
            workspaceWindow.contentView = workspace
            workspaceWindow.orderFront(nil)
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            workspace.layoutSubtreeIfNeeded()
            let workspaceBitmap = workspace.bitmapImageRepForCachingDisplay(in: workspace.bounds)!
            workspace.cacheDisplay(in: workspace.bounds, to: workspaceBitmap)
            let workspaceName = scheme == .dark ? "workspace-dark.png" : "workspace-light.png"
            let workspaceURL = URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent(workspaceName)
            try workspaceBitmap.representation(using: .png, properties: [:])!.write(to: workspaceURL)
            workspaceWindow.orderOut(nil)
        }
        print("PASS: bundled Inter, content-sized replies, empty notes, Markdown headings; dark/light ticket and workspace renders")
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
        shutil.copy2(APP / "Resources/Assets.xcassets/AppIcon.appiconset/app_icon_512.png",
                     bundle / "Resources/app_icon_512.png")
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
    card = (APP / "Views/MatchaWork/KanbanCard.swift").read_text()
    columns = (APP / "Views/MatchaWork/KanbanBoardView+Columns.swift").read_text()
    theme = (APP / "App/AppState+Theme.swift").read_text()
    assert 'return ("In queue"' in card
    assert "Text(currentColumnLabel)" not in card
    assert ".strokeBorder(Color.yellow" not in columns
    assert "Text(label.uppercased())" not in columns
    assert "var isSidebarDark: Bool { !isLightFamily }" in theme
    print("PASS: icon catalog references resolve")


if __name__ == "__main__":
    main()
