import SwiftUI

struct SectionFormView: View {
    @Bindable var vm: PageEditorViewModel
    let blockKey: String

    private var block: CappeBlock? { vm.blocks.first { $0._k == blockKey } }

    var body: some View {
        ScrollView {
            if let block, let schemaBlock = vm.schema?.blocks[block.type] {
                VStack(alignment: .leading, spacing: 16) {
                    Text(schemaBlock.label).font(.title2.bold()).foregroundStyle(GummfitTheme.textPrimary)
                    ForEach(schemaBlock.fields.keys.sorted(), id: \.self) { name in
                        if let field = schemaBlock.fields[name] {
                            SchemaFieldInput(field: field, path: name, value: block.fields[name], onChange: { path, value in vm.setField(blockKey: blockKey, path: path, value: value) }, siteId: vm.site.id)
                        }
                    }
                    DesignInspectorView(vm: vm, blockKey: blockKey)
                }
                .padding()
            } else {
                ContentUnavailableView("Section unavailable", systemImage: "questionmark.square")
            }
        }
        .navigationTitle("Edit section")
        .gummfitScreenChrome()
    }
}
