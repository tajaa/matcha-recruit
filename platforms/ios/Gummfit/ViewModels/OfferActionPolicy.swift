import Foundation

enum OfferActionPolicy {
    static func actions(side: String, status: String) -> Set<String> {
        if ["sent", "negotiating"].contains(status) {
            return side == "creator" ? ["accept", "decline"] : ["withdraw"]
        }
        if ["accepted", "active"].contains(status) { return ["cancel"] }
        return []
    }
}
