import Foundation

struct Config {
    let apiBase: URL
    let slug: String
    let origin: URL
    let scheme: String
    let displayName: String
    let tagline: String
    static let current = Config(info: Bundle.main.infoDictionary ?? [:], environment: ProcessInfo.processInfo.environment)

    init(info: [String: Any], environment: [String: String] = [:]) {
        var base = info["CappeAPIBase"] as? String ?? "https://gummfit.com/api/cappe"
        #if DEBUG
        base = environment["CAPPE_API_URL"] ?? base
        #endif
        apiBase = URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/")))!
        slug = info["CappeSiteSlug"] as? String ?? "ahnimal"
        origin = URL(string: info["CappeSiteOrigin"] as? String ?? "https://ahnimal.gummfit.com")!
        scheme = info["AppURLScheme"] as? String ?? "ahnimal"
        displayName = info["CappeDisplayName"] as? String ?? info["CFBundleDisplayName"] as? String ?? "Store"
        tagline = info["CappeTagline"] as? String ?? "Thoughtful products, delivered."
    }
    var sitePath: String { "/public/sites/\(slug)" }
    var shopperPath: String { sitePath + "/shopper" }
    var returnURL: String { origin.absoluteString + "/__cappe/app-return" }
}

enum DeepLinkHandler {
    static func token(from url: URL, scheme: String = Config.current.scheme) -> String? {
        guard url.scheme == scheme, url.host == "order" else { return nil }
        let token = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return valid(token) ? token : nil
    }
    static func token(from payload: [AnyHashable: Any]) -> String? {
        guard payload["type"] as? String == "order", let token = payload["order_token"] as? String, valid(token) else { return nil }
        return token
    }
    static func valid(_ token: String) -> Bool { token.range(of: "^[0-9a-f]{32}$", options: .regularExpression) != nil }
}
