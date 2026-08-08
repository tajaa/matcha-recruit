import Foundation

/// The `location_id`/`shared` query-string contract shared by every
/// whole-set-replace endpoint (availability, rate-rules, discounts). Mirrors
/// `_loc_filter` in server/app/cappe/routes/bookings.py and the equivalent
/// inline logic in discounts.py:
///   - `shared=true`      → only the location-agnostic (shared) rows
///   - a concrete `locationId` → that location's rows PLUS shared rows
///   - neither          → every row across every location
/// On a PUT, the `location_id` query param (not any per-row field) decides
/// which existing rows get deleted and what the new rows are stamped with —
/// so a GET that doesn't pass `shared: true` when `locationId == nil` reads
/// a wider set than the following PUT will replace, silently duplicating
/// every location-scoped row as a new shared one.
enum LocationQuery {
    static func string(_ locationId: String?, shared: Bool = false) -> String {
        if shared { return "?shared=true" }
        if let locationId { return "?location_id=\(locationId)" }
        return ""
    }
}
