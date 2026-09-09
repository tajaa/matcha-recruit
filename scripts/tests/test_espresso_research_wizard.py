#!/usr/bin/env python3
"""Offline macOS smoke test using the production wizard and composer sources.

Usage: python3 scripts/tests/test_espresso_research_wizard.py [preview.png]
Optional preview renders a temporary native window; no app account or API is used.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / "platforms/desktop/Espresso/Espresso"
STUBS = r'''import SwiftUI
import AppKit
@Observable final class AppState {
 var themeText: Color = .primary
 var themeAccent: Color = .indigo
}
extension Color { static let appBackground = Color(nsColor: .windowBackgroundColor) }
'''
CHECKS = r'''@main struct WizardSmoke {
 @MainActor static func main() {
  let original = "Unstructured context: café ☕\n\n## Subject\nCompare tools\n\n## Questions to answer\n1. Cost?\n2. Offline use?\n\n## Custom requirements\nKeep this exact section."
  let parsed = ResearchBriefWizard.parse(original)
  precondition(parsed.values["subject"] == "Compare tools")
  precondition(parsed.values["questions"] == "1. Cost?\n2. Offline use?")
  precondition(parsed.context.contains("café ☕"))
  precondition(parsed.context.contains("## Custom requirements\nKeep this exact section."))
  let composed = KanbanTemplate.composeDescription(fields: ResearchBriefWizard.fields, values: parsed.values)
  let roundTrip = ResearchBriefWizard.parse(composed)
  precondition(roundTrip.values == parsed.values)
  precondition(ResearchBriefWizard.parse("plain text").context == "plain text")
  precondition(ResearchBriefWizard.parse("").values.isEmpty)
  let fenced = "## Questions to answer\nKeep this example:\n```markdown\n## Subject\nnot a field\n```"
  precondition(ResearchBriefWizard.parse(fenced).values["subject"] == nil)
  precondition(ResearchBriefWizard.parse(fenced).values["questions"]?.contains("## Subject") == true)
  print("Research brief preservation and round-trip checks passed")
  guard CommandLine.arguments.count > 1 else { return }
  let app = NSApplication.shared
  app.setActivationPolicy(.accessory)
  let view = NSHostingView(rootView: ResearchBriefWizard(initialTitle: "") { _, _, _ in }.environment(AppState()).preferredColorScheme(.dark))
  let window = NSWindow(contentRect: NSRect(x:0,y:0,width:620,height:570), styleMask:[.borderless], backing:.buffered, defer:false)
  window.contentView = view
  window.orderFront(nil)
  RunLoop.main.run(until: Date().addingTimeInterval(1))
  view.layoutSubtreeIfNeeded()
  if let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
   view.cacheDisplay(in: view.bounds, to: bitmap)
   try! bitmap.representation(using:.png, properties:[:])!.write(to: URL(fileURLWithPath:CommandLine.arguments[1]))
  }
  window.orderOut(nil)
 }
}
'''


def main():
    model = (SWIFT / "Models/MatchaWork/ProjectBizModels.swift").read_text().split("enum KanbanTemplate:", 1)[1]
    wizard = (SWIFT / "Views/MatchaWork/TaskCompose.swift").read_text().split("struct ResearchBriefWizard:", 1)[1]
    composer = (SWIFT / "Views/Components/ComposerTextView.swift").read_text()
    with tempfile.TemporaryDirectory(prefix="espresso-wizard-") as directory:
        path = Path(directory)
        source = path / "Smoke.swift"
        source.write_text(STUBS + "\nenum KanbanTemplate:" + model + "\n" + composer
                          + "\nstruct ResearchBriefWizard:" + wizard + "\n" + CHECKS)
        binary = path / "smoke"
        subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-module-cache-path",
                        str(path / "cache"), str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary), *sys.argv[1:]], check=True)


if __name__ == "__main__":
    main()
