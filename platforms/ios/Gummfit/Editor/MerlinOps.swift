import Foundation

enum MerlinOp {
    case setField(block: String, path: String, value: JSONValue)
    case setDesign(block: String, group: String, key: String, value: JSONValue)
    case setDesignBulk(blocks: [String], design: [String: [String: JSONValue]])
    case addBlock(type: String, at: Int, content: [String: JSONValue]?, design: [String: JSONValue]?, preset: String?, id: String?)
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
        switch name {
        case "set_field": self = .setField(block: string("block"), path: string("path"), value: object["value"] ?? .null)
        case "set_design": self = .setDesign(block: string("block"), group: string("group"), key: string("key"), value: object["value"] ?? .null)
        case "remove_block": self = .removeBlock(block: string("block"))
        case "move_block": self = .moveBlock(block: string("block"), to: object["to"]?.intValue ?? 0)
        case "set_theme": self = .setTheme(key: string("key"), value: object["value"] ?? .null)
        case "duplicate_block": self = .duplicateBlock(block: string("block"), at: object["at"]?.intValue, id: object["id"]?.stringValue)
        case "generate_image": self = .generateImage(block: string("block"), field: object["field"]?.stringValue, background: object["background"]?.boolValue ?? false, prompt: string("prompt"), aspect: object["aspect"]?.stringValue, imageSize: object["image_size"]?.stringValue)
        default: self = .unrecognized
        }
    }
}

struct MerlinApplyResult {
    var blocks: [CappeBlock]
    var theme: [String: JSONValue]
    var results: [CappeMerlinOpResult]
    var tempIdMap: [String: String]
    var changed: Bool
}

func deepSet(_ target: JSONValue?, _ parts: ArraySlice<String>, _ value: JSONValue) -> (ok: Bool, value: JSONValue?) {
    guard let target else { return (false, nil) }
    guard let head = parts.first else { return (true, value) }
    let rest = parts.dropFirst()
    switch target {
    case .object(var object):
        guard let child = object[head] else { return (false, nil) }
        let result = deepSet(child, rest, value)
        guard result.ok, let updated = result.value else { return (false, nil) }
        object[head] = updated
        return (true, .object(object))
    case .array(var array):
        guard let index = Int(head), index >= 0, index <= array.count else { return (false, nil) }
        if index == array.count {
            guard !rest.isEmpty else { array.append(value); return (true, .array(array)) }
            return (false, nil)
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
    guard let head = parts.first, !RESERVED_PATH_KEYS.contains(head) else { return nil }
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
        guard let id = value.stringValue, let preset = schema?.preset(id) else { return nil }
        result = preset.config
        result["preset"] = .string(id)
        return result
    }
    let parts = key.split(separator: ".").map(String.init)
    guard let head = parts.first else { return nil }
    if parts.count == 1 {
        if value.isNull { result.removeValue(forKey: head) } else { result[head] = value }
        return result
    }
    var group = result[head]?.objectValue ?? [:]
    if value.isNull { group.removeValue(forKey: parts[1]) } else { group[parts[1]] = value }
    result[head] = .object(group)
    if key == "colors.brand", let color = value.stringValue {
        group["accent"] = value
        group["brandText"] = .string(contrastText(color))
        result[head] = .object(group)
    }
    if key == "mode" { return result }
    return result
}

func applyMerlinOps(blocks: [CappeBlock], theme: [String: JSONValue], ops: [MerlinOp], schema: CappeEditorSchema?) -> MerlinApplyResult {
    var blocks = blocks
    var theme = theme
    var results: [CappeMerlinOpResult] = []
    var tempIdMap: [String: String] = [:]
    var changed = false
    func key(_ value: String) -> String { tempIdMap[value] ?? value }
    for op in ops {
        switch op {
        case let .setField(block, path, value):
            guard let index = blocks.firstIndex(where: { $0._k == key(block) }), let updated = applyFieldPath(block: blocks[index], path: path, value: value) else { results.append(.init(ok: false, summary: "Skipped — section no longer exists")); continue }
            blocks[index] = updated; changed = true; results.append(.init(ok: true, summary: "Updated \(path)"))
        case let .setTheme(key, value):
            guard let updated = applyThemeOp(theme, key: key, value: value, schema: schema) else { results.append(.init(ok: false, summary: "Skipped — unknown theme preset")); continue }
            theme = updated; changed = true; results.append(.init(ok: true, summary: "Updated theme"))
        case let .removeBlock(block):
            guard let index = blocks.firstIndex(where: { $0._k == key(block) }) else { results.append(.init(ok: false, summary: "Skipped — section no longer exists")); continue }
            blocks.remove(at: index); changed = true; results.append(.init(ok: true, summary: "Removed section"))
        case let .moveBlock(block, to):
            guard let from = blocks.firstIndex(where: { $0._k == key(block) }) else { results.append(.init(ok: false, summary: "Skipped — section no longer exists")); continue }
            let item = blocks.remove(at: from); blocks.insert(item, at: min(max(0, to), blocks.count)); changed = true; results.append(.init(ok: true, summary: "Moved section"))
        case let .duplicateBlock(block, at, id):
            guard let source = blocks.first(where: { $0._k == key(block) }) else { results.append(.init(ok: false, summary: "Skipped — section no longer exists")); continue }
            let clone = source.cloned(); let cloneKey = id ?? clone._k; tempIdMap[cloneKey] = clone._k; blocks.insert(clone, at: min(max(0, at ?? (blocks.firstIndex(where: { $0._k == key(block) })! + 1)), blocks.count)); changed = true; results.append(.init(ok: true, summary: "Duplicated section"))
        case .generateImage: results.append(.init(ok: true, summary: "Image generation queued"))
        default: results.append(.init(ok: false, summary: "Skipped — unsupported op"))
        }
    }
    return MerlinApplyResult(blocks: blocks, theme: theme, results: results, tempIdMap: tempIdMap, changed: changed)
}
