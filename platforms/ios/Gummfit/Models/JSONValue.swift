import Foundation

/// Untyped JSON bags returned by form submissions and creator portfolio metrics.
/// Keeping this lossless avoids pretending those server-defined fields are strings.
enum JSONValue: Codable, Hashable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) }
        else { self = .array(try c.decode([JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws { var c = encoder.singleValueContainer(); switch self { case .string(let v): try c.encode(v); case .number(let v): try c.encode(v); case .bool(let v): try c.encode(v); case .object(let v): try c.encode(v); case .array(let v): try c.encode(v); case .null: try c.encodeNil() } }
}

extension JSONValue {
    var stringValue: String? { if case .string(let value) = self { return value }; return nil }
    var doubleValue: Double? { if case .number(let value) = self { return value }; return nil }
    var intValue: Int? {
        guard let value = doubleValue, value.isFinite else { return nil }
        if value >= Double(Int.max) { return Int.max }
        if value <= Double(Int.min) { return Int.min }
        return Int(value)
    }
    var boolValue: Bool? { if case .bool(let value) = self { return value }; return nil }
    var objectValue: [String: JSONValue]? { if case .object(let value) = self { return value }; return nil }
    var arrayValue: [JSONValue]? { if case .array(let value) = self { return value }; return nil }
    var isNull: Bool { if case .null = self { return true }; return false }

    static func from(_ any: Any) -> JSONValue {
        if let number = any as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return .bool(number.boolValue)
            }
            return .number(number.doubleValue)
        }
        switch any {
        case is NSNull:
            return .null
        case let value as String:
            return .string(value)
        case let value as Int:
            return .number(Double(value))
        case let value as Double:
            return .number(value)
        case let value as Float:
            return .number(Double(value))
        case let value as [String: Any]:
            return .object(value.mapValues(JSONValue.from))
        case let value as [Any]:
            return .array(value.map(JSONValue.from))
        default:
            return .null
        }
    }

    var anyValue: Any? {
        switch self {
        case .string(let value): return value
        case .number(let value): return value
        case .bool(let value): return value
        case .object(let value): return value.mapValues { $0.anyValue ?? NSNull() }
        case .array(let value): return value.map { $0.anyValue ?? NSNull() }
        case .null: return NSNull()
        }
    }
}
