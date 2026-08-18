import Foundation

enum MerlinOp {
    case setField(block: String, path: String, value: JSONValue)
    case setDesign(block: String, group: String, key: String, value: JSONValue)
    case setDesignBulk(blocks: [String], design: [String: [String: JSONValue]])
    case addBlock(type: String, at: Int, content: [String: JSONValue]?, design: [String: [String: JSONValue]]?, preset: String?, id: String?)
    case duplicateBlock(block: String, at: Int?, id: String?)
    case removeBlock(block: String)
    case moveBlock(block: String, to: Int)
    case setTheme(key: String, value: JSONValue)
    case canvasAdd(block: String, element: [String: JSONValue])
    case canvasUpdate(block: String, el: String, patch: [String: JSONValue])
    case canvasRemove(block: String, el: String)
    case generateImage(block: String, field: String?, background: Bool, prompt: String, aspect: String?, imageSize: String?)
    case unrecognized

    init(json: JSONValue) {
        guard let object = json.objectValue, let name = object["op"]?.stringValue else {
            self = .unrecognized
            return
        }
        let string = { (key: String) in object[key]?.stringValue ?? "" }
        let objectValue = { (key: String) in object[key]?.objectValue }
        let stringArray = { (key: String) -> [String]? in object[key]?.arrayValue?.compactMap(\.stringValue) }
        switch name {
        case "set_field": self = .setField(block: string("block"), path: string("path"), value: object["value"] ?? .null)
        case "set_design": self = .setDesign(block: string("block"), group: string("group"), key: string("key"), value: object["value"] ?? .null)
        case "set_design_bulk":
            guard let blocks = stringArray("blocks"), let rawDesign = objectValue("design") else { self = .unrecognized; return }
            let design = rawDesign.reduce(into: [String: [String: JSONValue]]()) { result, entry in
                if let group = entry.value.objectValue { result[entry.key] = group }
            }
            self = .setDesignBulk(blocks: blocks, design: design)
        case "add_block":
            let design = objectValue("design")?.reduce(into: [String: [String: JSONValue]]()) { result, entry in
                if let group = entry.value.objectValue { result[entry.key] = group }
            }
            self = .addBlock(type: string("type"), at: object["at"]?.intValue ?? 0, content: objectValue("content"), design: design, preset: object["preset"]?.stringValue, id: object["id"]?.stringValue)
        case "remove_block": self = .removeBlock(block: string("block"))
        case "move_block": self = .moveBlock(block: string("block"), to: object["to"]?.intValue ?? 0)
        case "set_theme": self = .setTheme(key: string("key"), value: object["value"] ?? .null)
        case "duplicate_block": self = .duplicateBlock(block: string("block"), at: object["at"]?.intValue, id: object["id"]?.stringValue)
        case "canvas_add":
            guard let element = objectValue("element") else { self = .unrecognized; return }
            self = .canvasAdd(block: string("block"), element: element)
        case "canvas_update":
            guard let patch = objectValue("patch") else { self = .unrecognized; return }
            self = .canvasUpdate(block: string("block"), el: string("el"), patch: patch)
        case "canvas_remove": self = .canvasRemove(block: string("block"), el: string("el"))
        case "generate_image": self = .generateImage(block: string("block"), field: object["field"]?.stringValue, background: object["background"]?.boolValue ?? false, prompt: string("prompt"), aspect: object["aspect"]?.stringValue, imageSize: object["image_size"]?.stringValue)
        default: self = .unrecognized
        }
    }
}

/// SwiftUI `.onMove` supplies an insert-before index computed BEFORE the row is
/// removed; `MerlinOp.moveBlock` removes first, then inserts. Shift a downward
/// move by one to convert between the two conventions.
func merlinMoveDestination(from source: Int, to destination: Int, count: Int) -> Int {
    let adjusted = destination > source ? destination - 1 : destination
    return min(max(0, adjusted), max(0, count - 1))
}

struct MerlinApplyResult {
    var blocks: [CappeBlock]
    var theme: [String: JSONValue]
    var results: [CappeMerlinOpResult]
    var tempIdMap: [String: String]
    var changed: Bool
}

func deepSet(_ target: JSONValue?, _ parts: ArraySlice<String>, _ value: JSONValue) -> (ok: Bool, value: JSONValue?) {
    guard let head = parts.first else { return (true, value) }
    let rest = parts.dropFirst()
    let isIndex = !head.isEmpty && head.allSatisfy(\.isNumber)
    guard let target else {
        guard !isIndex else { return (false, nil) }
        guard rest.isEmpty else {
            let result = deepSet(nil, rest, value)
            guard result.ok, let updated = result.value else { return (false, nil) }
            return (true, .object([head: updated]))
        }
        return (true, .object([head: value]))
    }
    switch target {
    case .object(var object):
        guard !isIndex else { return (false, nil) }
        guard let child = object[head] else {
            if rest.isEmpty {
                object[head] = value
                return (true, .object(object))
            }
            let result = deepSet(nil, rest, value)
            guard result.ok, let updated = result.value else { return (false, nil) }
            object[head] = updated
            return (true, .object(object))
        }
        let result = deepSet(child, rest, value)
        guard result.ok, let updated = result.value else { return (false, nil) }
        object[head] = updated
        return (true, .object(object))
    case .array(var array):
        guard isIndex, let index = Int(head), index >= 0, index <= array.count else { return (false, nil) }
        if index == array.count {
            guard !rest.isEmpty else { array.append(value); return (true, .array(array)) }
            let result = deepSet(nil, rest, value)
            guard result.ok, let updated = result.value else { return (false, nil) }
            array.append(updated)
            return (true, .array(array))
        }
        let result = deepSet(array[index], rest, value)
        guard result.ok, let updated = result.value else { return (false, nil) }
        array[index] = updated
        return (true, .array(array))
    default:
        return (false, nil)
    }
}

let RESERVED_PATH_KEYS: Set<String> = ["_k", "id", "type", "_design"]

func applyFieldPath(block: CappeBlock, path: String, value: JSONValue) -> CappeBlock? {
    let parts = path.split(separator: ".").map(String.init)
    guard let head = parts.first, !head.isEmpty, !RESERVED_PATH_KEYS.contains(head) else { return nil }
    var copy = block
    if parts.count == 1 {
        copy.fields[head] = value
        return copy
    }
    let result = deepSet(copy.fields[head], parts.dropFirst()[...], value)
    guard result.ok, let updated = result.value else { return nil }
    copy.fields[head] = updated
    return copy
}

func contrastText(_ hex: String) -> String {
    let value = hex.trimmingCharacters(in: .whitespacesAndNewlines)
    guard value.count == 7, value.first == "#", let number = Int(value.dropFirst(), radix: 16) else { return "#ffffff" }
    let red = Double((number >> 16) & 255), green = Double((number >> 8) & 255), blue = Double(number & 255)
    let luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return luminance > 0.6 ? "#10120a" : "#ffffff"
}

func applyThemeOp(_ theme: [String: JSONValue], key: String, value: JSONValue, schema: CappeEditorSchema?) -> [String: JSONValue]? {
    var result = theme
    if key == "preset" {
        guard let id = value.stringValue,
              let config = schema?.preset(id)?.config ?? fallbackThemeConfig(id) else { return nil }
        result = config
        result["preset"] = .string(id)
        return result
    }
    if key == "mode", let mode = value.stringValue, (mode == "light" || mode == "dark"), theme["mode"]?.stringValue != mode {
        var colors = result["colors"]?.objectValue ?? [:]
        for surfaceKey in ["bg", "surface", "text", "muted", "border"] {
            colors.removeValue(forKey: surfaceKey)
        }
        result["mode"] = value
        result["colors"] = .object(colors)
        return result
    }
    let parts = key.split(separator: ".").map(String.init)
    guard let head = parts.first else { return nil }
    if parts.count == 1 {
        if value.isNull { result.removeValue(forKey: head) } else { result[head] = value }
        return result
    }
    let subkey = parts.dropFirst().joined(separator: ".")
    var group = result[head]?.objectValue ?? [:]
    if value.isNull { group.removeValue(forKey: subkey) } else { group[subkey] = value }
    result[head] = .object(group)
    if key == "colors.brand", let color = value.stringValue {
        group["accent"] = value
        group["brandText"] = .string(contrastText(color))
        result[head] = .object(group)
    }
    return result
}

func applyMerlinOps(blocks: [CappeBlock], theme: [String: JSONValue], ops: [MerlinOp], schema: CappeEditorSchema?) -> MerlinApplyResult {
    var blocks = blocks
    var theme = theme
    var results: [CappeMerlinOpResult] = []
    var tempIdMap: [String: String] = [:]
    var changed = false
    func key(_ value: String) -> String { tempIdMap[value] ?? value }
    func index(of block: String) -> Int? { blocks.firstIndex { $0._k == key(block) } }
    func skip(_ summary: String) { results.append(.init(ok: false, summary: summary)) }
    func designBag(_ block: CappeBlock) -> [String: JSONValue] { block.fields["_design"]?.objectValue ?? [:] }
    func canvasElements(_ block: CappeBlock) -> [[String: JSONValue]] {
        (block.fields["elements"]?.arrayValue ?? []).compactMap(\.objectValue)
    }
    func canvasY(_ elements: [[String: JSONValue]]) -> Double {
        elements.reduce(0) { current, element in
            let d = element["d"]?.objectValue ?? [:]
            return max(current, (d["y"]?.doubleValue ?? 0) + (d["h"]?.doubleValue ?? 1))
        }
    }
    for op in ops {
        switch op {
        case let .setField(block, path, value):
            guard let index = index(of: block) else { skip("Skipped — section no longer exists"); continue }
            guard let updated = applyFieldPath(block: blocks[index], path: path, value: value) else {
                skip("Skipped — \"\(path)\" doesn't match this section's shape")
                continue
            }
            blocks[index] = updated; changed = true; results.append(.init(ok: true, summary: "Updated \(path)"))
        case let .setDesign(block, group, designKey, value):
            guard let index = index(of: block) else { skip("Skipped — section no longer exists"); continue }
            if let schema, schema.design[group]?[designKey] == nil {
                skip("Skipped — unknown design setting \"\(group).\(designKey)\"")
                continue
            }
            var design = designBag(blocks[index])
            var groupValues = design[group]?.objectValue ?? [:]
            if value.isNull || value.stringValue == "" { groupValues.removeValue(forKey: designKey) }
            else { groupValues[designKey] = value }
            design[group] = .object(groupValues)
            blocks[index].fields["_design"] = .object(design)
            changed = true
            results.append(.init(ok: true, summary: "Updated \(group).\(designKey)"))
        case let .setDesignBulk(targets, design):
            let targetKeys = Set(targets.map(key))
            var touched = 0
            for index in blocks.indices where targetKeys.contains(blocks[index]._k) {
                var merged = designBag(blocks[index])
                for (group, values) in design {
                    var groupValues = merged[group]?.objectValue ?? [:]
                    for (designKey, value) in values { groupValues[designKey] = value }
                    merged[group] = .object(groupValues)
                }
                blocks[index].fields["_design"] = .object(merged)
                touched += 1
            }
            if touched == 0 {
                skip("Skipped — none of the targeted sections exist")
            } else {
                changed = true
                results.append(.init(ok: true, summary: "Styled \(touched) section\(touched == 1 ? "" : "s")"))
            }
        case let .addBlock(type, at, content, design, preset, id):
            let schemaBlock = schema?.blocks[type]
            var newBlock = CappeBlock(fields: schemaBlock?.make ?? ["type": .string(type)]).withKey()
            if let content {
                for (field, value) in content where !RESERVED_PATH_KEYS.contains(field) { newBlock.fields[field] = value }
            }
            newBlock.fields["type"] = .string(type)
            newBlock = newBlock.withKey()
            if let design, !design.isEmpty { newBlock.fields["_design"] = .object(design.mapValues { .object($0) }) }
            if let id { tempIdMap[id] = newBlock._k }
            blocks.insert(newBlock, at: min(max(0, at), blocks.count))
            changed = true
            let suffix = preset.map { " (\($0))" } ?? ""
            results.append(.init(ok: true, summary: "Added \(schemaBlock?.label ?? type)\(suffix)"))
        case let .setTheme(key, value):
            guard let updated = applyThemeOp(theme, key: key, value: value, schema: schema) else { skip("Skipped — unknown theme preset"); continue }
            theme = updated; changed = true; results.append(.init(ok: true, summary: "Updated theme"))
        case let .removeBlock(block):
            guard let index = index(of: block) else { skip("Skipped — section no longer exists"); continue }
            blocks.remove(at: index); changed = true; results.append(.init(ok: true, summary: "Removed section"))
        case let .moveBlock(block, to):
            guard let from = index(of: block) else { skip("Skipped — section no longer exists"); continue }
            let destination = min(max(0, to), blocks.count - 1)
            if destination == from { results.append(.init(ok: true, summary: "Section already in place")); continue }
            let item = blocks.remove(at: from); blocks.insert(item, at: destination); changed = true; results.append(.init(ok: true, summary: "Moved section"))
        case let .duplicateBlock(block, at, id):
            guard let sourceIndex = index(of: block) else { skip("Skipped — section no longer exists"); continue }
            let clone = blocks[sourceIndex].cloned()
            if let id { tempIdMap[id] = clone._k }
            blocks.insert(clone, at: min(max(0, at ?? (sourceIndex + 1)), blocks.count)); changed = true; results.append(.init(ok: true, summary: "Duplicated section"))
        case let .canvasAdd(block, element):
            guard let index = index(of: block), blocks[index].type == "canvas" else { skip("Skipped — canvas section not found"); continue }
            var elements = canvasElements(blocks[index])
            guard elements.count < 200 else { skip("Skipped — canvas is full"); continue }
            guard let kind = element["kind"]?.stringValue, ["heading", "text", "image", "button"].contains(kind) else { skip("Skipped — unknown canvas element kind"); continue }
            var newElement: [String: JSONValue] = ["id": .string(String(UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(8))), "kind": .string(kind)]
            for field in ["text", "src", "alt", "href", "style"] where element[field] != nil { newElement[field] = element[field] }
            newElement["d"] = element["d"] ?? .object(["x": .number(1), "y": .number(canvasY(elements)), "w": .number(8), "h": .number(2)])
            elements.append(newElement)
            blocks[index].fields["elements"] = .array(elements.map { .object($0) })
            changed = true; results.append(.init(ok: true, summary: "Added element to canvas"))
        case let .canvasUpdate(block, elementID, patch):
            guard let index = index(of: block), blocks[index].type == "canvas" else { skip("Skipped — canvas section not found"); continue }
            var elements = canvasElements(blocks[index])
            guard let elementIndex = elements.firstIndex(where: { $0["id"]?.stringValue == elementID }) else { skip("Skipped — element no longer exists"); continue }
            for (field, value) in patch where field != "id" && field != "kind" { elements[elementIndex][field] = value }
            blocks[index].fields["elements"] = .array(elements.map { .object($0) })
            changed = true; results.append(.init(ok: true, summary: "Updated canvas element"))
        case let .canvasRemove(block, elementID):
            guard let index = index(of: block), blocks[index].type == "canvas" else { skip("Skipped — canvas section not found"); continue }
            var elements = canvasElements(blocks[index])
            guard elements.contains(where: { $0["id"]?.stringValue == elementID }) else { skip("Skipped — element no longer exists"); continue }
            elements.removeAll { $0["id"]?.stringValue == elementID }
            blocks[index].fields["elements"] = .array(elements.map { .object($0) })
            changed = true; results.append(.init(ok: true, summary: "Removed element from canvas"))
        case .generateImage: skip("Skipped — image generation requires the async image service")
        case .unrecognized: skip("Skipped — unrecognized op")
        }
    }
    return MerlinApplyResult(blocks: blocks, theme: theme, results: results, tempIdMap: tempIdMap, changed: changed)
}
