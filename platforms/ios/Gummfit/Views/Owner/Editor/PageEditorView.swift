import SwiftUI

struct PageEditorView: View {
    let site: CappeSite
    @State private var vm: PageEditorViewModel
    @State private var mode = 0
    @State private var command: CzCommand?
    @State private var showSections = false
    @State private var showTheme = false
    @State private var showChat = false

    init(site: CappeSite) {
        self.site = site
        _vm = State(initialValue: PageEditorViewModel(site: site))
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            if vm.previewHTML.isEmpty {
                ProgressView("Loading preview…").tint(GummfitTheme.accent)
            } else {
                PreviewWebView(html: vm.previewHTML, onSelect: { vm.selection = $0 }, onReady: {}, command: $command)
                    .ignoresSafeArea(edges: .bottom)
            }
            bottomBar
        }
        .navigationTitle(vm.title.isEmpty ? "Site design" : vm.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarLeading) {
                Button { vm.undo() } label: { Image(systemName: "arrow.uturn.backward") }
                Button { vm.redo() } label: { Image(systemName: "arrow.uturn.forward") }
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button(vm.isLoading ? "Saving…" : "Save") { Task { await vm.save() } }
                    .disabled(vm.isLoading || !vm.isDirty)
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 4) }
        .gummfitScreenChrome()
        .sheet(isPresented: $showSections) { NavigationStack { SectionListView(vm: vm) } }
        .sheet(isPresented: $showTheme) { NavigationStack { ThemeSheet(vm: vm) } }
        .sheet(isPresented: $showChat) { NavigationStack { MerlinChatView(editor: vm) } }
        .task { await vm.load() }
        .interactiveDismissDisabled(vm.isDirty)
    }

    private var bottomBar: some View {
        HStack(spacing: 0) {
            editorButton("Sections", icon: "rectangle.3.group", selected: mode == 0) { mode = 0; showSections = true }
            editorButton("Theme", icon: "paintpalette", selected: mode == 1) { mode = 1; showTheme = true }
            editorButton("Merlin", icon: "sparkles", selected: mode == 2) { mode = 2; showChat = true }
        }
        .padding(6)
        .background(.ultraThinMaterial, in: Capsule())
        .padding(.horizontal, 24)
        .padding(.bottom, 12)
    }

    private func editorButton(_ title: String, icon: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .font(.caption.weight(.semibold))
                .foregroundStyle(selected ? GummfitTheme.background : GummfitTheme.textPrimary)
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .background(selected ? GummfitTheme.accent : .clear, in: Capsule())
        }
        .frame(maxWidth: .infinity)
    }
}
