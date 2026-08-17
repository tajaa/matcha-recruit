╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Merlin design system in platforms/ios/Gummfit │
│ │
│ Context │
│ │
│ platforms/ios/Gummfit is an operate-only companion app (products, bookings, orders, inbox, CRM, site settings). Site design is currently a web handoff, stated in two places we are deleting: │
│ │
│ - Views/Owner/More/SiteSettingsView.swift:56 — Text("Theme editing and page editing stay on web.") │
│ - Views/Owner/More/SiteSettingsView.swift:62 — Text("Publishing and page editing stay on web.") │
│ │
│ Goal: site owners design from the phone — Merlin AI chat, native section (block) editing, native theme editing, live preview. │
│ │
│ Load-bearing facts established during exploration │
│ │
│ 1. Merlin never writes the page. services/merlin/agent.py:run*merlin_agent folds ops onto a server-side working copy and returns an op log; CappeMerlinChatRequest's docstring says it outright: "Client state is the source of truth… the server never reads blocks/theme from the DB for this endpoint." iOS must own block state, apply ops locally, and persist via PUT /sites/{id}/pages/{id}. │
│ 2. Preview is server-rendered and self-contained. render/page.py:303 inlines \_CANVAS_JS (and CSS) into the returned document; images are absolute CDN URLs. WKWebView.loadHTMLString gives a pixel-exact preview. No Swift renderer, ever. │
│ 3. canvas.js:50 is function post(m){try{window.parent.postMessage(m,'*');}catch(e){}}. In a WKWebView top frame window.parent === window, so the frame dispatches a message event on the same window. A WKUserScript forwarding message events to a WKScriptMessageHandler captures every outbound cz-_ frame. Inbound goes to canvas.js:324's window.addEventListener('message', …) via evaluateJavaScript. Zero server change for tap-to-select. │
│ 4. APIClient cannot stream. No EventSource, no URLSession.bytes, no text/event-stream anywhere in the Swift tree. Must be added. │
│ 5. XcodeGen sources whole folders (project.yml lists App, Models, Services, ViewModels, Views, Resources) — new .swift files need no pbxproj edit, only make generate. │
│ │
│ Decisions (confirmed) │
│ │
│ - Scope: Merlin chat + native section forms + native theme controls + WKWebView preview with tap-to-select. Canvas freeform UI out of scope; canvas_add/update/remove are implemented in the Swift reducer so a Merlin turn can't corrupt a canvas block authored on web. │
│ - Block schema is API-driven — extend GET /api/cappe/merlin/schema, no third hand-maintained mirror in Swift. │
│ - Setup concierge included (POST /sites/{id}/merlin/setup/agent). │
│ │
│ --- │
│ Part A — Backend: complete the editor schema │
│ │
│ Additive, backwards-compatible, no migration. The web bundle ignores the new keys. │
│ │
│ A1. server/app/cappe/services/merlin/catalog.py │
│ │
│ Existing BLOCK_FIELDS: dict[str, dict[str, str]] (type → field → kind) and SELECT_OPTIONS: dict[str, dict[str, frozenset[str]]] stay untouched. Add three tables mirroring client/src/cappe/pages/site/PageEditor/blockSchemas.ts — this module's docstring already declares itself that file's hand-maintained mirror; we are completing it. │
│ │
│ # Human label + optional placeholder per field, mirroring blockSchemas.ts's │
│ # F(key, label, kind, {placeholder}). Consumed by GET /merlin/schema so a │
│ # non-web client (platforms/ios/Gummfit) can render a labelled form without │
│ # a fourth copy of this data. Missing entry -> the field name is the label. │
│ BLOCK_FIELD_LABELS: dict[str, dict[str, str]] = { │
│ "hero": { │
│ "eyebrow": "Eyebrow (small label)", "heading": "Heading", │
│ "subheading": "Subheading", "style": "Layout", │
│ "image": "Hero photo — adds a full-bleed background", │
│ "video": "Hero video — premium, autoplay full-bleed background", │
│ "align": "Text align (image layout)", "overlay": "Photo overlay (image layout)", │
│ "height": "Height (image layout)", "cta": "Button label", │
│ "ctaHref": "Button link", "cta2": "Second button label", │
│ "cta2Href": "Second button link", │
│ }, │
│ ... # one entry per BLOCK_FIELDS key │
│ } │
│ │
│ BLOCK_FIELD_PLACEHOLDERS: dict[str, dict[str, str]] = { │
│ "hero": {"ctaHref": "/p/contact or https://…"}, │
│ "pricing": {"price": "$24"}, │
│ ... │
│ } │
│ │
│ # Per-option label for select fields (SELECT_OPTIONS carries values only). │
│ SELECT_OPTION_LABELS: dict[str, dict[str, dict[str, str]]] = { │
│ "hero": { │
│ "style": {"centered": "Centered", "split": "Split (with image)", │
│ "image": "Full image background", "minimal": "Minimal"}, │
│ "align": {"center": "Center", "left": "Left"}, │
│ "overlay": {"light": "Light", "medium": "Medium", "dark": "Dark"}, │
│ "height": {"tall": "Tall", "full": "Full screen"}, │
│ }, │
│ } │
│ │
│ # Sub-field schema for every kind=="list" field: {block: {field: {sub: kind}}}. │
│ # THE piece the server genuinely lacks today — without it a list field is an │
│ # opaque blob to any client that isn't blockSchemas.ts. │
│ BLOCK_LIST_ITEM_FIELDS: dict[str, dict[str, dict[str, str]]] = { │
│ "features": {"items": {"icon": "text", "title": "text", "body": "textarea"}}, │
│ "gallery": {"images": {"url": "image", "caption": "text"}}, │
│ "pricing": {"plans": {"name": "text", "price": "text", "period": "text", │
│ "features": "strlist", "cta": "text", "ctaHref": "text"}}, │
│ ... # every list field in BLOCK_FIELDS │
│ } │
│ BLOCK_LIST_ITEM_LABELS: dict[str, dict[str, dict[str, str]]] = {...} │
│ │
│ # Add-row button label + the blank row a client inserts, mirroring │
│ # Field.addLabel / Field.newItem(). │
│ BLOCK_LIST_ITEM_DEFAULTS: dict[str, dict[str, dict[str, Any]]] = { │
│ "features": {"items": {"title": "", "body": ""}}, │
│ "pricing": {"plans": {"name": "", "price": "", "features": []}}, │
│ ... │
│ } │
│ BLOCK_LIST_ADD_LABELS: dict[str, dict[str, str]] = { │
│ "features": {"items": "Add feature"}, "pricing": {"plans": "Add plan"}, ... │
│ } │
│ │
│ # JSON equivalent of each BLOCK_SCHEMAS[type].make() closure — they are all │
│ # pure literals today. `add_block` on a non-web client builds from this. │
│ BLOCK_DEFAULTS: dict[str, dict[str, Any]] = { │
│ "hero": {"type": "hero", "heading": "Your headline", │
│ "subheading": "A sentence of supporting copy.", │
│ "cta": "Get started", "style": "centered"}, │
│ "features": {"type": "features", "heading": "What I do", "items": [ │
│ {"icon": "✦", "title": "Feature one", "body": "Short description."}, │
│ {"icon": "◆", "title": "Feature two", "body": "Short description."}, │
│ {"icon": "▲", "title": "Feature three", "body": "Short description."}]}, │
│ ... # one per BLOCK_TYPES; canvas -> the grid/mobile/elements literal from │
│ # canvasHelpers.ts:convertSectionToCanvas's return shape │
│ } │
│ │
│ # Display order, mirroring blockSchemas.ts's BLOCK_ORDER (already regex-parsed │
│ # by tests/cappe/test_merlin_validation.py:test_server_catalog_matches_client_block_schemas). │
│ BLOCK_ORDER: tuple[str, ...] = ("hero", "features", "split", ...) │
│ │
│ A2. server/app/cappe/services/theme_presets.py │
│ │
│ ThemePreset is a frozen dataclass of {id, name, blurb, premium, mode}. Add two fields: │
│ │
│ @dataclass(frozen=True) │
│ class ThemePreset: │
│ id: str │
│ name: str │
│ blurb: str │
│ premium: bool │
│ mode: str │
│ # Written verbatim into theme_config (plus {"preset": id}) when a client │
│ # applies `set_theme key="preset"`. Mirrors cappeThemes.ts's │
│ # CAPPE_THEMES[].config. REQUIRED for any client that isn't the web │
│ # bundle: render/page.py:\_tokens reads theme.colors/fonts/radius, never │
│ # theme.preset, so writing only `preset` leaves the old palette painting │
│ # (the exact bug merlinOps.ts:applyThemeOp documents). │
│ config: dict[str, Any] = field(default_factory=dict) │
│ # Card preview swatch, mirrors CAPPE_THEMES[].swatch. │
│ swatch: dict[str, str] = field(default_factory=dict) │
│ │
│ Populate config/swatch for all 10 presets (clean, minimal, noir, editorial, studio, sunset, terra, cobalt, bloom, press) verbatim from client/src/cappe/data/cappeThemes.ts's CAPPE_THEMES. Update the module docstring — it currently says the config "has no reason to exist server-side"; it does now. │
│ │
│ Also export the font pairings with their ids/labels so a native client can render the picker: │
│ │
│ @dataclass(frozen=True) │
│ class FontPairing: │
│ id: str; label: str; heading: str; body: str │
│ │
│ FONT_PAIRING_LIST: tuple[FontPairing, ...] = ( │
│ FontPairing("inter", "Inter / Inter", "Inter", "Inter"), ... │
│ ) │
│ Keep the existing FONT_PAIRINGS: tuple[tuple[str, str], ...] (prompt text) as tuple((p.heading, p.body) for p in FONT_PAIRING_LIST) so font_pairings_text() is unchanged. │
│ │
│ A3. server/app/cappe/services/merlin/ops.py::build_merlin_schema() │
│ │
│ Signature unchanged (-> dict[str, Any], still cached by routes/merlin.py:76's \_merlin_schema_cache). Emit the new data: │
│ │
│ def \_field_json(btype: str, name: str, kind: str) -> dict[str, Any]: │
│ out: dict[str, Any] = { │
│ "kind": kind, │
│ "label": BLOCK_FIELD_LABELS.get(btype, {}).get(name, name), │
│ } │
│ if ph := BLOCK_FIELD_PLACEHOLDERS.get(btype, {}).get(name): │
│ out["placeholder"] = ph │
│ if name in SELECT_OPTIONS.get(btype, {}): │
│ labels = SELECT_OPTION_LABELS.get(btype, {}).get(name, {}) │
│ out["options"] = [{"value": v, "label": labels.get(v, v)} │
│ for v in sorted(SELECT_OPTIONS[btype][name])] │
│ if kind == "list": │
│ item_kinds = BLOCK_LIST_ITEM_FIELDS.get(btype, {}).get(name, {}) │
│ item_labels = BLOCK_LIST_ITEM_LABELS.get(btype, {}).get(name, {}) │
│ out["item"] = {sub: {"kind": k, "label": item_labels.get(sub, sub)} │
│ for sub, k in item_kinds.items()} │
│ out["newItem"] = BLOCK_LIST_ITEM_DEFAULTS.get(btype, {}).get(name, {}) │
│ out["addLabel"] = BLOCK_LIST_ADD_LABELS.get(btype, {}).get(name, "Add item") │
│ return out │
│ │
│ blocks[btype] gains "make": BLOCK_DEFAULTS.get(btype, {"type": btype}); top level gains "blockOrder": list(BLOCK_ORDER); themePresets[] gains "config": p.config, "swatch": p.swatch; a new top-level "fontPairings": [{"id","label","heading","body"}]. │
│ │
│ options shape change: currently sorted(opts[name]) — a list[str]. It becomes list[{value,label}]. merlinOps.ts's MerlinDesignSchema type declares fields?: Record<string, {kind: string}> and only reads .kind; MerlinPanel.tsx's "Apply image to…" menu also only tests kind === 'image'. Grep client/src/cappe/\*\* for .options on a schema field before landing — if any web reader indexes it as strings, emit "options" (strings, unchanged) and a new "optionLabels": {value: label} instead of changing the shape. │
│ │
│ A4. Tests — extend the existing parity suite (do not add a parallel one) │
│ │
│ server/tests/cappe/test_merlin_validation.py already has test_server_catalog_matches_client_block_schemas (regex-parses BLOCK_ORDER out of blockSchemas.ts). server/tests/cappe/test_theme_presets.py already regex-parses CAPPE_THEMES ids. Add: │
│ │
│ Test: test_block_defaults_cover_every_block_type │
│ File: test_merlin_validation.py │
│ Asserts: set(BLOCK_DEFAULTS) == set(BLOCK_TYPES), and every value's ["type"] equals its key │
│ ──────────────────────────────────────── │
│ Test: test_every_list_field_has_an_item_schema │
│ File: test_merlin_validation.py │
│ Asserts: for each btype, field, kind in BLOCK_FIELDS where kind == "list", BLOCK_LIST_ITEM_FIELDS[btype][field] is │
│ non-empty │
│ ──────────────────────────────────────── │
│ Test: test_list_item_sub_kinds_are_known │
│ File: test_merlin_validation.py │
│ Asserts: every sub-kind ∈ LIST_KINDS | TEXT_KINDS | {"bool"} │
│ ──────────────────────────────────────── │
│ Test: test_block_field_labels_cover_every_field │
│ File: test_merlin_validation.py │
│ Asserts: set(BLOCK_FIELD_LABELS[b]) >= set(BLOCK_FIELDS[b]) for all b │
│ ──────────────────────────────────────── │
│ Test: test_block_order_matches_client │
│ File: test_merlin_validation.py │
│ Asserts: Python BLOCK_ORDER tuple == the regex-parsed BLOCK_ORDER list from blockSchemas.ts, order included │
│ ──────────────────────────────────────── │
│ Test: test_select_option_labels_cover_every_option │
│ File: test_merlin_validation.py │
│ Asserts: for each select field, set(SELECT_OPTION_LABELS[b][f]) == SELECT_OPTIONS[b][f] │
│ ──────────────────────────────────────── │
│ Test: test_preset_configs_match_client │
│ File: test_theme_presets.py │
│ Asserts: regex-extract each id:/config: pair from cappeThemes.ts (brace-matched slice), json5-ish normalize, assert │
│ key sets match THEME_PRESETS[i].config per preset. Palette values stay convention-checked; key drift is the │
│ failure mode that breaks rendering │
│ ──────────────────────────────────────── │
│ Test: test_font_pairing_ids_match_client │
│ File: test_theme_presets.py │
│ Asserts: {p.id for p in FONT_PAIRING_LIST} == regex-parsed FONT_PAIRINGS ids from cappeThemes.ts │
│ ──────────────────────────────────────── │
│ Test: test_schema_is_json_serializable │
│ File: test_merlin_validation.py │
│ Asserts: json.dumps(build_merlin_schema()) doesn't raise; │
│ blocks["features"]["fields"]["items"]["item"]["title"]["kind"] == "text"; themePresets[0]["config"] non-empty │
│ │
│ --- │
│ Part B — iOS foundation │
│ │
│ B1. Services/APIClient.swift — three additions (no signature changes to existing methods) │
│ │
│ /// Endpoints that answer `text/html` rather than JSON — today only │
│ /// POST /sites/{id}/preview (server/app/cappe/routes/sites.py:211). │
│ /// Shares requestData's 401-refresh / maintenance-retry path. │
│ func requestHTML(method: String, path: String, body: (any Encodable)? = nil) async throws -> String { │
│ let data = try await requestData(method: method, path: path, body: body) │
│ guard let html = String(data: data, encoding: .utf8) else { throw APIError.noData } │
│ return html │
│ } │
│ │
│ /// POST-based SSE. Port of client/src/cappe/sse.ts — iOS has no EventSource │
│ /// equivalent, and EventSource is GET-only anyway. │
│ /// │
│ /// `onFrame` returns true to stop consuming (the `[DONE]` sentinel does this │
│ /// automatically). Malformed JSON frames are SKIPPED, not thrown: one bad │
│ /// frame must not kill a turn. │
│ func streamSSE( │
│ path: String, │
│ body: any Encodable, │
│ onFrame: @escaping (Data) -> Bool │
│ ) async throws { │
│ try await AuthService.shared.ensureFreshToken(minTTL: 60) │
│ guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL } │
│ var req = URLRequest(url: url) │
│ req.httpMethod = "POST" │
│ req.setValue("application/json", forHTTPHeaderField: "Content-Type") │
│ req.setValue("text/event-stream", forHTTPHeaderField: "Accept") │
│ req.cachePolicy = .reloadIgnoringLocalCacheData │
│ req.timeoutInterval = 300 // agent turns run to a wall-clock budget │
│ if let token = accessToken { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") } │
│ req.httpBody = try encoder.encode(body) │
│ │
│ let (bytes, response) = try await URLSession.shared.bytes(for: req) │
│ guard let http = response as? HTTPURLResponse else { throw APIError.noData } │
│ guard (200...299).contains(http.statusCode) else { │
│ // Body is small on an error — drain it for the FastAPI `detail`. │
│ var buf = Data() │
│ for try await b in bytes { buf.append(b); if buf.count > 8192 { break } } │
│ throw APIError.httpError(http.statusCode, \_extractErrorMessage(from: buf) ?? "HTTP \(http.statusCode)") │
│ } │
│ for try await line in bytes.lines { // .lines splits on \n and handles \r\n │
│ try Task.checkCancellation() │
│ guard line.hasPrefix("data: ") else { continue } │
│ let payload = line.dropFirst(6).trimmingCharacters(in: .whitespacesAndNewlines) │
│ if payload.isEmpty { continue } │
│ if payload == "[DONE]" { return } │
│ if onFrame(Data(payload.utf8)) { return } │
│ } │
│ } │
│ (URLSession.AsyncBytes.lines already does the cross-chunk buffering and UTF-8 stream decoding that sse.ts hand-rolls, and yields a trailing unterminated line — the case sse.ts:60-64 comments as load-bearing. SSEParserTests below pins that.) │
│ │
│ Services/AuthService.swift gains: │
│ /// Refresh if the stored access token expires within `minTTL` seconds. │
│ /// A stream cannot replay a mid-flight 401 the way requestData's buffered │
│ /// retry can (cappe sse.ts's `cappeStreamHeaders` exists for this reason). │
│ func ensureFreshToken(minTTL: TimeInterval) async throws │
│ Implementation: base64url-decode the JWT payload's exp; refresh when exp - now < minTTL; a decode failure is a no-op (the stream's own 401 still surfaces). │
│ │
│ B2. Models/PageModels.swift (new) │
│ │
│ Mirrors server/app/cappe/models/sites.py:156-197. │
│ │
│ enum CappePageStatus: String, Codable { // Enums.swift house pattern │
│ case draft, published, archived, unknown │
│ init(from decoder: Decoder) throws { ... } // unknown fallback, never throws │
│ var isWritable: Bool { self != .unknown } │
│ } │
│ │
│ struct CappePage: Codable, Identifiable, Hashable { │
│ let id: String │
│ let site_id: String │
│ var title: String │
│ var slug: String │
│ var content: [String: JSONValue] // {"blocks": [...]} │
│ var sort_order: Int │
│ var status: CappePageStatus │
│ let created_at: String │
│ let updated_at: String │
│ │
│ /// content["blocks"] as blocks, empty when absent/misshapen. │
│ var blocks: [CappeBlock] { ... } │
│ } │
│ │
│ struct CappePageCreate: Encodable { let title: String; let slug: String?; let content: [String: JSONValue]; let sort_order: Int; let status: String } │
│ struct CappePageUpdate: Encodable { let title: String?; let slug: String?; let content: [String: JSONValue]?; let sort_order: Int?; let status: String? } │
│ │
│ /// POST /sites/{id}/preview body (models/sites.py:172 CappePagePreview). │
│ struct CappePagePreviewRequest: Encodable { │
│ let title: String?; let slug: String? │
│ let content: [String: JSONValue] │
│ let theme_config: [String: JSONValue]? │
│ let meta_config: [String: JSONValue]? │
│ let editable: Bool │
│ } │
│ │
│ CappeBlock — heterogeneous, must round-trip losslessly (a block may carry keys this build has never heard of). Models/JSONValue.swift already exists and is exactly the right primitive. │
│ │
│ /// One page section. Backed by an untyped JSONValue bag because the block │
│ /// vocabulary is server/registry-defined and a build must round-trip fields │
│ /// it doesn't understand (blockSchemas.ts gains types faster than the app │
│ /// ships). Value semantics: every mutator returns a new CappeBlock. │
│ struct CappeBlock: Codable, Identifiable, Hashable { │
│ var fields: [String: JSONValue] │
│ │
│ init(from decoder: Decoder) throws { fields = try [String: JSONValue](from: decoder) } │
│ func encode(to encoder: Encoder) throws { try fields.encode(to: encoder) } │
│ │
│ var type: String { fields["type"]?.stringValue ?? "" } │
│ /// Stable client key. Assigned on load, stripped on save — mirrors │
│ /// PageEditor/index.tsx's withKey/withKeys. Merlin ops address blocks by it. │
│ var \_k: String { fields["_k"]?.stringValue ?? "" } │
│ var id: String { \_k } │
│ var design: [String: JSONValue] { fields["_design"]?.objectValue ?? [:] } │
│ │
│ static func make(fromSchemaDefault d: [String: JSONValue]) -> CappeBlock // + fresh \_k │
│ func withKey(_ k: String = UUID().uuidString) -> CappeBlock │
│ func strippingKey() -> CappeBlock // for save │
│ /// Deep JSON copy with a fresh `_k`, a dropped `_design.anchor.id`, and │
│ /// fresh canvas element ids. Port of canvasHelpers.ts:cloneBlock — both │
│ /// ids MUST change (a duplicated anchor id duplicates an HTML id; a │
│ /// shared canvas element id lets canvas*update edit the wrong copy). │
│ func cloned() -> CappeBlock │
│ } │
│ │
│ Models/JSONValue.swift gains accessors (no change to the enum or its coding): │
│ extension JSONValue { │
│ var stringValue: String? ; var doubleValue: Double? ; var intValue: Int? │
│ var boolValue: Bool? ; var objectValue: [String: JSONValue]? ; var arrayValue: [JSONValue]? │
│ var isNull: Bool │
│ static func from(* any: Any) -> JSONValue // for schema `make`/`newItem` blobs │
│ var anyValue: Any? │
│ } │
│ ⚠️ JSONValue.init(from:) tries Bool before Double. Verified correct for JSON (true never decodes as a Double). .number(Double) is the only numeric case — JSONEncoder writes Double(3) as 3, so canvas grid ints (d.x/y/w/h) round-trip integrally. PageSaveEncodeTests pins this. │
│ │
│ B3. Models/EditorSchema.swift (new) │
│ │
│ Decodes GET /merlin/schema (Part A output). │
│ │
│ struct CappeEditorSchema: Codable { │
│ struct FieldOption: Codable { let value: String; let label: String } │
│ struct SubField: Codable { let kind: String; let label: String } │
│ struct Field: Codable { │
│ let kind: String // text|textarea|select|bool|image|video|strlist|list │
│ let label: String │
│ let placeholder: String? │
│ let options: [FieldOption]? │
│ let item: [String: SubField]? // kind == "list" │
│ let newItem: [String: JSONValue]? │
│ let addLabel: String? │
│ } │
│ struct Block: Codable { let label: String; let fields: [String: Field]; let make: [String: JSONValue] } │
│ struct ThemePreset: Codable { │
│ let id: String; let name: String; let blurb: String │
│ let premium: Bool; let mode: String │
│ let config: [String: JSONValue] // Part A2 — required for set*theme preset │
│ let swatch: [String: String] │
│ } │
│ struct FontPairing: Codable { let id, label, heading, body: String } │
│ struct SectionPreset: Codable { let name, label, blurb, blockType: String } │
│ struct StyleRecipe: Codable { let key, label, blurb: String } │
│ struct ThemeInfo: Codable { let keys: [String]; let prefixes: [String]; let modes: [String] } │
│ │
│ let blocks: [String: Block] │
│ let blockOrder: [String] │
│ let design: [String: [String: JSONValue]] // group -> key -> spec │
│ let theme: ThemeInfo │
│ let themePresets: [ThemePreset] │
│ let fontPairings: [FontPairing] │
│ let sectionPresets: [SectionPreset] │
│ let styleRecipes: [StyleRecipe] │
│ let limits: Limits │
│ │
│ func fieldOrder(for blockType: String) -> [String] // blocks[t].fields keys, stable-sorted │
│ func preset(* id: String) -> ThemePreset? │
│ } │
│ │
│ /// Process-wide cache. The server already caches the document in-process │
│ /// (routes/merlin.py:76) and it changes only on deploy, so one fetch per │
│ /// app launch is enough — no ETag, no TTL. │
│ @MainActor final class SchemaStore { │
│ static let shared = SchemaStore() │
│ private(set) var schema: CappeEditorSchema? │
│ func load() async throws -> CappeEditorSchema // memoized, coalesces concurrent callers │
│ } │
│ Models/ThemeModels.swift's existing hardcoded CappePublishedThemeCatalog stays — it's the offline swatch source for SiteSettingsView's read-only preview. The editor uses the fetched themePresets. │
│ │
│ B4. Models/MerlinModels.swift (new) │
│ │
│ Mirrors server/app/cappe/models/merlin.py. │
│ │
│ struct CappeMerlinHistoryTurn: Codable { let role: String; let content: String; let ops*summary: String? } │
│ struct CappeMerlinAttachment: Codable { let url: String; let mime: String? } │
│ struct CappeMerlinSelection: Codable { │
│ let block: String; let field: String?; let element: String? │
│ let kind: String // text|image|button|element │
│ let start: Int?; let end: Int?; let text: String? │
│ } │
│ │
│ struct CappeMerlinChatRequest: Encodable { │
│ let page_id: String │
│ let conversation_id: String? │
│ let message: String // 1...2000, enforce client-side │
│ let history: [CappeMerlinHistoryTurn] // <= 20 │
│ let blocks: [CappeBlock] // <= 200; \_k KEPT (ops address by it) │
│ let theme: [String: JSONValue] │
│ let model_tier: String // auto|lite|regular|max │
│ let selected_block: String? │
│ let selection: CappeMerlinSelection? │
│ let attachments: [CappeMerlinAttachment] // <= 8 │
│ } │
│ │
│ struct CappeMerlinSetupRequest: Encodable { let conversation_id: String?; let message: String } │
│ │
│ /// One decoded SSE frame. `agent_stream.py:_sse` frames both endpoints. │
│ enum CappeMerlinFrame: Decodable { │
│ case status(String) │
│ case step(CappeMerlinStep) │
│ case stagedAction(CappeSetupActionEntry) // setup endpoint only │
│ case error(String) │
│ case result(CappeMerlinResult) │
│ case unknown // forward-compat, never throws │
│ } │
│ struct CappeMerlinStep: Codable, Identifiable { │
│ let id = UUID() │
│ let kind: String // ops|screenshot|inspect|critique|image │
│ let label: String │
│ let results: [CappeMerlinOpResult]? │
│ let image_url: String? │
│ } │
│ struct CappeMerlinResult: Decodable { // page-editor terminal frame │
│ let message: String │
│ let ops: [JSONValue] │
│ let rejected: [CappeMerlinRejection] │
│ let tier: String │
│ let routed: Bool │
│ let conversation_id: String? │
│ let message_id: String? │
│ let steps: [CappeMerlinStep]? │
│ } │
│ struct CappeSetupResult: Decodable { // setup terminal frame │
│ let message: String │
│ let links: [JSONValue]? │
│ let tier: String │
│ let steps: [CappeMerlinStep]? │
│ let results: [JSONValue]? │
│ let readiness: [String: JSONValue]? │
│ } │
│ struct CappeMerlinRejection: Codable { let op: [String: JSONValue]; let reason: String } │
│ struct CappeMerlinOpResult: Codable { let ok: Bool; let summary: String } │
│ │
│ struct CappeMerlinConversation: Codable, Identifiable { let id, title, created_at, updated_at: String } │
│ struct CappeMerlinStoredMessage: Codable, Identifiable { │
│ let id: String; let role: String; let content: String │
│ let results: [CappeMerlinOpResult]?; let steps: [CappeMerlinStep]? │
│ let attachments: [JSONValue]?; let ops: [JSONValue]?; let tier: String?; let created_at: String │
│ /// `ops != nil && results == nil` ⇒ the turn's changes were never applied │
│ /// (client disconnected mid-turn). Offer "apply now", per merlin.py's │
│ /// CappeMerlinStoredMessage.ops doc comment. │
│ var isUnapplied: Bool { ops != nil && results == nil } │
│ } │
│ struct CappeMerlinConversationDetail: Codable { │
│ let id, title, created_at, updated_at, kind: String │
│ let messages: [CappeMerlinStoredMessage] │
│ let staged_actions: [CappeSetupActionEntry]? │
│ } │
│ struct CappeSetupActionEntry: Codable, Identifiable { │
│ let id, type, summary: String │
│ let payload: [String: JSONValue] │
│ let status: String // proposed|executed|dismissed|blocked │
│ let result: [String: JSONValue]?; let message: String? │
│ let created_at: String; let executed_at: String? │
│ } │
│ struct CappeSetupActionResult: Codable { let action: CappeSetupActionEntry; let message: String; let readiness: [String: JSONValue] } │
│ struct CappeMerlinResultsUpdate: Encodable { let results: [CappeMerlinOpResult] } // <= 60 │
│ │
│ B5. Editor/MerlinOps.swift (new) — ⚠️ highest-risk file │
│ │
│ Direct port of client/src/cappe/pages/site/PageEditor/merlinOps.ts (373 lines). The TS file's comments document real content-corruption bugs; keep every refusal rule and port the comments. │
│ │
│ enum MerlinOp { │
│ case setField(block: String, path: String, value: JSONValue) │
│ case setDesign(block: String, group: String, key: String, value: JSONValue) │
│ case setDesignBulk(blocks: [String], design: [String: [String: JSONValue]]) │
│ case addBlock(type: String, at: Int, content: [String: JSONValue]?, design: [String: JSONValue]?, preset: String?, id: String?) │
│ case duplicateBlock(block: String, at: Int?, id: String?) │
│ case removeBlock(block: String) │
│ case moveBlock(block: String, to: Int) │
│ case setTheme(key: String, value: JSONValue) │
│ case canvasAdd(block: String, element: [String: JSONValue]) │
│ case canvasUpdate(block: String, el: String, patch: [String: JSONValue]) │
│ case canvasRemove(block: String, el: String) │
│ case generateImage(block: String, field: String?, background: Bool, prompt: String, aspect: String?, imageSize: String?) │
│ case unrecognized │
│ │
│ init(json: JSONValue) // switch on ["op"]; unknown -> .unrecognized │
│ } │
│ │
│ struct MerlinApplyResult { │
│ var blocks: [CappeBlock] │
│ var theme: [String: JSONValue] │
│ var results: [CappeMerlinOpResult] │
│ /// Model temp id ("new-1") -> real `_k`, THIS TURN ONLY. A later op in the │
│ /// same turn can target a block that didn't exist when the turn started. │
│ /// Never reused as a real `_k` (two turns can both say "new-1"). │
│ var tempIdMap: [String: String] │
│ var changed: Bool │
│ } │
│ │
│ /// Immutable deep-set over object keys and numeric array indices, mirroring │
│ /// set_field's dot-path convention. REFUSES rather than coerces on a container │
│ /// mismatch: coercing turned `path: "items.title"` on a list into │
│ /// `items: {title: …}`, deleting every card while the chat reported success. │
│ /// An index past the end is refused, not padded (`== count` is an append). │
│ func deepSet(* target: JSONValue?, _ parts: ArraySlice<String>, _ value: JSONValue) -> (ok: Bool, value: JSONValue?) │
│ │
│ /// Structural keys a dot path must never reach. │
│ let RESERVED*PATH_KEYS: Set<String> = ["_k", "id", "type", "_design"] │
│ │
│ /// Returns nil when the path doesn't fit the block's shape (same refusal │
│ /// rules as deepSet). Shared by the set_field op and by direct form edits, so │
│ /// a nested path (`items.2.title`) behaves identically whichever wrote it. │
│ func applyFieldPath(* block: CappeBlock, path: String, value: JSONValue) -> CappeBlock? │
│ │
│ /// One set*theme. `key` is a dot path: colors.brand, fonts.heading, type.*, │
│ /// style._, or a bare top-level key (radius, mode, preset, premium). │
│ /// preset -> replaces the WHOLE theme with schema.preset(id).config │
│ /// + {"preset": id}. Writing only `preset` leaves the old │
│ /// palette painting (render/page.py:\_tokens reads colors). │
│ /// colors.brand -> also derives accent = value, brandText = contrastText(value) │
│ /// mode -> clears SURFACE keys bg/surface/text/muted/border only │
│ /// (brand/accent/brandText are identity, not mode) │
│ /// value == .null -> deletes the key │
│ /// Returns nil to signal "skip this op" (only for an unknown preset id). │
│ func applyThemeOp(_ theme: [String: JSONValue], key: String, value: JSONValue, │
│ schema: CappeEditorSchema?) -> [String: JSONValue]? │
│ │
│ /// Port of cappeThemes.ts:contrastText — relative luminance, threshold 0.6. │
│ /// Non-#rrggbb input returns "#ffffff". │
│ func contrastText(_ hex: String) -> String │
│ │
│ func applyMerlinOps(blocks: [CappeBlock], theme: [String: JSONValue], │
│ ops: [MerlinOp], schema: CappeEditorSchema?) -> MerlinApplyResult │
│ │
│ Per-op behaviour to preserve exactly: │
│ │
│ ┌────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ op │ Rule │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ │ block by \_k (through tempIdMap); missing → {ok:false,"Skipped — section no longer │ │
│ │ set_field │ exists"}; bad path → {ok:false, "Skipped — \"\(path)\" doesn't match this section's │ │
│ │ │ shape"} │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ set_design │ if schema.design[group][key] absent → skip "unknown design setting". ""/null clears the │ │
│ │ │ key │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ set_design_bulk │ server pre-expands "all" to ids; 0 matches → one {ok:false} result and changed = false │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ add_block │ schema.blocks[type] missing → skip unknown block type. New block = make ⊕ content, │ │
│ │ │ fresh \_k; design non-empty → \_design. at clamped 0...count. op.id → tempIdMap │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ duplicate_block │ cloned(); default at = idx + 1; op.id → tempIdMap │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ remove_block / │ id-addressed; move clamps to to 0...count-1; to == from → {ok:true,"already in place"} │ │
│ │ move_block │ │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ set_theme │ via applyThemeOp │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ │ operate on elements; canvas_add refuses at CV_MAX_ELEMENTS = 200; default d = {x:1, │ │
│ │ canvas\_\_ │ y:cvNextY(els), w:8, h:2}; canvas*update spreads patch (never id/kind — server already │ │
│ │ │ filters via CANVAS_PATCH_KEYS) │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ generate_image │ deliberate no-op in the synchronous fold; executed out-of-band by the VM │ │
│ ├────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ default │ {ok:false, "Skipped — unrecognized op"} │ │
│ └────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────┘ │
│ │
│ Swift value semantics remove the web's referential-stability concern; changed: Bool replaces it for the undo stack. │
│ │
│ B6. Editor/EditorHistory.swift (new) │
│ │
│ struct EditorSnapshot: Equatable { │
│ var blocks: [CappeBlock]; var title: String │
│ var status: CappePageStatus │
│ var theme: [String: JSONValue]; var meta: [String: JSONValue] │
│ } │
│ │
│ /// Combined undo/redo over the whole editor state, mirroring │
│ /// PageEditor/useEditorHistory.ts. A typed edit coalesces into the previous │
│ /// entry inside `coalesceWindow`; `checkpoint()` closes that window so a │
│ /// Merlin turn lands as exactly ONE undo entry. │
│ @MainActor final class EditorHistory { │
│ init(initial: EditorSnapshot, limit: Int = 60, coalesceWindow: TimeInterval = 0.6) │
│ private(set) var canUndo: Bool │
│ private(set) var canRedo: Bool │
│ func record(* s: EditorSnapshot, coalescing: Bool) │
│ func checkpoint() │
│ func undo() -> EditorSnapshot? │
│ func redo() -> EditorSnapshot? │
│ } │
│ │
│ B7. Services (new files, existing thin-wrapper house style) │
│ │
│ // Services/PagesService.swift — server/app/cappe/routes/pages.py │
│ final class PagesService { │
│ static let shared = PagesService(); private init() {} │
│ func list(siteId: String) async throws -> [CappePage] // GET /sites/{siteId}/pages │
│ func create(siteId: String, * body: CappePageCreate) async throws -> CappePage // POST /sites/{siteId}/pages │
│ func update(siteId: String, pageId: String, * body: CappePageUpdate) async throws -> CappePage // PUT │
│ func delete(siteId: String, pageId: String) async throws // DELETE, 204 │
│ } │
│ │
│ // Services/PreviewService.swift — routes/sites.py:211 preview*site_page │
│ final class PreviewService { │
│ static let shared = PreviewService(); private init() {} │
│ /// Returns a complete HTML document. `editable: true` embeds canvas.js │
│ /// (render/page.py:303) — required for tap-to-select. │
│ func render(siteId: String, title: String?, slug: String?, │
│ blocks: [CappeBlock], theme: [String: JSONValue]?, │
│ meta: [String: JSONValue]?, editable: Bool) async throws -> String │
│ } │
│ │
│ // Services/MerlinService.swift — routes/merlin.py + routes/merlin_setup.py │
│ final class MerlinService { │
│ static let shared = MerlinService(); private init() {} │
│ │
│ func schema() async throws -> CappeEditorSchema // GET /merlin/schema │
│ func conversations(siteId: String, pageId: String) async throws -> [CappeMerlinConversation] │
│ func createConversation(siteId: String, pageId: String, title: String?) async throws -> CappeMerlinConversation │
│ func conversation(* id: String) async throws -> CappeMerlinConversationDetail // GET /merlin/conversations/{id} │
│ func renameConversation(* id: String, title: String) async throws -> CappeMerlinConversation │
│ func deleteConversation(* id: String) async throws │
│ func reportResults(messageId: String, * results: [CappeMerlinOpResult]) async throws // PATCH /merlin/messages/{id}/results │
│ │
│ /// SSE. POST /sites/{siteId}/merlin/agent. │
│ func agent(siteId: String, * body: CappeMerlinChatRequest, │
│ onFrame: @escaping (CappeMerlinFrame) -> Void) async throws │
│ │
│ /// SSE. POST /sites/{siteId}/merlin/setup/agent. │
│ func setupAgent(siteId: String, * body: CappeMerlinSetupRequest, │
│ onFrame: @escaping (CappeMerlinFrame) -> Void) async throws │
│ func setupConversations(siteId: String) async throws -> [CappeMerlinConversation] │
│ func setupConversation(* id: String) async throws -> CappeMerlinConversationDetail │
│ func executeAction(conversationId: String, actionId: String) async throws -> CappeSetupActionResult │
│ func dismissAction(conversationId: String, actionId: String) async throws -> CappeMerlinConversationDetail │
│ } │
│ │
│ // Services/AssetsService.swift — routes/uploads.py │
│ final class AssetsService { │
│ static let shared = AssetsService(); private init() {} │
│ func upload(siteId: String, image: Data, mime: String, filename: String) async throws -> String // POST /sites/{id}/upload -> {url} │
│ /// POST /sites/{id}/generate-image. Throws APIError.httpError(429,*) on │
│ /// the shared daily image quota (image_quota.py: 3/day free, 30/day paid) — │
│ /// charged even on a failed generation. │
│ func generateImage(siteId: String, prompt: String, aspectRatio: String, │
│ imageSize: String?, style: String?, mood: String?) async throws -> String │
│ func assets(siteId: String, kind: String?) async throws -> [CappeAsset] // GET /sites/{id}/assets │
│ } │
│ │
│ --- │
│ Part C — iOS editor UI (Views/Owner/Editor/) │
│ │
│ Uses the existing design system: GummfitTheme, GummfitSpacing, GummfitTypography, GummfitStatusPill, .gummfitMuted(), .buttonStyle(.gummfitGhost), ErrorBanner, .gummfitScreenChrome(), Color(hex:). │
│ │
│ C1. PreviewWebView.swift │
│ │
│ /// Server-rendered live preview. render/page.py inlines canvas.js + canvas.css │
│ /// and all images are absolute CDN URLs, so the document is self-contained. │
│ struct PreviewWebView: UIViewRepresentable { │
│ let html: String │
│ let baseURL: URL? // APIClient.shared.assetOrigin │
│ var onSelect: (CzSelection) -> Void │
│ var onReady: () -> Void │
│ @Binding var command: CzCommand? // outbound, cleared after send │
│ │
│ func makeUIView(context: Context) -> WKWebView │
│ func updateUIView(* v: WKWebView, context: Context) // reload only when html changes; │
│ // restores scrollView.contentOffset │
│ func makeCoordinator() -> Coordinator │
│ final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate { ... } │
│ } │
│ │
│ /// canvas.js:50 posts to `window.parent`; in a top frame that IS `window`, so │
│ /// the frame lands as a `message` event here and we forward it to Swift. │
│ private let CZ_BRIDGE_JS = """ │
│ window.addEventListener('message', function(e){ │
│ try { window.webkit.messageHandlers.cz.postMessage(e.data) } catch (err) {} │
│ }); │
│ """ │
│ // WKUserScript(source: CZ_BRIDGE_JS, injectionTime: .atDocumentStart, forMainFrameOnly: true) │
│ │
│ /// Inbound frames consumed in v1. cz-reorder / cz-edit / cz-elem-move / │
│ /// cz-elem-resize / cz-drop-image are Canvas mode — ignored (see Scope). │
│ struct CzSelection { let block: Int; let field: String?; let element: String? │
│ let kind: String; let start: Int?; let end: Int?; let text: String? } │
│ enum CzCommand { case mode(String), highlight(Int), clear, breakpoint(String) } │
│ // sent via webView.evaluateJavaScript("window.postMessage(\(json),'_')") │
│ canvas.js addresses blocks by index (data-cz-block), Merlin by _k — PageEditorViewModel.selection(from:) maps index → \_k before building CappeMerlinSelection. │
│ │
│ C2. PageEditorView.swift + ViewModels/PageEditorViewModel.swift │
│ │
│ @MainActor @Observable final class PageEditorViewModel: LoadableVM { │
│ var isLoading = false; var error: String? │
│ let site: CappeSite │
│ private(set) var pages: [CappePage] = [] │
│ var pageId: String │
│ var title = ""; var status: CappePageStatus = .draft │
│ var blocks: [CappeBlock] = [] // \_k assigned on load │
│ var theme: [String: JSONValue] = [:] │
│ var meta: [String: JSONValue] = [:] │
│ var schema: CappeEditorSchema? │
│ private(set) var previewHTML = "" │
│ private(set) var isDirty = false │
│ var selection: CzSelection? │
│ │
│ func load() async // pages + site + SchemaStore.shared.load() │
│ func selectPage(_ id: String) async │
│ func refreshPreview() async // debounced 400ms (usePagePreview.ts parity) │
│ func save() async // see C7 │
│ func undo(); func redo() │
│ │
│ // Mutations — every one routes through applyFieldPath / applyMerlinOps so │
│ // form edits and Merlin edits share one code path. │
│ func setField(blockKey: String, path: String, value: JSONValue) │
│ func setDesign(blockKey: String, group: String, key: String, value: JSONValue) │
│ func addBlock(type: String, at: Int) │
│ func duplicateBlock(_ key: String); func removeBlock(_ key: String) │
│ func moveBlocks(from: IndexSet, to: Int) │
│ func setThemeKey(_ key: String, _ value: JSONValue) │
│ func apply(ops: [MerlinOp]) -> MerlinApplyResult // one history entry (checkpoint first) │
│ } │
│ PageEditorView: PreviewWebView fills the screen; bottom Picker(.segmented) Sections | Theme | ✨, each a .sheet with .presentationDetents([.medium, .large]) + .presentationBackgroundInteraction(.enabled) so the preview stays live behind. Toolbar: page menu, undo/redo, Save. │
│ │
│ C3. Section editing │
│ │
│ - SectionListView.swift — List over vm.blocks, .onMove(perform: vm.moveBlocks), .onDelete, swipe → Duplicate, row → SectionFormView, toolbar + → AddSectionSheet. │
│ - AddSectionSheet.swift — grid over schema.blockOrder (Block.label) + a "Presets" section over schema.sectionPresets. A plain type calls vm.addBlock(type:at:) (local make); a preset chip sends apply the "<key>" preset as a Merlin message — apply*section_preset is rewritten to add_block only inside ops.py:validate_ops, so it is not client-applicable. Documented in the file header. │
│ - SectionFormView.swift / SchemaFieldInputs.swift — fully schema-driven, no Swift block table: │
│ │
│ struct SchemaFieldInput: View { │
│ let field: CappeEditorSchema.Field │
│ let path: String // e.g. "items.2.title" │
│ let value: JSONValue? │
│ let onChange: (String, JSONValue) -> Void // (path, value) -> vm.setField │
│ let siteId: String // image/video pickers │
│ } │
│ │
│ ┌────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ kind │ control │ │
│ ├────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ text │ TextField(field.label, text:), prompt: field.placeholder │ │
│ ├────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ textarea │ TextEditor + label │ │
│ ├────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ select │ Picker over field.options ({value,label}) │ │
│ ├────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ bool │ Toggle │ │
│ ├────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ image / │ thumbnail + menu: Library (GET /sites/{id}/assets), Upload (PhotosPicker → │ │
│ │ video │ AssetsService.upload), Generate (prompt sheet → AssetsService.generateImage), Clear │ │
│ ├────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ strlist │ rows of TextField, .onDelete, "Add" │ │
│ ├────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ list │ rows of nested SchemaFieldInput driven by field.item; "Add" appends field.newItem; │ │
│ │ │ .onMove/.onDelete write items.<i> paths │ │
│ └────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│ │
│ - DesignInspectorView.swift — per-block \_design, driven by schema.design groups (layout/colors/border/motion/bg/type/anchor/divider). ""/nil clears a key. Premium groups render disabled with an upgrade note: design_gate.py:gate_content silently strips \_design on save for non-premium plans, so the UI must not imply it persisted. │
│ │
│ C4. ThemeSheet.swift │
│ │
│ Every control emits exactly one vm.setThemeKey(*:_:) → applyThemeOp — one code path shared with Merlin. │
│ │
│ ┌───────────────────────────────────────────┬──────────────────────────────────────┬──────────────────────────┐ │
│ │ Control │ key │ value │ │
│ ├───────────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────┤ │
│ │ Preset grid (swatch from │ preset │ preset id │ │
│ │ ThemePreset.swatch, premium badge) │ │ │ │
│ ├───────────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────┤ │
│ │ ColorPicker │ colors.brand │ #rrggbb (derives accent │ │
│ │ │ │ + brandText) │ │
│ ├───────────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────┤ │
│ │ Font pairing Picker over │ fonts.heading + fonts.body │ names │ │
│ │ schema.fontPairings │ │ │ │
│ ├───────────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────┤ │
│ │ Corners Picker │ radius │ preset value │ │
│ ├───────────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────┤ │
│ │ Light/Dark Picker │ mode │ light/dark (clears │ │
│ │ │ │ surface colors) │ │
│ ├───────────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────┤ │
│ │ Premium: headline anim / gradient / │ type.heroAnim, colors.brandGradient, │ — │ │
│ │ effects │ premium │ │ │
│ ├───────────────────────────────────────────┼──────────────────────────────────────┼──────────────────────────┤ │
│ │ Premium: layout & spacing │ style.<key> for each key in │ number/enum │ │
│ │ │ schema.theme.prefixes │ │ │
│ └───────────────────────────────────────────┴──────────────────────────────────────┴──────────────────────────┘ │
│ │
│ C5. MerlinChatView.swift + ViewModels/MerlinChatViewModel.swift │
│ │
│ @MainActor @Observable final class MerlinChatViewModel: LoadableVM { │
│ var isLoading = false; var error: String? │
│ unowned let editor: PageEditorViewModel │
│ var conversationId: String? │
│ private(set) var messages: [CappeMerlinStoredMessage] = [] │
│ private(set) var liveSteps: [CappeMerlinStep] = [] │
│ private(set) var statusLine: String? │
│ var draft = "" │
│ var tier = "auto" // auto|lite|regular|max │
│ var attachments: [CappeMerlinAttachment] = [] │
│ private var task: Task<Void, Never>? │
│ │
│ func loadConversations() async │
│ func open(_ conversationId: String) async │
│ func send() async │
│ func cancel() │
│ func applyUnapplied(_ message: CappeMerlinStoredMessage) // ops != nil && results == nil │
│ } │
│ │
│ send() sequence: │
│ 1. editor.blocks + editor.theme snapshot read at send time; guard combined JSON < 300_000 bytes (routes/merlin.py:\_MAX_SNAPSHOT_BYTES) and surface the 413 copy pre-flight. │
│ 2. history = last 20 turns; selection from editor.selection (block index → \_k). │
│ 3. MerlinService.agent(...) streaming. .status → statusLine; .step → append liveSteps; .error → self.error (the agent route delivers rate limits as an in-band error frame, never an HTTP 429). │
│ 4. On .result: editor.apply(ops:) against live state re-read now (2–5s elapsed; concurrent form edits must not be reverted) — one checkpoint() + one history entry. │
│ 5. generateImage ops: remap block through tempIdMap, call AssetsService.generateImage, then apply the follow-up — setField(path: field) for a content field, or the set_design bg.type = "image" + bg.image = url pair when background == true. │
│ 6. MerlinService.reportResults(messageId:). On failure retry ×3 with backoff (1s/4s/12s), then enqueue to Editor/PendingResultsQueue.swift (a JSON file in .applicationSupportDirectory, drained on next app foreground) — the localStorage fallback useMerlin.ts has. │
│ │
│ Error surfaces to render explicitly: │
│ │
│ ┌─────────────────────────────────┬──────────────────────────────────────────────┬─────────────────────────────┐ │
│ │ Condition │ Where │ Copy anchor │ │
│ ├─────────────────────────────────┼──────────────────────────────────────────────┼─────────────────────────────┤ │
│ │ 429 chat (10/hr free, 60/hr │ in-band .error frame on SSE routes; HTTP 429 │ │ │
│ │ paid), agent (20/hr), setup │ on /merlin/chat │ server detail │ │
│ │ (20/hr) │ │ │ │
│ ├─────────────────────────────────┼──────────────────────────────────────────────┼─────────────────────────────┤ │
│ │ 413 snapshot > 300KB │ HTTP, pre-flight guarded │ "Page is too large for chat │ │
│ │ │ │ — edit sections directly" │ │
│ ├─────────────────────────────────┼──────────────────────────────────────────────┼─────────────────────────────┤ │
│ │ image quota 429 (3/day free, │ AssetsService.generateImage │ server detail │ │
│ │ 30/day paid) │ │ │ │
│ ├─────────────────────────────────┼──────────────────────────────────────────────┼─────────────────────────────┤ │
│ │ tier clamp │ none — server clamps to lite silently; show │ │ │
│ │ │ the returned result.tier │ │ │
│ └─────────────────────────────────┴──────────────────────────────────────────────┴─────────────────────────────┘ │
│ │
│ C6. Save (vm.save()) │
│ │
│ Explicit, not autosave — matches the web. │
│ 1. PUT /sites/{siteId}/pages/{pageId} with CappePageUpdate(title:, status:, content: ["blocks": blocks.map { $0.strippingKey() }]). │
│ 2. If theme/meta dirty: PUT /sites/{siteId} with {theme_config, meta_config} (reuse SitesService.update; extend CappeSiteUpdate with the two optional bags). │
│ 3. 409 on slug → APIError.conflict already handled by APIClient. │
│ 4. .interactiveDismissDisabled(vm.isDirty) + confirmation dialog on back. │
│ │
│ --- │
│ Part D — Setup concierge │
│ │
│ Views/Owner/SetupConciergeView.swift + ViewModels/SetupMerlinViewModel.swift, entered from HomeView. Reuses streamSSE and the chat UI; no local block state — every write is a server-side staged action. │
│ │
│ @MainActor @Observable final class SetupMerlinViewModel: LoadableVM { │
│ var isLoading = false; var error: String? │
│ let siteId: String │
│ var conversationId: String? │
│ private(set) var messages: [CappeMerlinStoredMessage] = [] │
│ private(set) var stagedActions: [CappeSetupActionEntry] = [] │
│ private(set) var readiness: CappeReadiness? // existing model, SiteModels.swift │
│ var draft = "" │
│ func load() async │
│ func send() async // POST /sites/{id}/merlin/setup/agent │
│ func execute(_ action: CappeSetupActionEntry) async // POST .../actions/{id}/execute │
│ func dismiss(\_ action: CappeSetupActionEntry) async // POST .../actions/{id}/dismiss │
│ } │
│ .stagedAction frames upsert into stagedActions by id (they arrive on stage and on execute). Each status == "proposed" entry renders a card with Do it / Dismiss; blocked shows action.message. The terminal frame's readiness drives a checklist reusing CappeReadiness/CappeReadinessItem. │
│ │
│ --- │
│ Part E — Copy / docs │
│ │
│ ┌───────────────────────────────────────────────────┬──────────────────────────────────────────────────────────┐ │
│ │ File │ Change │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ │ delete Text("Theme editing and page editing stay on │ │
│ │ Views/Owner/More/SiteSettingsView.swift:56 │ web."); add NavigationLink("Edit site design") { │ │
│ │ │ PageEditorView(site: site) } │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ │ "Publishing and page editing stay on web." → "Publishing │ │
│ │ Views/Owner/More/SiteSettingsView.swift:62 │ stays on web."; keep the Link as a secondary "Open on │ │
│ │ │ web" │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ │ drop "Page editing … remain web handoffs by design"; │ │
│ │ platforms/ios/Gummfit/README.md:3-5 │ list what is still web-only: billing purchase, domain │ │
│ │ │ setup, payout onboarding, Canvas freeform mode │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ │ update the webOrigin doc comment — it cites the page │ │
│ │ Services/APIClient.swift:130-132 │ editor as out-of-scope and a GUMMFIT_IOS_APP_PLAN.md │ │
│ │ │ that no longer exists in the repo │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ Services/SitesService.swift:15 │ create()'s "no page editor in this app" comment │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ Models/SiteModels.swift:41-42, │ same stale comment │ │
│ │ Views/Owner/CreateSiteView.swift:4-5 │ │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ server/app/cappe/services/merlin/catalog.py │ note the mirror now also feeds the iOS editor via GET │ │
│ │ docstring │ /merlin/schema │ │
│ ├───────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤ │
│ │ server/app/cappe/services/theme_presets.py │ it no longer carries "only what the model needs" — it │ │
│ │ docstring │ carries the canonical config for non-web clients │ │
│ └───────────────────────────────────────────────────┴──────────────────────────────────────────────────────────┘ │
│ │
│ --- │
│ Tests │
│ │
│ Backend — server/tests/cappe/ │
│ │
│ Nine cases listed in A4, added to the existing test_merlin_validation.py / test_theme_presets.py. │
│ │
│ iOS — platforms/ios/Gummfit/Tests/ (XCTest, @testable import Gummfit, decode/encode-pinning house style) │
│ │
│ MerlinOpsTests.swift — the port's correctness. Each case builds [CappeBlock] from JSON literals and asserts on applyMerlinOps: │
│ │
│ ┌───────────────────────────────────────────────┬───────────────────────────────────────────────────────────────┐ │
│ │ Test │ Asserts │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetFieldNamedKeyIntoListIsRefused │ set_field path:"items.title" on features → results[0].ok == │ │
│ │ │ false, blocks unchanged (the documented card-deleting bug) │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetFieldIndexPastEndIsRefused │ items.5.title on a 3-item list → refused, no null padding │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetFieldIndexEqualCountAppends │ items.3.title on a 3-item list → appended, ok == true │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetFieldReservedHeadKeysRefused │ paths \_k, id, type, \_design → each refused │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetFieldNestedListItemApplies │ items.1.body → only that item changes │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testMissingBlockYieldsSkippedChipNotError │ unknown \_k → {ok:false, summary contains "no longer exists"}, │ │
│ │ │ no throw │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetDesignEmptyValueClearsKey │ value: "" removes the key from the group │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetDesignUnknownKeySkipped │ key absent from schema.design[group] → skipped │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetDesignBulkNoMatchLeavesBlocksUnchanged │ changed == false, blocks identical │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testAddBlockUsesSchemaMakeAndClampsAt │ at: 99 on 2 blocks → appended at index 2; content from │ │
│ │ │ schema.blocks[t].make merged under content │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testTempIdRemapsSameTurnGenerateImage │ add_block(id:"new-1") then generate_image(block:"new-1") → │ │
│ │ │ tempIdMap["new-1"] is the new \_k │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testDuplicateBlockFreshKeysAndDroppedAnchor │ clone \_k ≠ source, \_design.anchor.id absent, canvas element │ │
│ │ │ ids all differ │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testMoveBlockToSameIndexIsNoOpButOk │ {ok:true, "already in place"}, changed == false │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetThemePresetReplacesWholeConfig │ old colors.bg gone, new preset's palette present, │ │
│ │ │ theme["preset"] set │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetThemeUnknownPresetSkipped │ ok == false, theme unchanged │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetThemeBrandDerivesAccentAndContrast │ colors.accent == brand; contrastText("#ffee00") == "#10120a", │ │
│ │ │ contrastText("#101010") == "#ffffff" │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetThemeModeClearsSurfaceOnly │ bg/surface/text/muted/border removed; brand/accent/brandText │ │
│ │ │ retained │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testSetThemeNullDeletesKey │ key absent afterwards │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testCanvasAddRespectsMaxElements │ 200 elements → refused │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testCanvasUpdatePatchIgnoresIdAndKind │ element id/kind unchanged │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testGenerateImageIsNoOpInFold │ blocks/theme unchanged, no "unrecognized" chip │ │
│ ├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤ │
│ │ testUnknownOpYieldsUnrecognizedChip │ {ok:false, "unrecognized"} │ │
│ └───────────────────────────────────────────────┴───────────────────────────────────────────────────────────────┘ │
│ │
│ EditorSchemaDecodeTests.swift — decode a captured GET /merlin/schema body: a list field's item sub-schema + newItem + addLabel; select options as {value,label}; blocks["hero"].make["heading"]; themePresets[0].config non-empty; blockOrder non-empty; unknown top-level keys don't throw. │
│ │
│ SSEParserTests.swift — drive streamSSE's line handling through a URLProtocol stub (first stub harness in the app; put it in Tests/Support/StubURLProtocol.swift): │
│ - frame split across two chunks reassembles │
│ - multi-byte character (é, emoji) straddling a chunk boundary decodes intact │
│ - \r\n line endings parse │
│ - malformed-JSON frame is skipped, the following good frame still delivers │
│ - data: [DONE] terminates │
│ - terminal result frame with no trailing newline is still delivered │
│ - non-data: lines (event:, : heartbeat) ignored │
│ - HTTP 429 before the stream opens → APIError.httpError(429, detail) │
│ - Task cancellation mid-stream throws CancellationError, no leak │
│ │
│ PageSaveEncodeTests.swift — \_k stripped from every block on save; a block key the app has never seen round-trips byte-identical through JSONValue; an integer field (canvas d.x = 3) re-encodes as 3, not 3.0; CappePageUpdate omits nil fields. │
│ │
│ PageModelDecodeTests.swift — CappePage decode incl. empty content; status: "archived" → .archived; unknown status → .unknown, no throw. │
│ │
│ MerlinFrameDecodeTests.swift — each frame type decodes; an unknown type → .unknown (forward-compat, never throws); CappeMerlinStoredMessage.isUnapplied true only for ops != nil && results == nil. │
│ │
│ --- │
│ Verification │
│ │
│ Backend │
│ cd server │
│ python3 -m pytest tests/cappe/test_merlin_validation.py tests/cappe/test_theme_presets.py -v │
│ python3 -c "import json; from app.cappe.services.merlin.ops import build_merlin_schema; s=build_merlin_schema(); json.dumps(s); print(s['blocks']['features']['fields']['items']['item'])" │
│ Web regression (the schema change is additive but options changes shape — see A3): with ./scripts/dev-remote.sh up, open the page editor at :5174, confirm Merlin applies an op and the / command menu still lists blocks/presets. Then: │
│ cd client && npx tsc -p tsconfig.app.json --noEmit # bare `npx tsc --noEmit` checks NOTHING │
│ │
│ iOS │
│ cd platforms/ios/Gummfit │
│ make generate && make build && make test │
│ ./run.sh # Debug → http://127.0.0.1:8001/api/cappe │
│ │
│ End-to-end on simulator (backend on :8001, a site with at least one page): │
│ 1. Sign in → site → Edit site design. Preview renders identically to the web editor for the same page. │
│ 2. Tap a hero in the preview → its form sheet opens — proves the cz-select bridge (the single riskiest assumption). │
│ 3. Edit a heading → preview updates within ~400ms. Save. Reload the web editor → change persisted. │
│ 4. Add a features section → edit items.1.title in the nested list form → preview reflects it — proves the item sub-schema round trip. │
│ 5. Theme sheet → switch preset → preview repaints with the new palette (not just the highlight) — proves A2's config and applyThemeOp's whole-config replace. │
│ 6. Merlin: "add a pricing section under the hero and make it dark" → status line + step trail stream, section appears, chips render, one undo reverts the whole turn. │
│ 7. Merlin image generation on a hero background → image lands in the preview; a second/third rapid request eventually surfaces the daily-quota 429 copy. │
│ 8. Home → Set up your site → "add a contact page" → staged card → Do it → the page appears in the editor's page menu. │
│ 9. Airplane mode mid-stream → clean error banner, blocks uncorrupted; re-enable, foreground the app, confirm the pending results report drains (check PATCH /merlin/messages/{id}/results in the backend log).
