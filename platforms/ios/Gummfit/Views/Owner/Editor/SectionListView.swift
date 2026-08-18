import SwiftUI

struct SectionListView: View {
    @Bindable var vm: PageEditorViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var showAdd = false

    var body: some View {
        List {
            if vm.blocks.isEmpty {
                ContentUnavailableView("No sections", systemImage: "rectangle.3.group", description: Text("Add a section to start designing this page."))
            }
            ForEach(Array(vm.blocks.enumerated()), id: \.element.id) { index, block in
                NavigationLink {
                    SectionFormView(vm: vm, blockKey: block._k)
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "rectangle.3.group.fill").foregroundStyle(GummfitTheme.accent)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(vm.schema?.blocks[block.type]?.label ?? block.type.capitalized)
                                .font(.subheadline.weight(.semibold))
                            Text(block.type).font(.caption).foregroundStyle(GummfitTheme.textDim)
                        }
                        Spacer()
                        Menu {
                            Button("Duplicate") { vm.duplicateBlock(block._k) }
                            Button("Move up") { if index > 0 { vm.moveBlocks(from: IndexSet(integer: index), to: index - 1) } }
                            Button("Move down") { if index + 1 < vm.blocks.count { vm.moveBlocks(from: IndexSet(integer: index), to: index + 2) } }
                            Button("Delete", role: .destructive) { vm.removeBlock(block._k) }
                        } label: { Image(systemName: "ellipsis.circle") }
                    }
                }
                .listRowBackground(GummfitTheme.surface)
            }
            .onMove(perform: vm.moveBlocks)
            .onDelete { offsets in offsets.map { vm.blocks[$0]._k }.forEach(vm.removeBlock) }
        }
        .navigationTitle("Sections")
        .toolbar {
            ToolbarItem(placement: .topBarLeading) { Button("Done") { dismiss() } }
            ToolbarItem(placement: .topBarTrailing) { Button { showAdd = true } label: { Image(systemName: "plus") } }
        }
        .sheet(isPresented: $showAdd) { AddSectionSheet(vm: vm) }
        .gummfitListBackground()
        .gummfitScreenChrome()
    }
}

struct AddSectionSheet: View {
    @Bindable var vm: PageEditorViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    ForEach(vm.schema?.blockOrder ?? [], id: \.self) { type in
                        Button {
                            vm.addBlock(type: type)
                            dismiss()
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                Image(systemName: "rectangle.3.group.fill").foregroundStyle(GummfitTheme.accent)
                                Text(vm.schema?.blocks[type]?.label ?? type.capitalized).font(.subheadline.weight(.semibold))
                                Text(type).font(.caption2).foregroundStyle(GummfitTheme.textDim)
                            }
                            .frame(maxWidth: .infinity, minHeight: 82, alignment: .leading)
                            .padding(14)
                            .background(GummfitTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding()
            }
            .navigationTitle("Add section")
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } } }
            .gummfitScreenChrome()
        }
    }
}
