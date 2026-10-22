// Hotkey logic without AppKit, so it can be unit-tested.

/// Hold-to-trigger: press, keep holding for `hold` seconds, fire once. Repeated presses while held (key repeat) are
/// ignored; a release before `hold` cancels. Times are monotonic seconds (ProcessInfo.systemUptime).
public struct HoldDetector {
    public let hold: Double
    public private(set) var pressedAt: Double?
    public private(set) var fired = false

    public init(hold: Double) { self.hold = hold }

    /// True when a new hold starts (the caller schedules `check` at pressedAt + hold).
    public mutating func press(at t: Double) -> Bool {
        if pressedAt != nil { return false }
        pressedAt = t
        fired = false
        return true
    }

    /// True exactly once, when the key has been held long enough.
    public mutating func check(at t: Double) -> Bool {
        guard let p = pressedAt, !fired, t - p >= hold - 0.01 else { return false }
        fired = true
        return true
    }

    /// True if the hold was cancelled (released before it fired).
    @discardableResult public mutating func release(at t: Double) -> Bool {
        defer { pressedAt = nil }
        guard pressedAt != nil else { return false }
        return !fired
    }
}

public enum OptionSide: Equatable { case none, left, right, both }

/// Which Option key is down, from the device-dependent bits of CGEventFlags (IOKit NX_DEVICELALTKEYMASK 0x20,
/// NX_DEVICERALTKEYMASK 0x40).
public func optionSide(flags raw: UInt64) -> OptionSide {
    switch (raw & 0x20 != 0, raw & 0x40 != 0) {
    case (true, true): return .both
    case (true, false): return .left
    case (false, true): return .right
    default: return .none
    }
}
