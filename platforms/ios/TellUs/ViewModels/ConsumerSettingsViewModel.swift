import Foundation
import Observation

@MainActor
@Observable
final class ConsumerSettingsViewModel: LoadableVM {
    var isLoading = false
    var error: String?
    var savedProfile = false
    var savedLocation = false

    func saveProfile(appState: AppState, displayName: String, leaderboardOptIn: Bool) async {
        savedProfile = false
        await withLoad {
            let updated = try await AuthService.shared.updateProfile(
                ProfileUpdate(display_name: displayName.isEmpty ? nil : displayName, leaderboard_opt_in: leaderboardOptIn)
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
