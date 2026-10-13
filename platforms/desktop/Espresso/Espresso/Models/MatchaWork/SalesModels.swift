import Foundation
import Observation

struct SalesCampaign: Decodable, Identifiable {
    let id: String
    let title: String
    let target: String
    let offer: String
    let status: String
    let sender: String?
    let error: String?
    let next_attempt_at: String?
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
}

struct SalesSnapshot: Decodable {
    let campaign: SalesCampaign
    let prospects: [SalesProspect]
    let counts: [String: Int]
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
enum SalesCSV {
    struct Invalid: LocalizedError {
        let errorDescription: String?
        init(_ message: String) { errorDescription = message }
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
        guard let first = rows.first else { throw Invalid("Paste email addresses or a CSV with email,name,company,website,notes headers.") }
        let allowed = ["email", "name", "company", "website", "notes"]
        let headers = first.map { $0.lowercased() }
        let hasHeader = headers.contains(where: { allowed.contains($0) })
        if hasHeader && (Set(headers).count != headers.count || headers.contains(where: { !allowed.contains($0) })) {
            throw Invalid("Use unique headers: email, name, company, website, notes.")
        }
        let data = hasHeader ? Array(rows.dropFirst()) : rows
        guard !data.isEmpty && data.count <= 1000 else { throw Invalid("Import between 1 and 1,000 prospects.") }
        return try data.enumerated().map { offset, values in
            let line = offset + (hasHeader ? 2 : 1)
            guard values.count == (hasHeader ? headers.count : 1) else { throw Invalid("Row \(line) has the wrong number of fields. Use a header row for CSV contacts.") }
            let fields = Dictionary(uniqueKeysWithValues: zip(hasHeader ? headers : ["email"], values))
            let email = (fields["email"] ?? "").lowercased()
            if !email.isEmpty && (email.count > 254 || email.range(of: #"^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$"#, options: .regularExpression) == nil) {
                throw Invalid("Row \(line) needs one complete email address.")
            }
            let name = fields["name"] ?? "", company = fields["company"] ?? "", notes = fields["notes"] ?? ""
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

struct AssistantSalesContext: Identifiable {
    let id = UUID()
    let owner: String
    let campaignId: String
    let projectId: String
    let title: String
    var prompt: String {
        "Work on my sales campaign \(campaignId) in workspace \(projectId). Read the saved campaign, target, offer and prospects first. Discover prospects matching my target if needed, research them using public source links, and save personalized email drafts. Work in batches and report how many remain. I will review and send in Sales.\n\nMy instructions: "
    }
}
