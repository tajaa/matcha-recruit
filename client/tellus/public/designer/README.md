# Designer asset pack

Served at `/tellus/designer/*` (Vite `base: '/tellus/'` publishes `public/` verbatim).
`ASSET_BASE` in `src/utils/designer.ts` is the single place that name appears — moving
this pack to S3/CloudFront later is a one-line change there.

Everything is same-origin on purpose: `stage.toDataURL()` taints on any image the
canvas can't read back, so a cross-origin sticker host would silently kill PNG export.

## `fonts/index.json`

`FontManifestEntry[]`. `file: null` means "a platform font, nothing to fetch" — the
shipped manifest is entirely system stacks so the designer works with no binaries in
the repo. To upgrade a family to a self-hosted webfont:

1. Drop a subset `.woff2` in `fonts/`.
2. Set `file` to its filename and `weight` to its real weight.

`useDesignerFonts` registers a `FontFace` for every entry that has a file and awaits
`document.fonts.load` for all of them before the stage draws or exports. No code change
is needed — that is the whole point of the null.

Licensing: only ship fonts whose licence allows web embedding (OFL/Apache). Do not add
a foundry font here without checking.

## `stickers/index.json`

`StickerManifestEntry[]`; `file` is both the filename and the `assetId` stored in the
document, so renaming a sticker file orphans it in already-saved designs. `w`/`h` are
the intrinsic dimensions used to seed the placed layer's aspect ratio.

SVG rather than webp: they scale to a 300dpi export without a 2x asset, and they are
diffable text in the repo.

## `templates/index.json`

`TemplateManifestEntry[]`, each pointing at a `FlyerDesign` JSON in the same folder.
`thumb: null` makes the picker render a live miniature of the document instead of a
baked image, so an edited template can never show a stale preview — prefer that unless
the pack grows large enough for the render cost to matter.

Template layer ids are placeholders; `instantiateTemplate()` regenerates them on apply
and swaps the brand's real logo into any `slot: "logo"` image layer (dropping that layer
entirely when the brand has no logo on file). QR layers store no URL — the campaign's
claim URL is injected at render time.
