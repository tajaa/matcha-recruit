import SwiftUI

struct Avatar: View {
    enum Size { case compact, row, header
        var points: CGFloat { switch self { case .compact: 28; case .row: 40; case .header: 88 } }
        var font: Font { switch self { case .compact: .interCaption; case .row: .interSubheadline; case .header: .interTitle2 } }
    }

    private let displayName: String?
    private let accountId: String
    private let imageURL: String?
    private let size: Size
    private let ringed: Bool

    init(displayName: String?, accountId: String, imageURL: String? = nil, size: Size, ringed: Bool = false) {
        self.displayName = displayName; self.accountId = accountId; self.imageURL = imageURL
        self.size = size; self.ringed = ringed
    }

    init(_ person: FriendSummary, size: Size, ringed: Bool = false) {
        self.init(displayName: person.display_name, accountId: person.account_id, imageURL: person.avatar_url, size: size, ringed: ringed)
    }

    init(_ profile: FriendProfile, size: Size, ringed: Bool = false) {
        self.init(displayName: profile.display_name, accountId: profile.account_id, imageURL: profile.avatar_url, size: size, ringed: ringed)
    }

    init(_ account: TellusAccount, size: Size, ringed: Bool = false) {
        self.init(displayName: account.handle, accountId: account.id, imageURL: account.avatar_url, size: size, ringed: ringed)
    }

    var body: some View {
        initialsView
            .frame(width: size.points, height: size.points)
            .clipShape(Circle())
            .overlay(Circle().stroke(ringed ? TU.ember : TU.hairline, lineWidth: ringed ? 2 : 1))
            .overlay {
                if let imageURL, let url = URL(string: imageURL) {
                    AsyncImage(url: url) { phase in
                        if case .success(let image) = phase { image.resizable().scaledToFill() }
                        else { initialsView }
                    }
                    .clipShape(Circle())
                }
            }
    }

    private var tint: Color { Self.palette[Self.paletteIndex(for: accountId)] }
    private var initialsView: some View {
        Circle().fill(tint.opacity(0.18)).overlay(Text(Self.initials(from: displayName)).font(size.font).foregroundStyle(tint))
    }

    static func initials(from displayName: String?) -> String {
        let clusters = (displayName ?? "").split(whereSeparator: { $0.isWhitespace }).compactMap { $0.first }
        guard !clusters.isEmpty else { return "?" }
        let value = clusters.count == 1 ? String(clusters[0]) : String(clusters.prefix(2))
        return value.trimmingCharacters(in: .punctuationCharacters).isEmpty ? "?" : value.uppercased()
    }

    static func paletteIndex(for accountId: String) -> Int {
        var hash: UInt64 = 14695981039346656037
        for byte in accountId.utf8 { hash ^= UInt64(byte); hash &*= 1099511628211 }
        return Int(hash % UInt64(palette.count))
    }

    static let palette: [Color] = [TU.ember, TU.emberHot, TU.emberDeep,
                                    Color(red: 0.30, green: 0.52, blue: 0.72),
                                    Color(red: 0.42, green: 0.62, blue: 0.52),
                                    Color(red: 0.56, green: 0.42, blue: 0.66)]
}
