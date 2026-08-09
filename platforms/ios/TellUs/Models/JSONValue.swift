import Foundation

/// A decoded-but-unmodelled JSON value.
///
/// Exists so a document this build doesn't fully understand can still be
/// re-encoded byte-for-byte instead of being silently reshaped. Swift's Codable
/// has no equivalent of "keep whatever else was here", so this is the standard
/// stand-in.
enum JSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            // Bool BEFORE Double: JSONDecoder will happily read `true` as 1.
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "unsupported JSON value"
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .number(let v):
            // Re-encode a whole number as an integer. Round-tripping 400 as
            // 400.0 is valid JSON but changes the bytes, and the parity test
            // compares documents rather than values.
            if v == v.rounded() && abs(v) < 9_007_199_254_740_992 {
                try container.encode(Int(v))
            } else {
                try container.encode(v)
            }
        case .bool(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }

    var stringValue: String? { if case .string(let v) = self { return v }; return nil }
    var doubleValue: Double? { if case .number(let v) = self { return v }; return nil }
    var objectValue: [String: JSONValue]? { if case .object(let v) = self { return v }; return nil }
}
