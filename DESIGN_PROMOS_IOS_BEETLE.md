Tell-Us: phone-native promo design system on iOS │
│ │
│ Context │
│ │
│ A brand should design and distribute a promo entirely from their phone — the motivating case being a Venice smoothie shop making a beach-themed promo, then sending it either to their Locals club board or as a push to nearby followers. │
│ │
│ A full iOS flyer designer already exists and reads/writes the same design*json as the web Konva designer: platforms/ios/TellUs/Views/Brand/Campaigns/Designer/{CampaignDesignerView,FlyerCanvasView,FlyerCanvasGeometry,FlyerRenderer,FlyerAssistantPanel}.swift, Models/FlyerDesign.swift + FlyerDesign+Editor.swift, ViewModels/FlyerDesignerViewModel.swift + FlyerDocumentStore.swift, Services/{FlyerAssetCatalog,FlyerExportService,FlyerAiService}.swift, 8 test files. It already does drag-to-move, corner-handle resize, snapping, undo/redo, autosave, CoreImage QR, PNG export at 150/300dpi, and AI assist. Four targeted gaps, not a greenfield build. │
│ │
│ 1. Unreachable for location campaigns. Only entry to CampaignDesignerView is CampaignQRSheet.swift:31; the earlier location-campaign QR fix made that sheet unopenable for campaign_type == "location", so those campaigns lost all designer access. Regression. │
│ 2. No pinch, no rotate. FlyerCanvasUIView registers exactly one recognizer — UIPanGestureRecognizer with maximumNumberOfTouches = 1 (FlyerCanvasView.swift:38-51). Rotation is only settable through a numeric TextField. Free scaling exists only via corner handles. │
│ 3. No themed content. 4 generic templates, 5 generic palettes, 8 generic stickers. Nothing beach/seasonal/vertical. │
│ 4. Design disconnected from distribution. tellus_board_posts.kind is CHECK (kind IN ('update','deal','event','question')) with no image and no campaign FK; deal attaches a reward listing. No way to put a promo on the Locals board. │
│ │
│ Decisions: four phases as sequential commits; theming via hand-authored packs and AI remix; Locals distribution as a real campaign↔post link; four packs (beach/summer, grand opening, holiday/festive, happy hour). │
│ │
│ Cross-cutting invariants │
│ │
│ - design_json has three renderers (web Konva, iOS CoreGraphics, server flyer_ai validator). Artboard/print px @150dpi, top-left origin, rotation in degrees, z-order = array index. Colour fields accept a palette token or hex. │
│ - DesignLayer.unknown(id:raw:) round-trips verbatim — never break it. │
│ - Asset packs are duplicated and parity-pinned. tests/tellus/test_flyer_ai.py::test_sticker_ids_match_the_web_pack and ::test_palette_presets_match_the_web_pack read the web pack off disk and compare to Python. They fail on drift by design. │
│ - Server never renders design_json. flyer_image_url is a client-uploaded raster; saving a design does not refresh it. │
│ - Server field ranges (services/flyer_ai/catalog.py:113-160) are the real clamp bounds: x/y ±4000, rotation ±180, opacity 0.05–1, text fontSize 8–400 / width 24–4000 / lineHeight 0.7–3.0 / letterSpacing −20–80 / text ≤400 chars, shape width 4–4000 / height 2–4000 / strokeWidth 0–64 / cornerRadius 0–400, sticker+image 8–4000, qr size 96–2000. │
│ - DB rule: author + commit the migration; do not run it against any database without explicit approval. │
│ │
│ --- │
│ Phase 0 — designer reachability │
│ │
│ platforms/ios/TellUs/Views/Brand/Campaigns/CampaignsView.swift │
│ │
│ private enum CampaignSheet: Identifiable { │
│ case create │
│ case qr(PromoCampaign) │
│ case design(PromoCampaign) // NEW │
│ │
│ var id: String { │
│ switch self { │
│ case .create: return "create" │
│ case .qr(let c): return "qr-\(c.id)" │
│ case .design(let c): return "design-\(c.id)" │
│ } │
│ } │
│ } │
│ │
│ In .sheet(item: $sheet): │
│ case .design(let campaign): │
│ NavigationStack { CampaignDesignerView(campaignID: campaign.id) } │
│ │
│ In CampaignListItem.body, below the row and above pushStatus, unconditional for both campaign types: │
│ Button { sheet = .design(campaign) } label: { │
│ Label(campaign.has_design ? "Edit flyer" : "Design flyer", systemImage: "paintbrush") │
│ } │
│ .buttonStyle(.bordered) │
│ .controlSize(.small) │
│ CampaignListItem already takes @Binding var sheet: CampaignSheet?. Leave the QR-sheet tap location-gated as-is; the duplicate "Design flyer" link inside CampaignQRSheet stays (harmless). │
│ │
│ Test: Tests/CampaignSheetTests.swift (new) — CampaignSheet.design(c).id == "design-\(c.id)" and that it differs from .qr(c).id for the same campaign (a collision would make SwiftUI reuse the wrong sheet). │
│ │
│ --- │
│ Phase 1 — themed content packs │
│ │
│ 1a. Palettes — two files, one commit │
│ │
│ client/tellus/public/designer/palettes.json — append objects {key, label, blurb, colors:{ink,paper,brand,brandSoft,accent,muted}}. │
│ │
│ server/app/tellus/services/flyer_ai/palettes.py — append matching PalettePreset(key=, label=, blurb=, colors={...}) to the PALETTES tuple. The module-level assert all(set(p.colors) == set(PALETTE_TOKENS) ...) at the bottom enforces exactly the six tokens; values must be hex. │
│ │
│ ┌───────────────────┬──────────────┬─────────┬─────────┬─────────┬───────────┬─────────┬─────────┐ │
│ │ key │ label │ ink │ paper │ brand │ brandSoft │ accent │ muted │ │
│ ├───────────────────┼──────────────┼─────────┼─────────┼─────────┼───────────┼─────────┼─────────┤ │
│ │ ocean-breeze │ Ocean breeze │ #0b3a4a │ #eef7fa │ #0e9bbd │ #67c7dc │ #f4a259 │ #7fa3ae │ │
│ ├───────────────────┼──────────────┼─────────┼─────────┼─────────┼───────────┼─────────┼─────────┤ │
│ │ sunset-strip │ Sunset strip │ #2b1330 │ #fff1e6 │ #ef5d60 │ #f79489 │ #ffb703 │ #a3798f │ │
│ ├───────────────────┼──────────────┼─────────┼─────────┼─────────┼───────────┼─────────┼─────────┤ │
│ │ evergreen-festive │ Evergreen │ #0e2a1e │ #f4f1e8 │ #b3202e │ #d4626c │ #1f7a4d │ #7e8a80 │ │
│ ├───────────────────┼──────────────┼─────────┼─────────┼─────────┼───────────┼─────────┼─────────┤ │
│ │ neon-night │ Neon night │ #f2e9ff │ #120d1c │ #c026d3 │ #e879f9 │ #22d3ee │ #7c6f91 │ │
│ └───────────────────┴──────────────┴─────────┴─────────┴─────────┴───────────┴─────────┴─────────┘ │
│ │
│ Contrast sanity: catalog.relative_luminance already exists — reuse it in the new test rather than hand-checking. │
│ │
│ 1b. Stickers — three touch points each │
│ │
│ Author flat 200×200 SVGs matching the existing 8 (solid fills, no gradients, viewBox="0 0 200 200", single colour). │
│ │
│ New ids: sun, wave, palm, ice-cream, confetti, balloon, snowflake, holly, cocktail, moon. │
│ │
│ Per sticker: │
│ 1. client/tellus/public/designer/stickers/<id>.svg + entry in that dir's index.json: { "id": "<id>", "file": "<id>.svg", "thumb": "<id>.svg", "w": 200, "h": 200 } │
│ 2. platforms/ios/TellUs/Resources/Assets.xcassets/sticker-<id>.imageset/ containing the same <id>.svg plus Contents.json copied verbatim from sticker-star.imageset/Contents.json (keep "preserves-vector-representation": true, "template-rendering-intent": "original"). No pbxproj edit — Assets.xcassets is a single folder.assetcatalog fileRef (pbxproj line 299). │
│ 3. platforms/ios/TellUs/Services/FlyerAssetCatalog.swift → add "<id>.svg": "sticker-<id>" to static let stickerImageNames, and server/app/tellus/services/flyer_ai/catalog.py → add "<id>.svg" to STICKER_IDS. │
│ │
│ 1c. Themed templates + making the palette actually apply │
│ │
│ Template JSON in both client/tellus/public/designer/templates/<id>.json and platforms/ios/TellUs/Resources/FlyerDesigner/templates/<id>.json, with an entry appended to each index.json. │
│ │
│ Manifest entry gains a theme field: │
│ { "id": "beach-day", "name": "Beach day", "preset": "flyer_letter", │
│ "file": "beach-day.json", "thumb": null, "theme": "beach-summer" } │
│ Existing four get "theme": null → grouped as "Essentials". │
│ │
│ - client/tellus/src/api/types.ts → TemplateManifestEntry gains theme: string | null. │
│ - platforms/ios/TellUs/Models/FlyerDesign.swift → FlyerTemplateManifestEntry gains let theme: String? (optional so an older pack still decodes). │
│ │
│ Unlike the existing four, a themed template ships its own palette — that's what makes it look themed. Layers stay in tokens, never hex, so a later palette swap still reads correctly. Two code changes are required for that palette to survive instantiation: │
│ │
│ client/tellus/src/utils/designer.ts — instantiateTemplate(template: FlyerDesign, logoUrl: string | null): FlyerDesign currently rebuilds the doc without palette. Add ...(template.palette ? { palette: template.palette } : {}) to the returned object. │
│ │
│ platforms/ios/TellUs/Models/FlyerDesign+Editor.swift — FlyerDesignFactory.instantiate(* template: FlyerDesign, logoURL: String?) -> FlyerDesign must carry template.palette onto its result (same one-line omission). │
│ │
│ Templates to author (one per pack, flyer*letter unless noted): │
│ │
│ ┌────────────────────┬─────────────────┬───────────────────┬───────────────────────────────────────────────────┐ │
│ │ file │ theme │ palette │ notes │ │
│ ├────────────────────┼─────────────────┼───────────────────┼───────────────────────────────────────────────────┤ │
│ │ beach-day.json │ beach-summer │ ocean-breeze │ sun + wave stickers, big condensed headline, QR │ │
│ │ │ │ │ bottom-right │ │
│ ├────────────────────┼─────────────────┼───────────────────┼───────────────────────────────────────────────────┤ │
│ │ grand-opening.json │ grand-opening │ sunset-strip │ starburst behind headline, "NOW OPEN" │ │
│ ├────────────────────┼─────────────────┼───────────────────┼───────────────────────────────────────────────────┤ │
│ │ festive-night.json │ holiday-festive │ evergreen-festive │ holly/snowflake corners │ │
│ ├────────────────────┼─────────────────┼───────────────────┼───────────────────────────────────────────────────┤ │
│ │ happy-hour.json │ happy-hour │ neon-night │ social_square preset, cocktail sticker │ │
│ └────────────────────┴─────────────────┴───────────────────┴───────────────────────────────────────────────────┘ │
│ │
│ pbxproj: template JSONs are individually referenced (12 grep hits for the current 4 = 3 entries each). Each new .json needs: a PBXBuildFile, a PBXFileReference, membership in the FlyerDesigner/templates group children (pbxproj group B416530E7E2B2926AACE5CB7), and the Resources build phase (not Sources). Then plutil -lint platforms/ios/TellUs/TellUs.xcodeproj/project.pbxproj. │
│ │
│ 1d. AI reach │
│ │
│ New palettes/stickers become model-selectable automatically (PALETTES, STICKER_IDS). Optionally add one themed entry per pack to services/flyer_ai/layouts.py — those must use tokens only and validate under every palette. │
│ │
│ Phase 1 tests │
│ │
│ server/tests/tellus/test_flyer_ai.py (existing, must stay green): │
│ - test_palette_presets_match_the_web_pack, test_every_palette_defines_exactly_the_tokens, test_every_palette_value_is_hex, test_sticker_ids_match_the_web_pack, test_every_layout_validates_under_every_palette. │
│ │
│ New, server/tests/tellus/test_flyer_packs.py: │
│ - test_every_template_index_entry_has_a_file — for both client/tellus/public/designer/templates/index.json and the iOS copy, every file exists on disk. │
│ - test_ios_and_web_template_packs_match — the two index.jsons are equal as parsed JSON, and each same-named template file parses to an equal document (whitespace-insensitive). │
│ - test_themed_templates_declare_a_known_palette_and_only_tokens — for each template with theme != null: it has a palette key covering exactly the six tokens, and no layer colour field is a hex literal (all must be tokens). │
│ - test_every_template_layer_is_inside_the_artboard — reuse catalog's bounds logic. │
│ - test_template_stickers_are_in_the_catalog — every assetId in every template ∈ STICKER_IDS. │
│ - test_palette_ink_paper_contrast_is_legible — relative_luminance ratio ≥ 4.5 for ink-on-paper in every palette. │
│ │
│ New, platforms/ios/TellUs/Tests/FlyerAssetCatalogTests.swift (extend existing): │
│ - testStickerImageNamesCoverTheWebPack — FlyerAssetCatalog.stickerImageNames.keys equals the set from the web index.json (file values), mirroring the Python parity test. │
│ - testEveryBundledTemplateDecodes — try FlyerAssetCatalog().templates() returns one entry per index.json row and each design.layers is non-empty. │
│ - testInstantiateCarriesTemplatePalette — a template with a palette survives FlyerDesignFactory.instantiate(*:logoURL:). │
│ │
│ --- │
│ Phase 2 — phone-native designer UX │
│ │
│ 2a. Gestures — Views/Brand/Campaigns/Designer/FlyerCanvasView.swift │
│ │
│ Add to FlyerCanvasUIView, alongside the existing pan: │
│ │
│ private var pinch: UIPinchGestureRecognizer! │
│ private var rotate: UIRotationGestureRecognizer! │
│ private var doubleTap: UITapGestureRecognizer! │
│ private var gestureBaseLayer: DesignLayer? // snapshot at .began, so scale/rotation are absolute not cumulative │
│ │
│ In init(frame:): │
│ pinch = UIPinchGestureRecognizer(target: self, action: #selector(handlePinch(_:))) │
│ rotate = UIRotationGestureRecognizer(target: self, action: #selector(handleRotate(_:))) │
│ doubleTap = UITapGestureRecognizer(target: self, action: #selector(handleDoubleTap(_:))) │
│ doubleTap.numberOfTapsRequired = 2 │
│ [pinch, rotate, doubleTap].forEach { $0.delegate = self; addGestureRecognizer($0) } │
│ FlyerCanvasUIView: UIGestureRecognizerDelegate with │
│ func gestureRecognizer(_ g: UIGestureRecognizer, │
│ shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool { │
│ (g === pinch && other === rotate) || (g === rotate && other === pinch) │
│ } │
│ so pinch+rotate compose but neither fights the single-touch pan. update(...) must also set pinch.isEnabled = interactive / rotate.isEnabled = interactive. │
│ │
│ New callback on FlyerCanvasView (the UIViewRepresentable) and threaded through update(...): │
│ let onBeginTextEdit: (String) -> Void // layer id │
│ │
│ Handlers — both snapshot at .began, emit commit: false on .changed, commit: true on .ended, matching the pan contract so one gesture = one undo step: │
│ │
│ @objc private func handlePinch(_ r: UIPinchGestureRecognizer) { │
│ guard interactive, let id = selectedLayerID else { return } │
│ switch r.state { │
│ case .began: │
│ gestureBaseLayer = design.layers.first { $0.id == id && !$0.isLocked } │
│ case .changed, .ended: │
│ guard let base = gestureBaseLayer else { return } │
│ let box = base.box │
│ let changed = FlyerCanvasGeometry.scaled(base, by: r.scale) // NEW, see below │
│ onLayerChange?(changed, r.state == .ended) │
│ if r.state == .ended { gestureBaseLayer = nil } │
│ default: gestureBaseLayer = nil │
│ } │
│ } │
│ │
│ @objc private func handleRotate(_ r: UIRotationGestureRecognizer) { │
│ guard interactive, let id = selectedLayerID else { return } │
│ // QR rotation is disabled for scan reliability — web disables it too. │
│ switch r.state { │
│ case .began: │
│ let candidate = design.layers.first { $0.id == id && !$0.isLocked } │
│ gestureBaseLayer = candidate?.kind == "qr" ? nil : candidate │
│ case .changed, .ended: │
│ guard let base = gestureBaseLayer else { return } │
│ let degrees = base.rotation + Double(r.rotation) _ 180 / .pi │
│ onLayerChange?(base.withRotation(FlyerCanvasGeometry.snapRotation(degrees)), r.state == .ended) │
│ if r.state == .ended { gestureBaseLayer = nil } │
│ default: gestureBaseLayer = nil │
│ } │
│ } │
│ │
│ @objc private func handleDoubleTap(* r: UITapGestureRecognizer) { │
│ guard interactive else { return } │
│ let point = pointInArtboard(r.location(in: self)) │
│ guard let id = FlyerCanvasGeometry.hitTest(at: point, in: design), │
│ case .text = design.layers.first(where: { $0.id == id }) else { return } │
│ onSelect?(id) │
│ onBeginTextEdit(id) │
│ } │
│ │
│ 2b. Geometry + clamping — FlyerCanvasGeometry.swift and FlyerDesign+Editor.swift │
│ │
│ withSize(width:height:) currently floors at the iOS minimums (24/8/4/2/96) but has no upper bound — a two-finger spread can author width: 99999, which flyer_ai's validator would reject (4000 ceiling) and which no export can render. Add the ceilings. │
│ │
│ FlyerDesign+Editor.swift — new, mirroring catalog.py: │
│ enum FlyerLayerLimits { │
│ static let position = -4000.0...4000.0 │
│ static let rotation = -180.0...180.0 │
│ static let opacity = 0.05...1.0 │
│ static let textFontSize = 8.0...400.0 │
│ static let textWidth = 24.0...4000.0 │
│ static let shapeWidth = 4.0...4000.0 │
│ static let shapeHeight = 2.0...4000.0 │
│ static let boxSide = 8.0...4000.0 // sticker + image │
│ static let qrSize = 96.0...2000.0 │
│ } │
│ Apply the upper bound in every withSize branch (min(max(...))), and clamp in withRotation/withOpacity too. │
│ │
│ FlyerCanvasGeometry.swift — two new pure functions, unit-testable without a view: │
│ /// Scales a layer about its CENTRE by `factor`, clamped to FlyerLayerLimits. │
│ /// Text scales fontSize and width together; qr scales `size`; everything else │
│ /// scales width/height and keeps aspect. │
│ static func scaled(* layer: DesignLayer, by factor: Double) -> DesignLayer │
│ │
│ /// Snaps to the nearest of 0/±90/±180 when within `detent` degrees, else │
│ /// returns `degrees` normalised into -180...180. │
│ static func snapRotation(* degrees: Double, detent: Double = 6) -> Double │
│ │
│ 2c. CampaignDesignerView.swift restructure │
│ │
│ Replace the horizontal toolbar-of-menus + numeric inspector with three surfaces. Keep FlyerDesignerViewModel's document/history/autosave contract, the assistant panel, and the export sheet unchanged. │
│ │
│ New file Designer/TemplateGalleryView.swift: │
│ struct TemplateGalleryView: View { │
│ let templates: [FlyerTemplateAsset] │
│ let assets: FlyerRenderAssets │
│ let onPick: (FlyerTemplateAsset) -> Void │
│ // Groups by manifest.theme (nil -> "Essentials"), renders each as a live │
│ // miniature via FlyerRenderer (claimURL: nil -> dashed QR placeholder), │
│ // same honest-preview approach as web's TemplatePreview. │
│ } │
│ Shown full-screen on first open when vm.document.design.layers.isEmpty, and reachable later from a "Restyle" toolbar button. │
│ │
│ New file Designer/LayerInspectorBar.swift: contextual bottom bar, switching on the selected layer kind — │
│ - .text → inline TextField bound to the live layer (no separate "Apply" button), font-family chips from the 5 portable families, size Stepper, colour swatches drawn from design.palette ?? DEFAULT_FLYER_PALETTE. │
│ - .sticker / .shape → size slider + swatches. │
│ - .qr → fg/bg swatches only. │
│ - .image → opacity + replace. │
│ │
│ Numeric X/Y/W/H/rotation fields move verbatim into a collapsed DisclosureGroup("Precise") — gesture-only editing is unusable with motor impairments, so they stay reachable, just off the default path. │
│ │
│ 2d. AI remix — FlyerAssistantPanel.swift │
│ │
│ Replace the fixed quickPrompts array with theme-seeded prompts: │
│ static func quickPrompts(theme: String?) -> [String] │
│ e.g. beach-summer → "Make it feel like sunset", "Add a wave along the bottom", "Bigger, bolder headline", "Move the QR bottom-right". Server needs nothing new. │
│ │
│ Phase 2 tests — Tests/FlyerCanvasGeometryTests.swift (extend) │
│ │
│ - testScaledKeepsLayerCentre — centre before == centre after for factor 2 and 0.5. │
│ - testScaledClampsToUpperBound — factor 100 on a sticker leaves width <= 4000. │
│ - testScaledClampsToLowerBound — factor 0.001 leaves width >= 8. │
│ - testScaledTextScalesFontSizeAndWidthTogether — ratio preserved. │
│ - testScaledQRStaysSquare — box.width == box.height. │
│ - testSnapRotationSnapsNearRightAngles — snapRotation(88) == 90, snapRotation(3) == 0, snapRotation(45) == 45. │
│ - testSnapRotationNormalisesBeyond180 — snapRotation(200) == -160. │
│ - testWithSizeRejectsOutOfRangeForServer — assert every withSize output sits inside FlyerLayerLimits, i.e. would pass catalog.py's validator. │
│ │
│ --- │
│ Phase 3 — post a promo to the Locals board │
│ │
│ 3a. Migration — server/alembic/versions/tellus_app_27_board_promo_posts.py │
│ │
│ revision = "tellus_app_27", down_revision = "tellus_app_26" (current head, verified). │
│ │
│ def upgrade(): │
│ op.execute(""" │
│ ALTER TABLE tellus_board_posts │
│ ADD COLUMN IF NOT EXISTS campaign_id UUID │
│ REFERENCES tellus_promo_campaigns(id) ON DELETE SET NULL │
│ """) │
│ # The kind CHECK was created inline in tellus_app_12, so Postgres named it │
│ # <table>*<column>\_check. Drop and recreate to admit 'promo'. │
│ op.execute("ALTER TABLE tellus_board_posts DROP CONSTRAINT IF EXISTS tellus_board_posts_kind_check") │
│ op.execute(""" │
│ ALTER TABLE tellus_board_posts ADD CONSTRAINT tellus_board_posts_kind_check │
│ CHECK (kind IN ('update','deal','event','question','promo')) │
│ """) │
│ op.execute(""" │
│ CREATE INDEX IF NOT EXISTS ix_tellus_board_posts_campaign │
│ ON tellus_board_posts (campaign_id) WHERE campaign_id IS NOT NULL │
│ """) │
│ │
│ def downgrade(): │
│ # Rows using the new kind must go first or the narrowed CHECK fails. │
│ op.execute("DELETE FROM tellus_board_posts WHERE kind = 'promo'") │
│ op.execute("DROP INDEX IF EXISTS ix_tellus_board_posts_campaign") │
│ op.execute("ALTER TABLE tellus_board_posts DROP COLUMN IF EXISTS campaign_id") │
│ op.execute("ALTER TABLE tellus_board_posts DROP CONSTRAINT IF EXISTS tellus_board_posts_kind_check") │
│ op.execute(""" │
│ ALTER TABLE tellus_board_posts ADD CONSTRAINT tellus_board_posts_kind_check │
│ CHECK (kind IN ('update','deal','event','question')) │
│ """) │
│ Set-based, idempotent, real downgrade. Rehearse with MIGRATE_REHEARSAL=1. Commit before applying anywhere; apply only on explicit approval. │
│ │
│ 3b. Models — server/app/tellus/models/tellus.py │
│ │
│ BoardPostKind = Literal["update", "deal", "event", "question", "promo"] # line 23 │
│ │
│ class TellusBoardPostCampaign(BaseModel): │
│ id: UUID │
│ title: str │
│ reward_text: str │
│ flyer_image_url: Optional[str] = None │
│ claim_url: str │
│ status: str │
│ campaign_type: Optional[str] = None │
│ TellusBoardPostCreate gains campaign_id: Optional[UUID] = None and the validator extends: │
│ @model_validator(mode="after") │
│ def \_kind_needs_its_attachment(self): │
│ if self.kind == "deal" and self.listing_id is None: │
│ raise ValueError("A deal post needs a listing_id") │
│ if self.kind == "promo" and self.campaign_id is None: │
│ raise ValueError("A promo post needs a campaign_id") │
│ return self │
│ TellusBoardPost gains campaign: Optional[TellusBoardPostCampaign] = None # embedded for kind='promo'. │
│ │
│ 3c. Route — server/app/tellus/routes/board.py:create_post │
│ │
│ Mirror the existing deal/listing_id block exactly: │
│ campaign_row = None │
│ if body.kind == "promo": │
│ campaign_row = await conn.fetchrow( │
│ "SELECT id, title, reward_text, flyer_image_url, claim_token, status, campaign_type " │
│ "FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2", │
│ body.campaign_id, brand["id"], │
│ ) │
│ if campaign_row is None or campaign_row["status"] == "cancelled": │
│ raise HTTPException( │
│ status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, │
│ detail="Pick an active campaign of your own", │
│ ) │
│ │
│ # Same rule as listing_id: only a validated campaign may attach, so a │
│ # non-promo post can't carry an unvalidated (possibly cross-brand) id. │
│ campaign_id = body.campaign_id if body.kind == "promo" else None │
│ Add campaign_id to the INSERT column list + $10, and pass campaign_row=campaign_row to both bs.serialize_post(...) calls in this file (create at ~line 617 and the sibling at ~673). │
│ │
│ 3d. Serializer — server/app/tellus/services/board_service.py │
│ │
│ def serialize_post(row, _, viewer_is_mod: bool, listing_row=None, campaign_row=None) -> TellusBoardPost: │
│ adding │
│ campaign=( │
│ TellusBoardPostCampaign( │
│ id=campaign_row["id"], │
│ title=campaign_row["title"], │
│ reward_text=campaign_row["reward_text"], │
│ flyer_image_url=campaign_row["flyer_image_url"], │
│ claim_url=f"/tellus/p/{campaign_row['claim_token']}", │
│ status=campaign_row["status"], │
│ campaign_type=campaign_row["campaign_type"], │
│ ) if campaign_row is not None else None │
│ ), │
│ claim_url is built here rather than selected, matching how promo_service mints it from claim_token. │
│ │
│ List path (routes/board.py:268-287) — batch exactly like listings_by_id, no N+1: │
│ campaign_ids = [r["campaign_id"] for r in rows if r["campaign_id"] is not None] │
│ campaigns_by_id = {} │
│ if campaign_ids: │
│ crows = await conn.fetch( │
│ "SELECT id, title, reward_text, flyer_image_url, claim_token, status, campaign_type " │
│ "FROM tellus_promo_campaigns WHERE id = ANY($1::uuid[]) AND brand_id = $2", │
│ campaign_ids, brand["id"], │
│ ) │
│ campaigns_by_id = {r["id"]: r for r in crows} │
│ then pass campaign_row=campaigns_by_id.get(r["campaign_id"]) into the serialize_post comprehension. │
│ │
│ notify_board_members already fires for every post — Locals get their notification free, no change. │
│ │
│ 3e. Clients │
│ │
│ iOS Models/Enums.swift: enum BoardPostKind { case update, deal, event, question, promo, unknown } — it's FallbackDecodable, so older builds degrade to .unknown instead of failing the list. │
│ │
│ iOS Models/BoardModels.swift: BoardPostCreate gains let campaign_id: String?; BoardPost gains let campaign: BoardPostCampaign? plus │
│ struct BoardPostCampaign: Codable, Hashable { │
│ let id: String │
│ let title: String │
│ let reward_text: String │
│ let flyer_image_url: String? │
│ let claim_url: String │
│ let status: String │
│ let campaign_type: String? │
│ } │
│ │
│ iOS ComposePostSheet.swift: leave composableKinds: [.update, .event, .question] untouched — promo posts are authored from the campaign/designer side, not the generic composer. │
│ │
│ iOS new Designer/ShareCampaignSheet.swift: presented from CampaignDesignerView's export sheet and from CampaignListItem: │
│ struct ShareCampaignSheet: View { │
│ let campaign: PromoCampaign │
│ let onPostedToLocals: () -> Void │
│ } │
│ Two destinations — │
│ - Post to Locals → BoardService.shared.createPost(BoardPostCreate(kind: "promo", title:, body:, listing_id: nil, campaign_id: campaign.id, ...)). Prefill title from campaign.title. │
│ - Push to nearby → the existing one-shot PromoService.shared.pushCampaign(id:), shown only for campaign_type == "location" with push_sent_at == nil, reusing the confirm alert added earlier. │
│ Plus the existing "Share PNG" / "Use as campaign flyer" actions. │
│ │
│ Web parity (a kind the phone can author must not break the web feed): │
│ - client/tellus/src/api/types.ts → BoardPostKind gains 'promo'; BoardPost gains campaign: BoardPostCampaign | null + the new interface. │
│ - client/tellus/src/components/BoardPostCard.tsx → KIND_LABEL is Record<BoardPost['kind'], string>, so tsc fails until a promo: 'Promo' entry is added — a compile-enforced touchpoint. Add a render branch for post.kind === 'promo' && post.campaign showing the flyer image + a claim link, alongside the existing deal branch. │
│ │
│ Phase 3 tests — server/tests/tellus/test_board_logic.py (extend) │
│ │
│ Model-level (no DB): │
│ - test_promo_kind_without_campaign_id_is_rejected — TellusBoardPostCreate(kind="promo", title="x") raises ValidationError. │
│ - test_deal_validator_still_requires_listing_id — the existing rule didn't regress. │
│ - test_non_promo_kind_may_omit_campaign_id. │
│ - test_serialize_post_embeds_campaign_only_for_promo — serialize_post(row, viewer_is_mod=False, campaign_row=None).campaign is None; with a campaign row, claim_url == "/tellus/p/<token>". │
│ │
│ Source-guard (the file's existing idiom — inspect.getsource): │
│ - test_create_post_force_nulls_campaign_id_for_non_promo — asserts the body.campaign_id if body.kind == "promo" else None line exists, same shape as the listing guard. │
│ - test_list_posts_batches_campaign_lookup — asserts = ANY($1::uuid[]) appears in the campaign fetch, i.e. no per-row query. │
│ │
│ Migration: │
│ - test_migration_chain_is_single_headed — if such a test exists in the repo, confirm tellus_app_27 extends the chain cleanly; else verify by hand with alembic heads. │
│ │
│ Explicitly out of scope: push-notification images. services/push.py:206-212 sends a plain aps alert with no mutable-content, so an APNs image attachment needs a Notification Service Extension target — separate work. │
│ │
│ --- │
│ Verification │
│ │
│ Per phase, before moving to the next: │
│ │
│ cd server && ./venv/bin/python -m pytest tests/tellus -q # 397 green today │
│ cd client/tellus && npx tsc -p tsconfig.app.json --noEmit # NOT bare `npx tsc --noEmit` — checks nothing │
│ plutil -lint platforms/ios/TellUs/TellUs.xcodeproj/project.pbxproj │
│ xcodebuild -project platforms/ios/TellUs/TellUs.xcodeproj -scheme TellUs \ │
│ -destination 'platform=iOS Simulator,name=iPhone 16' build │
│ │
│ End-to-end against the running dev-remote.sh (backend :8001, frontend :5174) as tessu2022+brand@gmail.com / TellUsBrandTest!2026 (local dev only): │
│ │
│ 1. Phase 0 — open the existing location campaign "Test Push" (5b1b2b36-9b45-4fcd-b1ac-fe98a20d6e80); "Design flyer" reachable from its row with no QR sheet involved. │
│ 2. Phase 1 — apply "Beach day"; ocean palette renders on iOS and web (/tellus/brand/campaigns/<id>/design); PUT .../design stays under the 256KiB cap (413 otherwise). │
│ 3. Phase 2 — pinch and rotate a sticker: one gesture = one undo step, rotated layer still hit-tests, QR refuses rotation, and a hard two-finger spread cannot exceed 4000px. │
│ 4. Phase 3 — post a promo to Locals from the phone; it appears in the web consumer board feed with its flyer; members get a notification; kind:"promo" with no campaign_id → 422; another brand's campaign_id → 422. │
│ │
│ The cross-cutting check that matters most every phase: author on web → open on iOS → save → reopen on web, confirming no layer is lost (the .unknown round-trip) and no colour silently resolves to black.
