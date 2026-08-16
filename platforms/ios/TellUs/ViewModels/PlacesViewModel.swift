import Foundation
import Observation

@MainActor
@Observable
final class PlacesViewModel {
    var query = "" { didSet { queryChanged() } }
    var dbResults: [PlaceSearchResult] = []
    var suggestions: [PlaceSuggestion] = []
    var searching = false
    var searchError: String?
    var addingPlaceId: String?          // per-suggestion spinner
    var navigateToken: ScannedToken?    // reuses ScanView.swift's Identifiable wrapper
    var navigateToBrandSlug: String?    // claimed place just created — open its native page

    // Manual-add form
    var addName = ""
    var addCity = ""
    var addState = ""
    var submittingManual = false
    var manualError: String?
    var showManualForm = false          // forced open after a 503 fallback

    private var searchTask: Task<Void, Never>?
    private var sessionToken = UUID().uuidString

    var noMatches: Bool {
        query.trimmingCharacters(in: .whitespaces).count >= 2
            && !searching && searchError == nil
            && dbResults.isEmpty && suggestions.isEmpty
    }

    private func queryChanged() {
        searchTask?.cancel()
        showManualForm = false
        manualError = nil
        let q = query.trimmingCharacters(in: .whitespaces)
        guard q.count >= 2 else {
            dbResults = []
            suggestions = []
            searchError = nil
            searching = false
            return
        }
        searching = true                                      // sync, matches web's setSearching(true)
        searchTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 450_000_000)   // debounce, matches web Places.tsx
            guard !Task.isCancelled else { return }
            await self?.runSearch(q)
        }
    }

    private func runSearch(_ q: String) async {
        defer { if !Task.isCancelled { searching = false } }
        async let dbCall = PlacesService.shared.search(q: q)
        async let acCall = PlacesService.shared.autocomplete(q: q, sessionToken: sessionToken)
        let ac = (try? await acCall) ?? []                    // autocomplete degrades silently
        do {
            let db = try await dbCall
            guard !Task.isCancelled else { return }
            dbResults = db
            suggestions = Self.dedupe(ac, against: db)
            searchError = nil
        } catch {
            guard !Task.isCancelled, !error.isCancellation else { return }
            dbResults = []                                    // web: setDbResults([]) on db error
            suggestions = ac                                  // web: okDb=[] ⇒ all ac kept
            if case APIError.httpError(429, _) = error {
                searchError = "Searching too fast — give it a second."
            } else {
                searchError = "Search failed — try again."
            }
        }
    }

    /// Pure so it's unit-testable without a network call (and without @MainActor).
    nonisolated static func dedupe(_ suggestions: [PlaceSuggestion], against db: [PlaceSearchResult]) -> [PlaceSuggestion] {
        let known = Set(db.compactMap(\.google_place_id))
        return suggestions.filter { !known.contains($0.place_id) }
    }

    func selectSuggestion(_ s: PlaceSuggestion) async {
        guard addingPlaceId == nil else { return }
        addingPlaceId = s.place_id
        defer { addingPlaceId = nil }
        let req = PlaceCreateRequest(name: s.name, google_place_id: s.place_id, session_token: sessionToken)
        sessionToken = UUID().uuidString                     // session ends on select, success or not
        do {
            handleCreated(try await PlacesService.shared.create(req))
        } catch {
            // 503 (Google Details lookup down) or anything else: fall back to manual add.
            addName = s.name
            showManualForm = true
            manualError = error.localizedDescription
        }
    }

    func submitManual() async {
        let name = addName.trimmingCharacters(in: .whitespaces)
        let city = addCity.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty, !city.isEmpty else {
            manualError = "Name and city are required."
            return
        }
        submittingManual = true
        defer { submittingManual = false }
        do {
            let state = addState.trimmingCharacters(in: .whitespaces)
            let resp = try await PlacesService.shared.create(
                PlaceCreateRequest(name: name, city: city, state: state.isEmpty ? nil : state)
            )
            handleCreated(resp)
        } catch {
            manualError = error.localizedDescription
        }
    }

    private func handleCreated(_ resp: PlaceCreateResponse) {
        if let token = resp.intake_token {
            navigateToken = ScannedToken(target: .intake(token))
        } else {
            navigateToBrandSlug = resp.slug
        }
    }
}
