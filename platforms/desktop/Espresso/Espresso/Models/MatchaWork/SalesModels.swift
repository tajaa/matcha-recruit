import Foundation
import Observation

struct SalesCampaign: Decodable, Identifiable {
    let id: String
    let title: String
    let target: String
    let offer: String
    let footer: String?
    let status: String
    let sender: String?
    let error: String?
    let next_attempt_at: String?
    /// Commercial email needs an opt-out line and a postal address; the server
    /// refuses to approve a batch until the footer has them.
    var needsFooter: Bool { SalesFooter.isMissing(footer ?? "") }
}

enum SalesFooter {
    static let placeholder = "[Your business name and postal address]"
    static let suggestion = "If you'd rather not hear from me, reply \"unsubscribe\" and I won't email you again.\n\(placeholder)"
    static func isMissing(_ footer: String) -> Bool {
        let text = footer.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty || text.contains(placeholder)
    }
}

struct SalesProspect: Decodable, Identifiable {
    let id: String
    let email: String
    let name: String
    let company: String
    let website: String
    let notes: String
    let research: String
    let sources: [String]
    let subject: String
    let body: String
    let stage: String
    let status: String
    let error: String?
    let review_token: String
    var title: String { !name.isEmpty ? name : (!company.isEmpty ? company : email) }
    var editable: Bool { ["prospect", "draft", "failed"].contains(status) }
    var statusLabel: String {
        switch status {
        case "unknown": "Delivery unconfirmed"
        case "opted_out": "Do not contact"
        default: status.capitalized
        }
    }
}

struct SalesSnapshot: Decodable {
    let campaign: SalesCampaign
    let prospects: [SalesProspect]
    let counts: [String: Int]
}

/// The cheap 15-second poll: no message text, just enough to see a change.
struct SalesStatus: Decodable {
    struct Item: Decodable { let id: String; let status: String; let error: String?; let review_token: String }
    let campaign: SalesCampaign
    let counts: [String: Int]
    let prospects: [Item]
}

/// Another editor's campaign in this workspace: a summary, never their contacts.
struct SalesWorkspaceCampaign: Decodable, Identifiable {
    let id: String
    let title: String
    let status: String
    let creator: String
    let prospects: Int
    let sent: Int
    let problems: Int
}

enum SalesBatch {
    /// Matches the server's cap: small enough to read every message approved.
    static let limit = 50
}

struct SalesContact: Encodable, Equatable {
    var email = ""
    var name = ""
    var company = ""
    var website = ""
    var notes = ""
}

/// Strict bounded CSV/TSV import: quoted commas, escaped quotes and multiline
/// fields are supported. Bad rows fail the whole import, with their row number.
/// Common CRM column names are recognised and other columns are ignored.
enum SalesCSV {
    struct Invalid: LocalizedError {
        let errorDescription: String?
        init(_ message: String) { errorDescription = message }
    }
    /// Normalized header (lowercase letters and digits only) -> field.
    static let aliases: [String: String] = [
        "email": "email", "emailaddress": "email", "workemail": "email", "businessemail": "email", "contactemail": "email",
        "name": "name", "fullname": "name", "contactname": "name", "contact": "name",
        "firstname": "first", "givenname": "first",
        "lastname": "last", "surname": "last", "familyname": "last",
        "company": "company", "companyname": "company", "organization": "company", "organisation": "company",
        "business": "company", "account": "company", "accountname": "company",
        "website": "website", "websiteurl": "website", "url": "website", "domain": "website", "companywebsite": "website", "web": "website",
        "notes": "notes", "note": "notes", "description": "notes",
    ]
    static func field(forHeader header: String) -> String? {
        aliases[header.lowercased().filter { $0.isLetter || $0.isNumber }]
    }
    static func parse(_ input: String) throws -> [SalesContact] {
        guard input.utf8.count <= 1_000_000 else { throw Invalid("Import at most 1 MB at a time.") }
        let text = input.replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n").trimmingCharacters(in: CharacterSet(charactersIn: "\u{FEFF}"))
        let delimiter: Character = text.prefix(while: { $0 != "\n" }).contains("\t") ? "\t" : ","
        var rows: [[String]] = [], row: [String] = [], field = ""
        var quoted = false, afterQuote = false, index = text.startIndex
        func appendRow() {
            row.append(field.trimmingCharacters(in: .whitespacesAndNewlines))
            if row.contains(where: { !$0.isEmpty }) { rows.append(row) }
            row = []; field = ""; afterQuote = false
        }
        while index < text.endIndex {
            let c = text[index]
            let next = text.index(after: index)
            if quoted {
                if c == "\"" {
                    if next < text.endIndex && text[next] == "\"" { field.append("\""); index = text.index(after: next); continue }
                    quoted = false; afterQuote = true
                } else { field.append(c) }
            } else if c == delimiter {
                row.append(field.trimmingCharacters(in: .whitespacesAndNewlines)); field = ""; afterQuote = false
            } else if c == "\n" {
                appendRow()
            } else if c == "\"" {
                guard field.isEmpty && !afterQuote else { throw Invalid("Unexpected quote on row \(rows.count + 1).") }
                quoted = true
            } else {
                guard !afterQuote || c.isWhitespace else { throw Invalid("Unexpected text after a quote on row \(rows.count + 1).") }
                field.append(c)
            }
            index = next
        }
        guard !quoted else { throw Invalid("An import field has an unclosed quote.") }
        appendRow()
        guard let first = rows.first else { throw Invalid("Paste email addresses or a CSV with an email, name, company or website column.") }
        let mapped = first.map(field(forHeader:))
        let hasHeader = mapped.contains { $0 != nil }
        if hasHeader {
            let known = mapped.compactMap { $0 }
            guard Set(known).count == known.count else {
                throw Invalid("Each of email, name, company, website and notes can appear in only one column.")
            }
            if known.contains("name") && (known.contains("first") || known.contains("last")) {
                throw Invalid("Use either a full-name column or first/last name columns, not both.")
            }
        }
        let data = hasHeader ? Array(rows.dropFirst()) : rows
        guard !data.isEmpty && data.count <= 1000 else { throw Invalid("Import between 1 and 1,000 prospects.") }
        return try data.enumerated().map { offset, values in
            let line = offset + (hasHeader ? 2 : 1)
            guard values.count == (hasHeader ? first.count : 1) else { throw Invalid("Row \(line) has the wrong number of fields. Use a header row for CSV contacts.") }
            var fields: [String: String] = [:]
            if hasHeader {
                // Columns we don't recognise (phone, title, owner…) are ignored.
                for (key, value) in zip(mapped, values) { if let key { fields[key] = value } }
            } else { fields["email"] = values[0] }
            let email = (fields["email"] ?? "").lowercased()
            if !email.isEmpty && (email.count > 254 || email.range(of: #"^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$"#, options: .regularExpression) == nil) {
                throw Invalid("Row \(line) needs one complete email address.")
            }
            let parts = [fields["first"] ?? "", fields["last"] ?? ""].filter { !$0.isEmpty }
            let name = fields["name"] ?? parts.joined(separator: " ")
            let company = fields["company"] ?? "", notes = fields["notes"] ?? ""
            var website = fields["website"] ?? ""
            if !website.isEmpty && !website.contains("://") { website = "https://" + website }
            if !website.isEmpty {
                guard let url = URLComponents(string: website), ["http", "https"].contains(url.scheme ?? ""),
                      url.host?.isEmpty == false, url.user == nil, url.password == nil else { throw Invalid("Row \(line) has an invalid website.") }
            }
            guard name.count <= 200 && company.count <= 200 && notes.count <= 4000 && website.count <= 2000 else { throw Invalid("Row \(line) has a field that is too long.") }
            guard !email.isEmpty || !name.isEmpty || !company.isEmpty || !website.isEmpty else { throw Invalid("Row \(line) needs a contact or business.") }
            return SalesContact(email: email, name: name, company: company, website: website, notes: notes)
        }
    }
}

struct AssistantSalesContext: AssistantHandoff {
    let id = UUID()
    let owner: String
    let campaignId: String
    let projectId: String
    let title: String
    var prompt: String {
        "Work on my sales campaign \(campaignId) in workspace \(projectId). Read the saved campaign, target, offer and prospects first. Discover prospects matching my target if needed, research them using public source links, and save personalized email drafts. Work in batches and report how many remain. I will review and send in Sales.\n\nMy instructions: "
    }
}
