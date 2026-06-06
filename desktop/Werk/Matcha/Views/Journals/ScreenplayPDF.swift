import AppKit
import CoreGraphics
import CoreText
import Foundation

/// Renders a parsed screenplay to a standard-format PDF via Core Text: a title
/// page (when present) then paginated body pages, Courier 12, US-Letter, with
/// scene numbers in the margins and page numbers top-right. Layout comes from
/// `ScreenplayPaginator` so it matches the on-screen page view.
enum ScreenplayPDF {

    static func render(_ doc: ScreenplayDocument) -> Data? {
        let data = NSMutableData()
        guard let consumer = CGDataConsumer(data: data as CFMutableData) else { return nil }
        var box = CGRect(x: 0, y: 0,
                         width: ScreenplayPageMetrics.pageWidth,
                         height: ScreenplayPageMetrics.pageHeight)
        guard let ctx = CGContext(consumer: consumer, mediaBox: &box, nil) else { return nil }

        if !doc.titlePage.isEmpty { drawTitlePage(ctx, doc.titlePage) }
        for page in ScreenplayPaginator.paginate(doc) { drawBodyPage(ctx, page) }

        ctx.closePDF()
        return data as Data
    }

    // MARK: - Pages

    private static func drawBodyPage(_ ctx: CGContext, _ page: ScreenplayPage) {
        let M = ScreenplayPageMetrics.self
        ctx.beginPDFPage(nil)

        if page.number > 1 {
            let label = "\(page.number)."
            let tw = CGFloat(label.count) * M.charWidth
            drawText(label, x: M.pageWidth - M.marginRight - tw, y: M.pageHeight - 36, ctx)
        }

        var row = 0
        for line in page.lines {
            defer { row += 1 }
            guard !line.isBlank else { continue }
            let y = M.pageHeight - M.marginTop - CGFloat(row) * M.lineHeight - 9   // baseline
            let tw = CGFloat(line.text.count) * M.charWidth
            let x: CGFloat
            switch line.element {
            case .transition: x = M.pageWidth - M.marginRight - tw
            case .centered:   x = (M.pageWidth - tw) / 2
            default:          x = M.leftInset(line.element)
            }
            drawText(line.text, x: x, y: y, bold: line.element == .sceneHeading, ctx)
            if let scene = line.sceneNumber {
                drawText(scene, x: 54, y: y, ctx)
                drawText(scene, x: M.pageWidth - M.marginRight + 14, y: y, ctx)
            }
        }
        ctx.endPDFPage()
    }

    private static func drawTitlePage(_ ctx: CGContext, _ tp: ScreenplayTitlePage) {
        let M = ScreenplayPageMetrics.self
        ctx.beginPDFPage(nil)
        let cx = M.pageWidth / 2

        func centered(_ s: String, y: CGFloat, bold: Bool = false) {
            guard !s.isEmpty else { return }
            let tw = CGFloat(s.count) * M.charWidth
            drawText(s, x: cx - tw / 2, y: y, bold: bold, ctx)
        }
        centered(tp.title.uppercased(), y: 540, bold: true)
        centered(tp.credit, y: 500)
        centered(tp.author, y: 480)
        centered(tp.source, y: 446)
        if !tp.contact.isEmpty {
            drawText(tp.contact, x: M.marginLeft, y: 96, ctx)
        }
        if !tp.draftDate.isEmpty {
            let tw = CGFloat(tp.draftDate.count) * M.charWidth
            drawText(tp.draftDate, x: M.pageWidth - M.marginRight - tw, y: 96, ctx)
        }
        ctx.endPDFPage()
    }

    // MARK: - Text

    private static func drawText(_ s: String, x: CGFloat, y: CGFloat, bold: Bool = false, _ ctx: CGContext) {
        guard !s.isEmpty else { return }
        let font = NSFont(name: bold ? "Courier-Bold" : "Courier", size: 12)
            ?? .monospacedSystemFont(ofSize: 12, weight: bold ? .bold : .regular)
        let attr = NSAttributedString(string: s, attributes: [
            .font: font,
            .foregroundColor: NSColor.black,
        ])
        let line = CTLineCreateWithAttributedString(attr)
        ctx.textMatrix = .identity
        ctx.textPosition = CGPoint(x: x, y: y)
        CTLineDraw(line, ctx)
    }
}
