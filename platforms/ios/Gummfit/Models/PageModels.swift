import Foundation

enum CappePageStatus: String, Codable {
    case draft
    case published
    case archived
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = CappePageStatus(rawValue: raw) ?? .unknown
    }

    var isWritable: Bool { self != .unknown }
}

struct CappePage: Codable, Identifiable, Hashable {
    let id: String
    let site_id: String
    var title: String
    var slug: String
    var content: [String: JSONValue]
    var sort_order: Int
    var status: CappePageStatus
    let created_at: String
    let updated_at: String

    private enum CodingKeys: String, CodingKey {
        case id, site_id, title, slug, content, sort_order, status, created_at, updated_at
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        site_id = try container.decode(String.self, forKey: .site_id)
        title = try container.decode(String.self, forKey: .title)
        slug = try container.decode(String.self, forKey: .slug)
        var decodedContent = try container.decode([String: JSONValue].self, forKey: .content)
        if let values = decodedContent["blocks"]?.arrayValue {
            decodedContent["blocks"] = .array(values.map { value in
                guard var fields = value.objectValue else { return value }
                if fields["_k"]?.stringValue?.isEmpty != false {
                    fields["_k"] = .string(UUID().uuidString)
                }
                return .object(fields)
            })
        }
        content = decodedContent
        sort_order = try container.decode(Int.self, forKey: .sort_order)
        status = try container.decode(CappePageStatus.self, forKey: .status)
        created_at = try container.decode(String.self, forKey: .created_at)
        updated_at = try container.decode(String.self, forKey: .updated_at)
    }

    var blocks: [CappeBlock] {
        guard let values = content["blocks"]?.arrayValue else { return [] }
        return values.compactMap { value in
            guard let fields = value.objectValue else { return nil }
            return CappeBlock(fields: fields)
        }
    }
}

struct CappePageCreate: Encodable {
    let title: String
    let slug: String?
    let content: [String: JSONValue]
    let sort_order: Int
    let status: String
}

struct CappePageUpdate: Encodable {
    let title: String?
    let slug: String?
    let content: [String: JSONValue]?
    let sort_order: Int?
    let status: String?
}

struct CappePagePreviewRequest: Encodable {
    let title: String?
    let slug: String?
    let content: [String: JSONValue]
    let theme_config: [String: JSONValue]?
    let meta_config: [String: JSONValue]?
    let editable: Bool
}

struct CappeBlock: Codable, Identifiable, Hashable {
    var fields: [String: JSONValue]

    init(fields: [String: JSONValue]) {
        self.fields = fields
    }

    init(from decoder: Decoder) throws {
        var decoded = try [String: JSONValue](from: decoder)
        if decoded["_k"]?.stringValue?.isEmpty != false {
            decoded["_k"] = .string(UUID().uuidString)
        }
        fields = decoded
    }

    func encode(to encoder: Encoder) throws {
        try fields.encode(to: encoder)
    }

    var type: String { fields["type"]?.stringValue ?? "" }
    var _k: String { fields["_k"]?.stringValue ?? "" }
    var id: String { _k }
    var design: [String: JSONValue] { fields["_design"]?.objectValue ?? [:] }

    static func make(fromSchemaDefault value: [String: JSONValue]) -> CappeBlock {
        CappeBlock(fields: value).withKey()
    }

    func withKey(_ key: String = UUID().uuidString) -> CappeBlock {
        var copy = self
        copy.fields["_k"] = .string(key)
        return copy
    }

    func strippingKey() -> CappeBlock {
        var copy = self
        copy.fields.removeValue(forKey: "_k")
        return copy
    }

    func cloned() -> CappeBlock {
        var copy = self.withKey()
        if let design = copy.fields["_design"]?.objectValue,
           design["anchor"]?.objectValue?["id"]?.stringValue != nil {
            var withoutAnchor = design
            withoutAnchor.removeValue(forKey: "anchor")
            copy.fields["_design"] = .object(withoutAnchor)
        }
        if var elements = copy.fields["elements"]?.arrayValue {
            elements = elements.map { element in
                guard var object = element.objectValue else { return element }
                object["id"] = .string(UUID().uuidString)
                return .object(object)
            }
            copy.fields["elements"] = .array(elements)
        }
        return copy
    }
}
