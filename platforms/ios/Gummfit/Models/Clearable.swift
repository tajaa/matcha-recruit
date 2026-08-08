import Foundation

/// PATCH-body wrapper distinguishing "field not sent" from "field explicitly
/// cleared to null". Swift's synthesized `Encodable` calls `encodeIfPresent`
/// on every `Optional` property, which skips `nil` entirely — but the
/// server's `build_patch` (keyed off Pydantic's `model_fields_set`,
/// server/app/cappe/routes/_shared.py:105-122) treats an explicit JSON
/// `null` as "clear this nullable column" and an absent key as "leave
/// untouched". A plain `Optional` field can therefore only ever leave a
/// value in place, never clear it. Types with nullable PATCH fields (product
/// photo/description/SKU/category/digital-file-url, order carrier/tracking)
/// use this instead and write a manual `encode(to:)`.
enum Clearable<T: Encodable> {
    /// Omit the key — the server leaves the column untouched.
    case unset
    /// Send an explicit JSON `null` — the server clears the column.
    case clear
    /// Send the value.
    case value(T)

    var isPresent: Bool {
        if case .unset = self { return false }
        return true
    }

    func encode<Key: CodingKey>(to container: inout KeyedEncodingContainer<Key>, forKey key: Key) throws {
        switch self {
        case .unset: return
        case .clear: try container.encodeNil(forKey: key)
        case .value(let v): try container.encode(v, forKey: key)
        }
    }
}

extension Clearable where T == String {
    /// Builds `.clear` for an emptied field, `.value` for a non-empty one,
    /// `.unset` when the caller hasn't touched the field at all — the
    /// common "trimmed text field" case across the Catalog/Sales forms.
    static func from(_ text: String, touched: Bool) -> Clearable<String> {
        guard touched else { return .unset }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? .clear : .value(trimmed)
    }
}
