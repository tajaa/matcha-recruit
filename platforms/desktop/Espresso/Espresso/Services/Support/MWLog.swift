import Foundation

/// Debug-only diagnostic logging.
///
/// `print` ships in Release and evaluates its argument eagerly, so the
/// per-frame WebSocket and per-event realtime logs were doing string
/// interpolation on the main thread in production builds — on every inbound
/// frame, before the handlers had even decided the event was relevant.
///
/// The `@autoclosure` is the point: in Release the closure is never called, so
/// the interpolation itself is compiled away, not merely discarded.
@inline(__always)
func mwLog(_ message: @autoclosure () -> String) {
    #if DEBUG
    print(message())
    #endif
}
