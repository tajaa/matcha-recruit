// A non-interactive miniature of a flyer document.
//
// Shared by the template picker and the assistant's Ideas grid on purpose: it
// is the SAME renderer the canvas uses, at a smaller scale, so a preview cannot
// disagree with what applying it actually produces. A baked thumbnail could.
import { Layer, Stage } from 'react-konva'
import type { FlyerDesign } from '../../api/types'
import { BackgroundNode, LayerNode } from './LayerRenderer'

export function TemplatePreview({
  design, width, stickerSrc,
}: {
  design: FlyerDesign
  width: number
  stickerSrc: (assetId: string) => string
}) {
  const scale = width / design.artboard.w
  return (
    <Stage
      width={width}
      height={Math.round(design.artboard.h * scale)}
      scaleX={scale}
      scaleY={scale}
      listening={false}
    >
      <Layer listening={false}>
        <BackgroundNode design={design} />
        {design.layers.map((l) => (
          <LayerNode
            key={l.id}
            layer={l}
            palette={design.palette}
            stickerSrc={stickerSrc}
            // No claim URL to encode at this size — LayerNode draws the QR's
            // dashed placeholder, which is the honest thing to show for a
            // document that isn't attached to a campaign yet.
            qrCanvas={() => undefined}
            draggable={false}
            listening={false}
          />
        ))}
      </Layer>
    </Stage>
  )
}
