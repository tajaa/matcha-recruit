import Foundation
import Observation

@MainActor
@Observable
final class ConsumerSettingsViewModel: LoadableVM {
    enum HandleCheckState: Equatable { case idle, checking, available, taken, invalid }
    var isLoading = false
    var error: String?
    var savedProfile = false
    var savedLocation = false
    var handleState: HandleCheckState = .idle

    func checkHandle(_ handle: String) async {
        let normalized = FriendHandle.normalize(handle)
        guard FriendHandle.validate(normalized) else { handleState = .invalid; return }
        handleState = .checking
        do {
            let result = try await FriendsService.shared.handleAvailable(normalized)
            handleState = result.available ? .available : .taken
        } catch { if !error.isCancellation { handleState = .idle; self.error = error.localizedDescription } }
    }

    func claimHandle(appState: AppState, handle: String) async {
        do {
            appState.account = try await FriendsService.shared.claimHandle(FriendHandle.normalize(handle))
            handleState = .idle
        } catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }

    func savePrivacy(appState: AppState, visibility: ProfileVisibility, discoverable: Bool, leaderboardOptIn: Bool) async {
        await withLoad {
            let updated = try await AuthService.shared.updateProfile(ProfileUpdate(
                display_name: nil, leaderboard_opt_in: leaderboardOptIn,
                profile_visibility: visibility.rawValue, discoverable: discoverable
            ))
            appState.account = updated
        }
    }

    func saveProfile(appState: AppState, displayName: String) async {
        savedProfile = false
        await withLoad {
            let updated = try await AuthService.shared.updateProfile(
                ProfileUpdate(display_name: displayName.isEmpty ? nil : displayName, leaderboard_opt_in: nil)
            )
            appState.account = updated
            savedProfile = true
        }
    }

    func saveLocation(appState: AppState, city: String, state: String, zipcode: String) async {
        savedLocation = false
        guard !city.isEmpty else { error = "City is required."; return }
        await withLoad {
            let updated = try await AuthService.shared.updateLocation(
                LocationUpdate(city: city, state: state.isEmpty ? nil : state, zipcode: zipcode.isEmpty ? nil : zipcode)
            )
            appState.account = updated
            savedLocation = true
        }
    }
}
