import CoreLocation
import Observation

/// One-shot location for Discover's "nearby" fill. Deliberately
/// `requestLocation()`, never `startUpdatingLocation()` — a discovery screen
/// needs one fix per open, not a continuous stream that drains battery.
@MainActor
@Observable
final class LocationService: NSObject, CLLocationManagerDelegate {
    static let shared = LocationService()

    private(set) var coordinate: CLLocationCoordinate2D?
    private(set) var authorizationStatus: CLAuthorizationStatus

    private let manager = CLLocationManager()
    private var pendingContinuations: [CheckedContinuation<CLLocationCoordinate2D?, Never>] = []
    private var timeoutTask: Task<Void, Never>?

    private override init() {
        authorizationStatus = CLLocationManager().authorizationStatus
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    /// nil when denied/restricted, on failure, or after an 8s timeout —
    /// callers fall back to the account's city. Never throws. Concurrent
    /// callers all resume off the same fix.
    func requestOnce() async -> CLLocationCoordinate2D? {
        switch manager.authorizationStatus {
        case .denied, .restricted:
            return nil
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        default:
            break
        }
        return await withCheckedContinuation { continuation in
            pendingContinuations.append(continuation)
            startTimeoutIfNeeded()
            if manager.authorizationStatus == .authorizedWhenInUse
                || manager.authorizationStatus == .authorizedAlways {
                manager.requestLocation()
            }
        }
    }

    private func startTimeoutIfNeeded() {
        guard timeoutTask == nil else { return }
        timeoutTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(8))
            guard !Task.isCancelled else { return }
            self?.resumeAll(with: nil)
        }
    }

    private func resumeAll(with coordinate: CLLocationCoordinate2D?) {
        timeoutTask?.cancel()
        timeoutTask = nil
        let pending = pendingContinuations
        pendingContinuations = []
        for continuation in pending {
            continuation.resume(returning: coordinate)
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor [weak self] in
            self?.authorizationStatus = status
            guard status == .authorizedWhenInUse || status == .authorizedAlways else {
                if status == .denied || status == .restricted {
                    self?.resumeAll(with: nil)
                }
                return
            }
            guard let self, !self.pendingContinuations.isEmpty else { return }
            self.manager.requestLocation()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let coord = locations.last?.coordinate
        Task { @MainActor [weak self] in
            self?.coordinate = coord
            self?.resumeAll(with: coord)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor [weak self] in
            self?.resumeAll(with: nil)
        }
    }
}
