import Foundation
import EventKit
import CryptoKit

/// EventKit owns provider sync (iCloud, Google accounts added to Calendar,
/// and local calendars). Only selected calendars are shared with Espresso.
@MainActor
@Observable
final class AppleCalendarSync {
    static let shared = AppleCalendarSync()
    static let didSync = Notification.Name("espresso.appleCalendarDidSync")
    private let store = EKEventStore()
    private let client = APIClient.shared
    private let base = "/matcha-work/calendar/apple"
    private var userID: String?
    private var loop: Task<Void, Never>?
    private var generation = 0
    private var syncing = false
    private(set) var configuration: AppleCalendarConfiguration?
    private(set) var calendars: [AppleCalendarDescriptor] = []
    private(set) var lastSync: Date?
    var error: String?

    private func key(_ user: String) -> String { "espresso.appleCalendar.\(user)" }

    func bind(userID: String?) {
        generation &+= 1
        loop?.cancel()
        loop = nil
        self.userID = userID
        configuration = nil
        calendars = []
        lastSync = nil
        error = nil
        if let userID, let data = UserDefaults.standard.data(forKey: key(userID)) {
            configuration = try? JSONDecoder().decode(AppleCalendarConfiguration.self, from: data)
        }
        if configuration != nil { startLoop() }
    }

    func requestAccess() async throws {
        let owner = userID
        let started = generation
        guard owner != nil else { throw SyncError("Sign in first.") }
        let granted = try await store.requestFullAccessToEvents()
        guard userID == owner, generation == started else { throw SyncError("The signed-in account changed.") }
        guard granted else { throw SyncError("Allow Calendar access in macOS Privacy & Security settings.") }
        calendars = store.calendars(for: .event).map {
            AppleCalendarDescriptor(id: $0.calendarIdentifier,
                title: String("\($0.title) · \($0.source.title)".prefix(300)), editable: $0.allowsContentModifications)
        }.sorted { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
    }

    func connect(selected: Set<String>, destination: String) async throws {
        guard let owner = userID else { throw SyncError("Sign in first.") }
        generation &+= 1
        let started = generation
        let config = AppleCalendarConfiguration(user_id: owner, connection_id: UUID(),
            calendars: calendars.filter { selected.contains($0.id) }, destination: destination)
        guard config.calendars.contains(where: { $0.id == destination && $0.editable }) else {
            throw SyncError("Choose a writable destination calendar.")
        }
        struct OK: Decodable { let ok: Bool }
        let _: OK = try await client.request(method: "PUT", path: base, body: config)
        guard owner == userID, generation == started else { return }
        configuration = config
        UserDefaults.standard.set(try JSONEncoder().encode(config), forKey: key(owner))
        startLoop()
        await sync()
    }

    func disconnect(connectionID: UUID? = nil) async throws {
        guard let owner = userID, let connectionID = connectionID ?? configuration?.connection_id else { return }
        generation &+= 1
        let started = generation
        loop?.cancel()
        struct OK: Decodable { let ok: Bool }
        do {
            let _: OK = try await client.request(method: "DELETE", path: "\(base)/\(connectionID)")
        } catch {
            if owner == userID, generation == started, configuration != nil { startLoop() }
            throw error
        }
        guard owner == userID, generation == started else { return }
        configuration = nil
        generation &+= 1
        loop?.cancel()
        loop = nil
        UserDefaults.standard.removeObject(forKey: key(owner))
        lastSync = nil
        NotificationCenter.default.post(name: Self.didSync, object: nil)
    }

    func status() async throws -> AppleCalendarStatus {
        try await client.request(method: "GET", path: base)
    }

    private func startLoop() {
        loop?.cancel()
        loop = Task { [weak self] in
            while !Task.isCancelled {
                await self?.sync()
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }

    /// Never prompts in the background. Revocation stops both reads and writes.
    func sync() async {
        guard !syncing, let owner = userID, let config = configuration else { return }
        guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else {
            error = "Calendar permission is off. Reconnect in Settings > Calendars."
            return
        }
        syncing = true
        let started = generation
        defer { syncing = false }
        func stillOwner() -> Bool { userID == owner && generation == started && !Task.isCancelled }
        do {
            try await upload(config, stillOwner: stillOwner)
            guard stillOwner() else { return }
            struct Actions: Decodable { let actions: [AppleCalendarAction] }
            let batch: Actions = try await client.request(method: "POST", path: "\(base)/\(config.connection_id)/claim")
            for action in batch.actions {
                guard stillOwner(), EKEventStore.authorizationStatus(for: .event) == .fullAccess else { return }
                let abilities = try await MatchaWorkService.shared.assistantAbilities()
                guard stillOwner(), abilities.abilities.contains(where: { $0.key == "calendar" && $0.enabled && $0.commitMode == "live" }) else { return }
                var failure: String?
                do { try apply(action, configuration: config) }
                catch { failure = error.localizedDescription }
                // A lost acknowledgment never causes a second EventKit write.
                struct Result: Encodable { let status: String; let error: String? }
                struct OK: Decodable { let ok: Bool }
                guard stillOwner() else { return }
                let _: OK = try await client.request(method: "PUT",
                    path: "\(base)/\(config.connection_id)/actions/\(action.id)",
                    body: Result(status: failure == nil ? "done" : "failed", error: failure.map { String($0.prefix(300)) }))
            }
            guard stillOwner() else { return }
            if !batch.actions.isEmpty { try await upload(config, stillOwner: stillOwner) }
            guard stillOwner() else { return }
            lastSync = Date()
            error = nil
            NotificationCenter.default.post(name: Self.didSync, object: nil)
        } catch {
            if stillOwner() { self.error = error.localizedDescription }
        }
    }

    private func upload(_ config: AppleCalendarConfiguration, stillOwner: () -> Bool) async throws {
        let cal = Calendar.current
        let start = cal.date(byAdding: .day, value: -30, to: cal.startOfDay(for: Date()))!
        let end = cal.date(byAdding: .day, value: 366, to: start)!
        let selected = config.calendars.compactMap { store.calendar(withIdentifier: $0.id) }
        guard selected.count == config.calendars.count else {
            throw SyncError("A selected calendar is no longer available. Choose calendars again.")
        }
        let events = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: selected))
            .filter { $0.status != .canceled }.sorted { ($0.startDate ?? .distantPast) < ($1.startDate ?? .distantPast) }
        var seen = Set<String>()
        let rows = events.compactMap { event -> AppleCalendarEvent? in
            let row = Self.snapshot(event)
            return seen.insert(row.id).inserted ? row : nil
        }
        guard stillOwner() else { throw CancellationError() }
        struct Snapshot: Encodable {
            let connection_id: UUID; let start: String; let end: String
            let events: [AppleCalendarEvent]; let complete: Bool
        }
        struct OK: Decodable { let ok: Bool }
        let _: OK = try await client.request(method: "PUT", path: "\(base)/snapshot",
            body: Snapshot(connection_id: config.connection_id, start: CalendarWire.instantString(start),
                end: CalendarWire.instantString(end), events: Array(rows.prefix(500)), complete: rows.count <= 500))
    }

    static func snapshot(_ event: EKEvent, calendar cal: Calendar = .current) -> AppleCalendarEvent {
        let start: Date = event.startDate ?? .distantPast
        let finish: Date = event.endDate ?? start
        let end: Date = event.isAllDay
            ? cal.date(byAdding: .day, value: -1, to: finish) ?? start : finish
        let occurrence = event.occurrenceDate.map { String($0.timeIntervalSince1970) } ?? ""
        let raw = "\(event.calendar.calendarIdentifier)|\(event.calendarItemIdentifier)|\(occurrence)"
        let id = SHA256.hash(data: Data(raw.utf8)).map { String(format: "%02x", $0) }.joined()
        return AppleCalendarEvent(id: id, calendar_id: event.calendar.calendarIdentifier,
            title: String((event.title ?? "(no title)").prefix(300)),
            start: event.isAllDay ? CalendarWire.dayString(start, calendar: cal) : CalendarWire.instantString(start),
            end: event.isAllDay ? CalendarWire.dayString(max(start, end), calendar: cal) : CalendarWire.instantString(end),
            all_day: event.isAllDay, notes: event.notes.map { String($0.prefix(4000)) },
            location: event.location.map { String($0.prefix(300)) },
            modified: CalendarWire.instantString(event.lastModifiedDate ?? .distantPast),
            editable: event.calendar.allowsContentModifications && (event.attendees ?? []).isEmpty)
    }

    private func apply(_ action: AppleCalendarAction, configuration: AppleCalendarConfiguration) throws {
        let event: EKEvent
        if action.operation == "create" {
            guard let destination = store.calendar(withIdentifier: configuration.destination), destination.allowsContentModifications else {
                throw SyncError("The destination calendar is no longer writable.")
            }
            event = EKEvent(eventStore: store)
            event.calendar = destination
        } else {
            guard let expected = action.payload.event,
                  configuration.calendars.contains(where: { $0.id == expected.calendar_id }),
                  let calendar = store.calendar(withIdentifier: expected.calendar_id),
                  let start = CalendarWire.date(expected.start), let end = CalendarWire.date(expected.end) else {
                throw SyncError("The event is no longer available.")
            }
            let windowEnd = Calendar.current.date(byAdding: .day, value: 2, to: end)!
            let matches = store.events(matching: store.predicateForEvents(
                withStart: start.addingTimeInterval(-86400), end: windowEnd, calendars: [calendar]))
            guard let current = matches.first(where: { Self.snapshot($0).id == expected.id }),
                  Self.snapshot(current) == expected, expected.editable,
                  calendar.allowsContentModifications, (current.attendees ?? []).isEmpty else {
                throw SyncError("The event changed or is read-only. Refresh it before trying again.")
            }
            event = current
        }
        if action.operation == "delete" {
            try store.remove(event, span: .thisEvent, commit: true)
            return
        }
        guard ["create", "update"].contains(action.operation),
              let title = action.payload.fields.title,
              let startRaw = action.payload.fields.start, let endRaw = action.payload.fields.end,
              let start = CalendarWire.date(startRaw), let end = CalendarWire.date(endRaw), end >= start else {
            throw SyncError("The calendar change has invalid fields.")
        }
        event.title = title
        event.isAllDay = action.payload.fields.all_day ?? false
        event.startDate = start
        event.endDate = event.isAllDay ? Calendar.current.date(byAdding: .day, value: 1, to: end) : end
        event.notes = action.payload.fields.notes
        event.location = action.payload.fields.location
        try store.save(event, span: .thisEvent, commit: true)
    }

    struct SyncError: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}
