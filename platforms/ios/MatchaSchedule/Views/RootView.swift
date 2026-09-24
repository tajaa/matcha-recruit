import SwiftUI

private enum Palette {
    static let background = Color(red: 0.98, green: 0.96, blue: 0.92)
    static let ink = Color(red: 0.20, green: 0.16, blue: 0.13)
}

struct RootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            switch appState.phase {
            case .restoring:
                ProgressView("Opening your schedule…")
            case .signedOut:
                LoginView()
            case .ready(let profile):
                MainTabs(profile: profile)
            case .needsWeb:
                VStack(spacing: 12) {
                    StatusView(title: "Use Matcha on the web", message: "This app is for employee accounts with a work profile.", symbol: "person.crop.circle.badge.questionmark")
                    Link("Open hey-matcha.com", destination: URL(string: "https://hey-matcha.com")!)
                }
            case .disabled:
                StatusView(title: "Scheduling isn’t enabled", message: "Ask your manager to enable employee scheduling for your company.", symbol: "calendar.badge.exclamationmark")
            case .retry(let message):
                StatusView(title: "Couldn’t connect", message: message, symbol: "wifi.exclamationmark", action: { Task { await appState.restore() } })
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .foregroundStyle(Palette.ink)
        .background(Palette.background)
    }
}

private struct StatusView: View {
    let title: String
    let message: String
    let symbol: String
    var action: (() -> Void)? = nil

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: symbol).font(.system(size: 46, weight: .thin))
            Text(title).font(.title2.bold())
            Text(message).multilineTextAlignment(.center).foregroundStyle(.secondary)
            if let action { Button("Try again", action: action).buttonStyle(.borderedProminent) }
        }
        .padding(32)
    }
}

private struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Spacer()
            Image(systemName: "calendar").font(.system(size: 42, weight: .thin))
            Text("Your week, at a glance.")
                .font(.system(size: 36, weight: .semibold, design: .serif))
            Text("Sign in with your employee account to see your shifts.")
                .foregroundStyle(.secondary)
            TextField("Email", text: $email)
                .textContentType(.username).keyboardType(.emailAddress)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)
            SecureField("Password", text: $password)
                .textContentType(.password).textFieldStyle(.roundedBorder)
            if let error { Text(error).foregroundStyle(.red).font(.footnote) }
            Button {
                busy = true
                error = nil
                Task {
                    defer { busy = false }
                    do { try await appState.signIn(email: email, password: password) }
                    catch { self.error = error.localizedDescription }
                }
            } label: {
                if busy { ProgressView().frame(maxWidth: .infinity) }
                else { Text("Sign in").frame(maxWidth: .infinity) }
            }
            .buttonStyle(.borderedProminent)
            .disabled(busy || email.isEmpty || password.isEmpty)
            Spacer()
        }
        .padding(28)
    }
}

private struct MainTabs: View {
    @Environment(AppState.self) private var appState
    let profile: EmployeeProfile

    var body: some View {
        @Bindable var state = appState
        TabView(selection: $state.selectedTab) {
            NavigationStack { ScheduleView(profile: profile) }
                .tabItem { Label("Schedule", systemImage: "calendar") }.tag(0)
            NavigationStack { PlaceholderView(title: "Requests", message: "Shift requests and time off will appear here.") }
                .tabItem { Label("Requests", systemImage: "arrow.left.arrow.right") }.tag(1)
            NavigationStack { PlaceholderView(title: "Messages", message: "Team messages will appear here.") }
                .tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right") }.tag(2)
            NavigationStack { MeView(profile: profile) }
                .tabItem { Label("Me", systemImage: "person.crop.circle") }.tag(3)
        }
    }
}

private struct PlaceholderView: View {
    let title: String
    let message: String

    var body: some View {
        ContentUnavailableView(title, systemImage: "clock", description: Text(message))
            .navigationTitle(title)
    }
}

private struct MeView: View {
    @Environment(AppState.self) private var appState
    let profile: EmployeeProfile
    @State private var error: String?
    @State private var signingOut = false

    var body: some View {
        List {
            Section {
                LabeledContent("Name", value: profile.displayName)
                LabeledContent("Company", value: profile.company_name)
            }
            Section {
                Button("Sign out") {
                    signingOut = true
                    Task {
                        defer { signingOut = false }
                        do { try await appState.signOut() }
                        catch { self.error = error.localizedDescription }
                    }
                }
                .disabled(signingOut)
            }
            if let error { Text(error).foregroundStyle(.red) }
        }
        .navigationTitle("Me")
    }
}
