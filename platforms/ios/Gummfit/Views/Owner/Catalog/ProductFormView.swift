import SwiftUI
import PhotosUI

/// Create (`existing == nil`) or edit a product — name/price/photo/options/
/// fulfillment. No page editor in this app; this is the whole native product
/// authoring surface (plan §"No page editor" is about site pages, not this).
struct ProductFormView: View {
    let site: CappeSite
    let existing: CappeProduct?
    var onSaved: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @State private var vm = ProductFormViewModel()
    @State private var photoItem: PhotosPickerItem?
    @State private var bookingTypes: [CappeBookingType] = []
    @State private var showStockAdjust = false
    @State private var showCreateBookingType = false
    @State private var newTypeName = ""
    @State private var newTypeDuration = 30
    @State private var newTypePriceCents = 0
    @State private var creatingBookingType = false

    var body: some View {
        Form {
            Section {
                ErrorBanner(message: vm.error)
                photoPicker
            }

            Section("Details") {
                TextField("Name", text: $vm.name)
                TextField("Description", text: $vm.description, axis: .vertical)
                HStack {
                    Text("Price")
                    Spacer()
                    TextField("0.00", value: priceDollarsBinding, format: .number.precision(.fractionLength(2)))
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                }
                TextField("SKU", text: $vm.sku)
                TextField("Category", text: $vm.category)
            }

            Section("Fulfillment") {
                Picker("Type", selection: $vm.fulfillment) {
                    Text("Physical").tag(Fulfillment.physical)
                    Text("Digital").tag(Fulfillment.digital)
                    Text("Service").tag(Fulfillment.service)
                    Text("Booking").tag(Fulfillment.booking)
                }
                if vm.fulfillment == .digital {
                    TextField("Digital file URL", text: $vm.digitalFileUrl)
                }
                if vm.fulfillment == .booking {
                    Picker("Booking type", selection: Binding(
                        get: { vm.bookingTypeId ?? "" },
                        set: { newValue in
                            if newValue == "__new__" {
                                showCreateBookingType = true
                            } else {
                                vm.bookingTypeId = newValue.isEmpty ? nil : newValue
                            }
                        }
                    )) {
                        Text("None").tag("")
                        ForEach(bookingTypes) { type in
                            Text(type.name).tag(type.id)
                        }
                        Text("+ New booking type").tag("__new__")
                    }
                }
                Toggle("Requires approval before it goes through", isOn: $vm.requiresApproval)
            }

            Section("Status") {
                Picker("Status", selection: $vm.status) {
                    Text("Draft").tag("draft")
                    Text("Active").tag("active")
                    Text("Archived").tag("archived")
                }
            }

            if vm.fulfillment == .physical {
                Section("Inventory") {
                    Toggle("Track stock", isOn: $vm.isTrackingStock)
                    if vm.isTrackingStock {
                        HStack {
                            Text("In stock")
                            Spacer()
                            TextField("0", value: $vm.inventory, format: .number)
                                .keyboardType(.numberPad)
                                .multilineTextAlignment(.trailing)
                        }
                        HStack {
                            Text("Low stock alert at")
                            Spacer()
                            TextField("None", value: $vm.lowStockThreshold, format: .number)
                                .keyboardType(.numberPad)
                                .multilineTextAlignment(.trailing)
                        }
                        if existing != nil {
                            Button("Adjust stock") { showStockAdjust = true }
                            NavigationLink("Inventory log") {
                                InventoryLogView(site: site, productId: existing!.id)
                            }
                        }
                    }
                }
            }

            Section {
                optionGroupsEditor
            } header: {
                Text("Options")
            } footer: {
                if !vm.optionsValid {
                    Text("Name every option group and option, or delete the empty rows.")
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle(existing == nil ? "New product" : "Edit product")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(vm.isLoading ? "Saving…" : "Save") {
                    Task {
                        if await vm.save(siteId: site.id) {
                            onSaved()
                            dismiss()
                        }
                    }
                }
                .disabled(!vm.canSubmit)
            }
        }
        .sheet(isPresented: $showStockAdjust) {
            if let existing {
                NavigationStack {
                    StockAdjustSheet(site: site, product: existing, currentInventory: vm.inventory, onAdjusted: { updated in
                        vm.applyAdjusted(updated)
                    })
                }
            }
        }
        .onChange(of: photoItem) { _, newItem in
            Task {
                guard let newItem, let data = try? await newItem.loadTransferable(type: Data.self) else { return }
                // PhotosPicker items are usually HEIC on-device even though
                // this call site used to hardcode "image/jpeg" — trust the
                // item's own declared type instead (ImagePrep re-encodes
                // anything outside its raster allowlist, so this just needs
                // to be accurate, not pre-filtered).
                let type = newItem.supportedContentTypes.first
                let mimeType = type?.preferredMIMEType ?? "image/jpeg"
                let ext = type?.preferredFilenameExtension ?? "jpg"
                await vm.uploadPhoto(data: data, mimeType: mimeType, filename: "product.\(ext)", siteId: site.id)
            }
        }
        .task {
            if let existing { vm.load(from: existing) }
            bookingTypes = (try? await BookingsService.shared.listTypes(siteId: site.id)) ?? []
        }
        .sheet(isPresented: $showCreateBookingType) {
            NavigationStack {
                Form {
                    TextField("Name", text: $newTypeName)
                    Stepper("\(newTypeDuration) minutes", value: $newTypeDuration, in: 5...480, step: 5)
                    HStack {
                        Text("Price")
                        Spacer()
                        TextField("0.00", value: Binding(
                            get: { Double(newTypePriceCents) / 100 },
                            set: { newTypePriceCents = Int(($0 * 100).rounded()) }
                        ), format: .number.precision(.fractionLength(2)))
                            .keyboardType(.decimalPad)
                    }
                }
                .navigationTitle("New booking type")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Save") {
                            Task {
                                creatingBookingType = true
                                defer { creatingBookingType = false }
                                if let created = try? await BookingsService.shared.createType(
                                    siteId: site.id,
                                    CappeBookingTypeCreate(name: newTypeName, duration_minutes: newTypeDuration, price_cents: newTypePriceCents)
                                ) {
                                    bookingTypes.append(created)
                                    vm.bookingTypeId = created.id
                                }
                                newTypeName = ""; newTypeDuration = 30; newTypePriceCents = 0
                                showCreateBookingType = false
                            }
                        }
                        .disabled(newTypeName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || creatingBookingType)
                    }
                }
            }
        }
    }

    private var photoPicker: some View {
        PhotosPicker(selection: $photoItem, matching: .images) {
            HStack {
                if let url = SafeURL.assetURL(vm.imageUrl) {
                    AsyncImage(url: url) { $0.resizable().aspectRatio(contentMode: .fill) } placeholder: { Color.gray.opacity(0.2) }
                        .frame(width: 60, height: 60)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                } else {
                    RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.15))
                        .frame(width: 60, height: 60)
                        .overlay(Image(systemName: "photo").foregroundStyle(GummfitTheme.textDim))
                }
                Text(vm.isUploadingPhoto ? "Uploading…" : "Choose photo")
                if vm.isUploadingPhoto { ProgressView() }
            }
        }
    }

    private var priceDollarsBinding: Binding<Double> {
        Binding(
            get: { Double(vm.priceCents) / 100 },
            set: { vm.priceCents = Int(($0 * 100).rounded()) }
        )
    }

    @ViewBuilder
    private var optionGroupsEditor: some View {
        ForEach($vm.optionGroups) { $group in
            DisclosureGroup(group.name.isEmpty ? "Option group" : group.name) {
                TextField("Group name", text: $group.name)
                Picker("Selection", selection: $group.select_type) {
                    Text("Pick one").tag("single")
                    Text("Pick any").tag("multi")
                }
                ForEach($group.options) { $option in
                    HStack {
                        TextField("Option name", text: $option.name)
                        TextField("+¢", value: $option.price_delta_cents, format: .number)
                            .keyboardType(.numberPad)
                            .frame(width: 60)
                    }
                }
                .onDelete { group.options.remove(atOffsets: $0) }
                Button("Add option") {
                    group.options.append(CappeProductOptionInput(name: "", price_delta_cents: 0))
                }
            }
        }
        .onDelete { vm.optionGroups.remove(atOffsets: $0) }
        Button("Add option group") {
            vm.optionGroups.append(CappeProductOptionGroupInput(name: ""))
        }
    }
}
