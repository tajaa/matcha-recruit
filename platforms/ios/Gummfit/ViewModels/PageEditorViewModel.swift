import Foundation
import Observation

@MainActor
@Observable
final class PageEditorViewModel: LoadableVM {
    let site: CappeSite
    var isLoading = false
    var error: String?
    private(set) var pages: [CappePage] = []
    var pageId = ""
    var title = ""
    var status: CappePageStatus = .draft
    var blocks: [CappeBlock] = []
    var theme: [String: JSONValue] = [:]
    var meta: [String: JSONValue] = [:]
    var schema: CappeEditorSchema?
    private(set) var previewHTML = ""
    private(set) var isDirty = false
    var selection: CzSelection?
    private var history: EditorHistory?
    private var previewTask: Task<Void, Never>?
    private var savedTheme: [String: JSONValue]
    private var savedMeta: [String: JSONValue]
    private(set) var themeDirty = false
    private(set) var metaDirty = false

    init(site: CappeSite) {
        self.site = site
        self.savedTheme = site.theme_config?.raw ?? [:]
        self.savedMeta = site.meta_config ?? [:]
    }

    func load() async {
        await withLoad {
            async let pageResult = PagesService.shared.list(siteId: site.id)
            async let schemaResult = SchemaStore.shared.load()
            let (loadedPages, loadedSchema) = try await (pageResult, schemaResult)
            pages = loadedPages
            schema = loadedSchema
            if pageId.isEmpty { pageId = loadedPages.first?.id ?? "" }
            if !pageId.isEmpty { selectPage(pageId) }
            history = EditorHistory(initial: snapshot())
            await refreshPreview()
        }
    }

    func selectPage(_ id: String) {
        guard let page = pages.first(where: { $0.id == id }) else { return }
        pageId = page.id
        title = page.title
        status = page.status
        blocks = page.blocks
        theme = savedTheme
        meta = savedMeta
        isDirty = false
        themeDirty = false
        metaDirty = false
    }

    func setField(blockKey: String, path: String, value: JSONValue) {
        guard let index = blocks.firstIndex(where: { $0._k == blockKey }),
              let updated = applyFieldPath(block: blocks[index], path: path, value: value) else { return }
        blocks[index] = updated
        record()
    }

    func setDesign(blockKey: String, group: String, key: String, value: JSONValue) {
        apply(ops: [.setDesign(block: blockKey, group: group, key: key, value: value)])
    }

    func addBlock(type: String, at: Int? = nil) {
        let position = at ?? blocks.count
        let result = apply(ops: [.addBlock(type: type, at: position, content: nil, design: nil, preset: nil, id: nil)])
        if !result.changed { error = "This section type is not available offline." }
    }

    func duplicateBlock(_ key: String) { _ = apply(ops: [.duplicateBlock(block: key, at: nil, id: nil)]) }
    func removeBlock(_ key: String) { _ = apply(ops: [.removeBlock(block: key)]) }

    func moveBlocks(from offsets: IndexSet, to destination: Int) {
        guard let source = offsets.first, blocks.indices.contains(source) else { return }
        let target = merlinMoveDestination(from: source, to: destination, count: blocks.count)
        _ = apply(ops: [.moveBlock(block: blocks[source]._k, to: target)])
    }

    func setThemeKey(_ key: String, _ value: JSONValue) { apply(ops: [.setTheme(key: key, value: value)]) }

    @discardableResult
    func apply(ops: [MerlinOp]) -> MerlinApplyResult {
        history?.checkpoint()
        let before = theme
        let result = applyMerlinOps(blocks: blocks, theme: theme, ops: ops, schema: schema)
        blocks = result.blocks
        theme = result.theme
        if result.theme != before { themeDirty = true }
        if result.changed { record() }
        return result
    }

    func undo() { if let snapshot = history?.undo() { restore(snapshot) } }
    func redo() { if let snapshot = history?.redo() { restore(snapshot) } }

    func save() async {
        guard !pageId.isEmpty else { return }
        guard status.isWritable else {
            error = "This page's status can't be saved from the app."
            return
        }
        await withLoad {
            let content: [String: JSONValue] = ["blocks": .array(blocks.map { .object($0.strippingKey().fields) })]
            _ = try await PagesService.shared.update(
                siteId: site.id,
                pageId: pageId,
                CappePageUpdate(title: title, slug: nil, content: content, sort_order: nil, status: status.rawValue)
            )
            // Theme + promos live on the SITE, not the page — mirrors the web
            // editor's second PUT (PageEditor/index.tsx:331-338).
            if themeDirty || metaDirty {
                _ = try await SitesService.shared.update(
                    siteId: site.id,
                    CappeSiteUpdate(theme_config: themeDirty ? theme : nil, meta_config: metaDirty ? meta : nil)
                )
                savedTheme = theme
                savedMeta = meta
                themeDirty = false
                metaDirty = false
            }
            isDirty = false
        }
    }

    func refreshPreview() async {
        previewTask?.cancel()
        let currentBlocks = blocks
        let currentTheme = theme
        previewTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(400))
            guard !Task.isCancelled, let self else { return }
            do {
                let html = try await PreviewService.shared.render(
                    siteId: self.site.id, title: self.title, slug: nil,
                    blocks: currentBlocks, theme: currentTheme, meta: self.meta, editable: true
                )
                guard !Task.isCancelled else { return }
                self.previewHTML = html
            } catch {
                if !error.isCancellation { self.error = error.localizedDescription }
            }
        }
        await previewTask?.value
    }

    func selectionFromPreview(_ selection: CzSelection) -> CappeMerlinSelection? {
        guard blocks.indices.contains(selection.block) else { return nil }
        return CappeMerlinSelection(
            block: blocks[selection.block]._k,
            field: selection.field,
            element: selection.element,
            kind: selection.kind,
            start: selection.start,
            end: selection.end,
            text: selection.text
        )
    }

    private func snapshot() -> EditorSnapshot {
        EditorSnapshot(blocks: blocks, title: title, status: status, theme: theme, meta: meta)
    }

    private func record() {
        isDirty = true
        history?.record(snapshot(), coalescing: true)
        Task { await refreshPreview() }
    }

    private func restore(_ snapshot: EditorSnapshot) {
        blocks = snapshot.blocks
        title = snapshot.title
        status = snapshot.status
        theme = snapshot.theme
        meta = snapshot.meta
        isDirty = true
        themeDirty = true
        Task { await refreshPreview() }
    }
}
