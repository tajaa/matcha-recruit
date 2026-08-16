import SwiftUI
import UIKit

struct TemplateGalleryView: View {
    let templates: [FlyerTemplateAsset]
    let assets: FlyerRenderAssets
    let onPick: (FlyerTemplateAsset) -> Void
    @Environment(\.dismiss) private var dismiss

    private var groups: [(String, [FlyerTemplateAsset])] {
        let grouped = Dictionary(grouping: templates) { $0.manifest.theme ?? "Essentials" }
        return grouped.keys.sorted { lhs, rhs in
            if lhs == "Essentials" { return true }
            if rhs == "Essentials" { return false }
            return lhs < rhs
        }.map { ($0, grouped[$0] ?? []) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 24) {
                    ForEach(groups, id: \.0) { theme, entries in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(theme)
                                .font(.interHeadline)
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                                ForEach(entries) { template in
                                    Button {
                                        onPick(template)
                                        dismiss()
                                    } label: {
                                        VStack(alignment: .leading, spacing: 8) {
                                            FlyerTemplatePreview(design: template.design, assets: assets)
                                                .aspectRatio(template.design.artboard.w / template.design.artboard.h, contentMode: .fit)
                                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                            Text(template.manifest.name)
                                                .font(.interFootnote)
                                                .foregroundStyle(.primary)
                                                .lineLimit(1)
                                        }
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Choose a style")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
}

private struct FlyerTemplatePreview: UIViewRepresentable {
    let design: FlyerDesign
    let assets: FlyerRenderAssets

    func makeUIView(context: Context) -> FlyerTemplatePreviewView {
        FlyerTemplatePreviewView()
    }

    func updateUIView(_ view: FlyerTemplatePreviewView, context: Context) {
        view.design = design
        view.assets = assets
        view.setNeedsDisplay()
    }
}

private final class FlyerTemplatePreviewView: UIView {
    var design = FlyerDesignFactory.blank()
    var assets = FlyerRenderAssets.bundled

    override func draw(_ rect: CGRect) {
        guard let context = UIGraphicsGetCurrentContext() else { return }
        let scale = min(bounds.width / CGFloat(design.artboard.w), bounds.height / CGFloat(design.artboard.h))
        let width = CGFloat(design.artboard.w) * scale
        let height = CGFloat(design.artboard.h) * scale
        context.saveGState()
        context.translateBy(x: (bounds.width - width) / 2, y: (bounds.height - height) / 2)
        context.scaleBy(x: scale, y: scale)
        FlyerRenderer.draw(design: design, claimURL: nil, assets: assets, in: context)
        context.restoreGState()
    }
}
