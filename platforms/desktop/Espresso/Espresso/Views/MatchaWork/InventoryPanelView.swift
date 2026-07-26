import SwiftUI

struct InventoryPanelView: View {
    let state: [String: AnyCodable]

    @State private var searchText = ""
    @State private var selectedCategory: String? = nil
    @State private var sortKey = "name"
    @State private var sortAscending = true

    private let categories = ["all", "protein", "produce", "dairy", "dry_goods", "beverages", "supplies", "equipment", "other"]

    private var items: [MWInventoryItem] {
        guard let raw = state["inventory_items"]?.value as? [AnyCodable] else { return [] }
        let data = try? JSONSerialization.data(withJSONObject: raw.map { $0.value })
        guard let data else { return [] }
        return (try? JSONDecoder().decode([MWInventoryItem].self, from: data)) ?? []
    }

    private var filtered: [MWInventoryItem] {
        var list = items
        if let cat = selectedCategory, cat != "all" {
            list = list.filter { $0.category == cat }
        }
        if !searchText.isEmpty {
            let q = searchText.lowercased()
            list = list.filter {
                ($0.productName?.lowercased().contains(q) ?? false)
                || ($0.sku?.lowercased().contains(q) ?? false)
                || ($0.vendor?.lowercased().contains(q) ?? false)
            }
        }
        return list.sorted { a, b in
            let result: Bool
            switch sortKey {
            case "quantity":
                result = (a.quantity ?? 0) < (b.quantity ?? 0)
            case "unit_cost":
                result = (a.unitCost ?? 0) < (b.unitCost ?? 0)
            case "total_cost":
                result = (a.totalCost ?? 0) < (b.totalCost ?? 0)
            case "vendor":
                result = (a.vendor ?? "") < (b.vendor ?? "")
            default:
                result = (a.displayName) < (b.displayName)
            }
            return sortAscending ? result : !result
        }
    }

    private var totalCost: Double {
        items.reduce(0) { $0 + ($1.totalCost ?? 0) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Inventory")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text("(\(items.count) items)")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Spacer()
                if totalCost > 0 {
                    Text("$\(String(format: "%.2f", totalCost))")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.matcha500)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            // Category filter
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(categories, id: \.self) { cat in
                        Button {
                            selectedCategory = cat == "all" ? nil : cat
                        } label: {
                            Text(cat.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.system(size: 10, weight: .medium))
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(
                                    (selectedCategory == nil && cat == "all") || selectedCategory == cat
                                    ? Color.matcha600 : Color.zinc800
                                )
                                .foregroundColor(
                                    (selectedCategory == nil && cat == "all") || selectedCategory == cat
                                    ? .white : .secondary
                                )
                                .cornerRadius(4)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 6)
            }

            // Search + Sort
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                TextField("Search by name, SKU, vendor...", text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))

                Menu {
                    ForEach(["name", "quantity", "unit_cost", "total_cost", "vendor"], id: \.self) { key in
                        Button {
                            if sortKey == key { sortAscending.toggle() }
                            else { sortKey = key; sortAscending = true }
                        } label: {
                            HStack {
                                Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                                if sortKey == key {
                                    Image(systemName: sortAscending ? "chevron.up" : "chevron.down")
                                }
                            }
                        }
                    }
                } label: {
                    Image(systemName: "arrow.up.arrow.down")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(Color.zinc800.opacity(0.5))

            Divider().opacity(0.3)

            // Item list
            if filtered.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "shippingbox")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("No inventory items")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(filtered) { item in
                            InventoryRow(item: item)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .background(Color.zinc900)
    }
}

private struct InventoryRow: View {
    let item: MWInventoryItem
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.displayName)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                    HStack(spacing: 6) {
                        if let cat = item.category {
                            Text(cat.replacingOccurrences(of: "_", with: " "))
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(.cyan)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color.cyan.opacity(0.12))
                                .cornerRadius(3)
                        }
                        if let vendor = item.vendor {
                            Text(vendor)
                                .font(.system(size: 10))
                                .foregroundColor(.secondary)
                        }
                    }
                }
                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    if let total = item.totalCost {
                        Text("$\(String(format: "%.2f", total))")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white)
                    }
                    if let qty = item.quantity, let unit = item.unit {
                        Text("\(String(format: qty == qty.rounded() ? "%.0f" : "%.1f", qty)) \(unit)")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }

                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeOut(duration: 0.15)) { isExpanded.toggle() }
            }

            if isExpanded {
                VStack(alignment: .leading, spacing: 4) {
                    if let sku = item.sku {
                        Label("SKU: \(sku)", systemImage: "barcode")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    if let unitCost = item.unitCost, let unit = item.unit {
                        Label("$\(String(format: "%.2f", unitCost)) / \(unit)", systemImage: "dollarsign.circle")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    if let par = item.parLevel {
                        Label("Par level: \(String(format: "%.0f", par))", systemImage: "chart.bar")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
                .transition(.opacity)
            }
        }
        .background(isExpanded ? Color.zinc800.opacity(0.3) : Color.clear)
    }
}
