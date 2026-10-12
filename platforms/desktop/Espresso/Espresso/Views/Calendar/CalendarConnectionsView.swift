import SwiftUI
import AppKit

/// One place for the person's consent, provider connections and sync status.
struct CalendarConnectionsView: View {
    @Environment(AppState.self) private var appState
    @State private var sync = AppleCalendarSync.shared
    @State private var abilities: AssistantAbilities?
    @State private var consent: AssistantAbility?
    @State private var selected = Set<String>()
    @State private var destination = ""
    @State private var status: AppleCalendarStatus?
    @State private var busy = false
    @State private var error: String?
    @State private var waitingForGoogle = false

    private var calendarAbility: AssistantAbility? { abilities?.abilities.first { $0.key == "calendar" } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if appState.assistantEnabled {
                    GroupBox("Espresso calendar access") {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(calendarAbility?.enabled == true ? "Espresso can work with your calendars." : "Allow Espresso to read and organize your calendars from your private chat.")
                                .font(.system(size: 12))
                            if let ability = calendarAbility {
                                Button(ability.enabled ? "Turn off Espresso access" : "Allow Espresso access") {
                                    if ability.enabled { Task { await disable(ability) } }
                                    else { consent = ability }
                                }.disabled(busy)
                                if ability.enabled, ability.commitMode == "dry_run" {
                                    Text("Calendar writes are explicitly paused on this server.").font(.caption).foregroundColor(.orange)
                                }
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
                    }
                }
                GroupBox("Google Calendar") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Connect once to see your Google Calendar here. When calendar access is on, Espresso can create, change and delete events there.")
                            .font(.system(size: 12))
                        Button(waitingForGoogle ? "Waiting for Google…" : "Connect or reconnect Google Calendar") {
                            Task { await connectGoogle() }
                        }.disabled(busy || waitingForGoogle)
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
                }
                GroupBox("Apple Calendar / calendars on this Mac") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Choose which calendars to share with Espresso and a destination for new events. This includes iCloud and Google accounts added to Apple Calendar. Selected event titles, times, locations and notes sync to your Espresso account.")
                            .font(.system(size: 12))
                        Text("Sync runs every 30 seconds while Espresso is open on this Mac, from 30 days ago through the next 11 months (up to 500 events). Espresso changes personal events; existing invitations stay read-only.")
                            .font(.caption).foregroundColor(.secondary)
                        Button("Choose calendars…") { Task { await chooseCalendars() } }.disabled(busy)
                        if !sync.calendars.isEmpty {
                            ForEach(sync.calendars) { calendar in
                                Toggle(calendar.title, isOn: Binding(
                                    get: { selected.contains(calendar.id) },
                                    set: { if $0 { selected.insert(calendar.id) } else { selected.remove(calendar.id) } }))
                                    .font(.system(size: 12))
                            }
                            Picker("New events go to", selection: $destination) {
                                Text("Choose a calendar").tag("")
                                ForEach(sync.calendars.filter { selected.contains($0.id) && $0.editable }) {
                                    Text($0.title).tag($0.id)
                                }
                            }
                            Button("Connect and sync selected calendars") { Task { await saveSelection() } }
                                .disabled(busy || selected.isEmpty || !selected.contains(destination))
                        }
                        if let config = sync.configuration {
                            Text("Connected: " + config.calendars.map(\.title).joined(separator: ", "))
                                .font(.caption).foregroundColor(.secondary)
                            HStack {
                                Button("Sync now") { Task { await sync.sync(); await refresh() } }.disabled(busy)
                                Button("Disconnect", role: .destructive) { Task { await disconnect() } }.disabled(busy)
                            }
                        } else if status?.connected == true {
                            Text("Another Mac is connected. Connect this Mac to replace it.").font(.caption)
                            Button("Disconnect connected Mac", role: .destructive) { Task { await disconnect() } }.disabled(busy)
                        }
                        if let date = sync.lastSync {
                            Text("Last synced \(date.formatted(date: .abbreviated, time: .standard))").font(.caption).foregroundColor(.secondary)
                        }
                        if let message = sync.error { Text(message).font(.caption).foregroundColor(.orange) }
                        ForEach(status?.actions ?? []) { action in
                            Text("\(action.operation.capitalized): \(action.status)" + (action.error.map { " — " + $0 } ?? ""))
                                .font(.caption).foregroundColor(action.status == "done" ? .secondary : .orange)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
                }
                if let error { Text(error).font(.caption).foregroundColor(.orange) }
                if busy { ProgressView().controlSize(.small) }
            }.padding(16)
        }
        .task(id: appState.currentUser?.id) {
            abilities = nil; status = nil; error = nil
            selected = []; destination = ""
            if appState.currentUser != nil { await refresh() }
        }
        .task(id: appState.assistantEnabled) { if appState.currentUser != nil { await refresh() } }
        .onChange(of: appState.foregroundTick) { _, _ in waitingForGoogle = false; Task { await refresh() } }
        .onReceive(NotificationCenter.default.publisher(for: AppleCalendarSync.didSync)) { _ in Task { await refresh() } }
        .sheet(item: $consent) { ability in
            AssistantConsentSheet(ability: ability) { _ in
                do {
                    try await MatchaWorkService.shared.enableAssistantAbility(ability.key, consentVersion: ability.disclosure?.version, contact: nil)
                    consent = nil
                    await refresh()
                    return nil
                } catch { return error.localizedDescription }
            }.environment(appState)
        }
    }

    private func refresh() async {
        let owner = appState.currentUser?.id
        guard owner != nil else { return }
        do {
            let loaded = appState.assistantEnabled ? try await MatchaWorkService.shared.assistantAbilities() : nil
            let state = try await sync.status()
            guard owner == appState.currentUser?.id else { return }
            abilities = loaded
            status = state
            error = nil
        } catch { if owner == appState.currentUser?.id { self.error = error.localizedDescription } }
    }

    private func disable(_ ability: AssistantAbility) async {
        busy = true
        defer { busy = false }
        do { try await MatchaWorkService.shared.disableAssistantAbility(ability.key); await refresh() }
        catch { self.error = error.localizedDescription }
    }

    private func connectGoogle() async {
        busy = true
        defer { busy = false }
        do {
            let raw = try await MatchaWorkService.shared.connectGoogle(forAbility: "calendar")
            if let url = URL(string: raw), url.scheme == "https" {
                waitingForGoogle = true
                NSWorkspace.shared.open(url)
            }
        } catch { self.error = error.localizedDescription }
    }

    private func chooseCalendars() async {
        busy = true
        defer { busy = false }
        do {
            try await sync.requestAccess()
            selected = Set(sync.configuration?.calendars.map(\.id) ?? [])
            destination = sync.configuration?.destination ?? ""
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func saveSelection() async {
        busy = true
        defer { busy = false }
        do { try await sync.connect(selected: selected, destination: destination); error = nil; await refresh() }
        catch { self.error = error.localizedDescription }
    }

    private func disconnect() async {
        busy = true
        defer { busy = false }
        do { try await sync.disconnect(connectionID: status?.connection_id); error = nil; await refresh() }
        catch { self.error = error.localizedDescription }
    }
}
