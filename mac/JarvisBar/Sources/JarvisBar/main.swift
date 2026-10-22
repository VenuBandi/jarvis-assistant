// Jarvis Bar (J1b): menu-bar icon + panel for the local Jarvis server, and the global hotkeys.
//   hold Right-Option+H for 3 s  → listening (panel opens, ready for input; voice arrives in J1c)
//   Right-Option+V               → Stop (ends the current Jarvis task)
// Hotkeys use macOS's standard hotkey service (RegisterEventHotKey): no Input Monitoring or Accessibility
// permission, and the key never reaches the app in front. That service cannot tell left from right Option, so the
// side is read from the modifier state and a left-Option press is ignored (it is still swallowed).
// Event log: <JarvisRoot>/data/jarvis_bar/events.log, hotkey timings only (never typed text, messages or the token).
import AppKit
import Carbon.HIToolbox
import Combine
import JarvisBarCore
import SwiftUI

let HOLD_SECONDS = 3.0
let JARVIS_URL = URL(string: "http://127.0.0.1:8770/")!

func uptime() -> Double { ProcessInfo.processInfo.systemUptime }

final class EventLog {
    private let url: URL?

    init(root: URL) {
        let dir = root.appendingPathComponent("data/jarvis_bar")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        url = dir.appendingPathComponent("events.log")
        if let url, !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
    }

    func write(_ event: String, _ fields: [String: String] = [:]) {
        guard let url, let h = try? FileHandle(forWritingTo: url) else { return }
        let stamp = ISO8601DateFormatter().string(from: Date())
        let extra = fields.keys.sorted().map { "\($0)=\(fields[$0]!)" }.joined(separator: " ")
        h.seekToEndOfFile()
        h.write("\(stamp) \(event) \(extra)\n".data(using: .utf8)!)
        try? h.close()
    }
}

// MARK: - Model

struct Row: Identifiable, Equatable {
    let id: Int
    let role: String
    let text: String
}

@MainActor
final class AppModel: ObservableObject {
    @Published var agentState = "offline"
    @Published var modelLabel = ""
    @Published var rows: [Row] = []
    @Published var pending: [Pending] = []
    @Published var input = ""
    @Published var busy = false
    @Published var arming = false
    @Published var listening = false
    @Published var lastError: String?
    @Published var focusToken = 0

    let client: JarvisClient?
    private var timer: Timer?
    private var lastState = ""

    init(client: JarvisClient?, tokenError: String?) {
        self.client = client
        lastError = tokenError
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.poll() }
        }
        Task { await poll(); await refreshConversation() }
    }

    var icon: String {
        if arming { return "ear" }
        if listening { return "ear.fill" }
        switch agentState {
        case "thinking": return "ellipsis.circle.fill"
        case "executing": return "gearshape.fill"
        case "idle": return "waveform.circle"
        default: return "exclamationmark.circle"
        }
    }

    var statusText: String {
        if arming { return "Keep holding…" }
        if listening { return "Listening" }
        switch agentState {
        case "idle": return "Ready"
        case "thinking": return "Thinking…"
        case "executing": return "Working…"
        default: return "Jarvis is not running"
        }
    }

    func poll() async {
        guard let client else { return }
        do {
            let s = try await client.state()
            agentState = s.agent_state
            modelLabel = s.active.label
            if pending != s.pending { pending = s.pending }
            if lastState != s.agent_state {
                if s.agent_state == "idle" { await refreshConversation() }
                lastState = s.agent_state
            }
            if lastError == "Jarvis is not running" { lastError = nil }
        } catch {
            agentState = "offline"
            lastState = "offline"
        }
    }

    func refreshConversation() async {
        guard let client, let msgs = try? await client.conversation() else { return }
        let shown = msgs.filter { $0.role == "user" || $0.role == "assistant" }.suffix(40)
        let new = shown.enumerated().map { Row(id: $0.offset, role: $0.element.role, text: $0.element.content) }
        if new != rows { rows = new }
    }

    func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let client, !text.isEmpty, !busy else { return }
        input = ""
        listening = false
        busy = true
        lastError = nil
        rows.append(Row(id: (rows.last?.id ?? -1) + 1, role: "user", text: text))
        Task {
            do {
                let r = try await client.chat(text)
                if let e = r.error, !e.isEmpty { lastError = e }
            } catch { lastError = "\(error)" }
            busy = false
            await refreshConversation()
            await poll()
        }
    }

    func decide(_ p: Pending, approve: Bool) {
        guard let client else { return }
        Task {
            do { _ = try await client.confirm(p.id, approve: approve) } catch { lastError = "\(error)" }
            await refreshConversation()
            await poll()
        }
    }

    func stop() {
        listening = false
        arming = false
        guard let client else { return }
        Task {
            do { try await client.stop() } catch { lastError = "\(error)" }
            await poll()
        }
    }
}

// MARK: - Panel

struct PanelView: View {
    @ObservedObject var model: AppModel
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: model.icon)
                Text(model.statusText).font(.headline)
                Spacer()
                Text(model.modelLabel).font(.caption).foregroundStyle(.secondary)
            }
            if model.listening {
                Text("Type your request (voice comes in step J1c).").font(.caption).foregroundStyle(.secondary)
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(model.rows) { r in
                            Text(r.text)
                                .textSelection(.enabled)
                                .padding(8)
                                .frame(maxWidth: .infinity, alignment: r.role == "user" ? .trailing : .leading)
                                .background(r.role == "user" ? Color.accentColor.opacity(0.15) : Color.secondary.opacity(0.1),
                                            in: RoundedRectangle(cornerRadius: 8))
                                .id(r.id)
                        }
                    }
                }
                .onChange(of: model.rows) { _, rows in
                    if let last = rows.last { proxy.scrollTo(last.id, anchor: .bottom) }
                }
                .onAppear { if let last = model.rows.last { proxy.scrollTo(last.id, anchor: .bottom) } }
            }
            .frame(height: 300)
            ForEach(model.pending) { p in
                VStack(alignment: .leading, spacing: 6) {
                    Text("Jarvis asks before it does this:").font(.caption).foregroundStyle(.secondary)
                    Text("\(p.tool): \(JSONValue.object(p.args).description)").font(.callout)
                    HStack {
                        Button("Yes, do it") { model.decide(p, approve: true) }
                        Button("No") { model.decide(p, approve: false) }
                    }
                }
                .padding(8)
                .background(Color.orange.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
            }
            HStack {
                TextField(model.busy ? "Jarvis is answering…" : "Ask Jarvis…", text: $model.input)
                    .textFieldStyle(.roundedBorder)
                    .focused($inputFocused)
                    .onSubmit { model.send() }
                    .disabled(model.busy || model.client == nil)
                Button("Send") { model.send() }
                    .disabled(model.busy || model.input.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            HStack {
                Button("Stop") { model.stop() }
                Button("Open full Jarvis") { NSWorkspace.shared.open(JARVIS_URL) }
                Spacer()
                Button("Quit Jarvis Bar") { NSApp.terminate(nil) }
            }
            .font(.caption)
            if let e = model.lastError {
                Text(e).font(.caption).foregroundStyle(.red)
            }
        }
        .padding(12)
        .frame(width: 400)
        .onChange(of: model.focusToken) { _, _ in inputFocused = true }
    }
}

// MARK: - Hotkeys

final class HotKeys {
    static let listenID: UInt32 = 1
    static let stopID: UInt32 = 2
    private var refs: [EventHotKeyRef] = []
    private let onEvent: (UInt32, Bool) -> Void

    init(onEvent: @escaping (UInt32, Bool) -> Void) {
        self.onEvent = onEvent
        var types = [EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed)),
                     EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyReleased))]
        InstallEventHandler(GetApplicationEventTarget(), { _, event, userData in
            guard let event, let userData else { return OSStatus(eventNotHandledErr) }
            var hk = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                              MemoryLayout<EventHotKeyID>.size, nil, &hk)
            let me = Unmanaged<HotKeys>.fromOpaque(userData).takeUnretainedValue()
            me.onEvent(hk.id, GetEventKind(event) == UInt32(kEventHotKeyPressed))
            return noErr
        }, 2, &types, Unmanaged.passUnretained(self).toOpaque(), nil)
    }

    /// Registers Option+<key>. Returns false if macOS refused (e.g. another app owns the combination).
    func register(id: UInt32, keyCode: Int) -> Bool {
        var ref: EventHotKeyRef?
        let hkID = EventHotKeyID(signature: OSType(0x4A52_5653), id: id)  // 'JRVS'
        let status = RegisterEventHotKey(UInt32(keyCode), UInt32(optionKey), hkID, GetApplicationEventTarget(), 0, &ref)
        if status == noErr, let ref { refs.append(ref) }
        return status == noErr
    }
}

// MARK: - App

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    let popover = NSPopover()
    var model: AppModel!
    var log: EventLog!
    var hotkeys: HotKeys!
    var hold = HoldDetector(hold: HOLD_SECONDS)
    var subs = Set<AnyCancellable>()

    func applicationDidFinishLaunching(_ note: Notification) {
        let rootPath = Bundle.main.object(forInfoDictionaryKey: "JarvisRoot") as? String
            ?? ProcessInfo.processInfo.environment["JARVIS_ROOT"] ?? ""
        let root = URL(fileURLWithPath: rootPath)
        log = EventLog(root: root)
        var client: JarvisClient?
        var tokenError: String?
        do { client = JarvisClient(base: JARVIS_URL, token: try JarvisClient.loadToken(root: root)) }
        catch { tokenError = "\(error)" }
        model = AppModel(client: client, tokenError: tokenError)

        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.action = #selector(togglePanel)
        item.button?.target = self
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: PanelView(model: model))
        model.objectWillChange.sink { [weak self] in
            DispatchQueue.main.async { self?.updateIcon() }
        }.store(in: &subs)
        updateIcon()

        hotkeys = HotKeys { [weak self] id, pressed in
            Task { @MainActor in self?.hotkey(id: id, pressed: pressed) }
        }
        let okListen = hotkeys.register(id: HotKeys.listenID, keyCode: kVK_ANSI_H)
        let okStop = hotkeys.register(id: HotKeys.stopID, keyCode: kVK_ANSI_V)
        log.write("start", ["listen_hotkey": okListen ? "ok" : "refused", "stop_hotkey": okStop ? "ok" : "refused",
                            "token": client == nil ? "missing" : "ok"])
        if !okListen || !okStop { model.lastError = "A hotkey could not be registered (see events.log)" }
    }

    func updateIcon() {
        let img = NSImage(systemSymbolName: model.icon, accessibilityDescription: model.statusText)
        img?.isTemplate = true
        item.button?.image = img
        item.button?.toolTip = "Jarvis: \(model.statusText)"
    }

    @objc func togglePanel() {
        if popover.isShown { popover.performClose(nil) } else { showPanel() }
    }

    func showPanel() {
        guard let button = item.button else { return }
        NSApp.activate(ignoringOtherApps: true)
        if !popover.isShown { popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY) }
        model.focusToken += 1
    }

    func rightOptionDown() -> (Bool, String) {
        let side = optionSide(flags: CGEventSource.flagsState(.hidSystemState).rawValue)
        return (side == .right || side == .both, "\(side)")
    }

    func hotkey(id: UInt32, pressed: Bool) {
        let now = uptime()
        if id == HotKeys.stopID {
            guard pressed else { return }
            let (right, side) = rightOptionDown()
            log.write(right ? "stop" : "stop_ignored", ["option": side])
            if right { model.stop() }
            return
        }
        guard id == HotKeys.listenID else { return }
        if !pressed {
            let startedAt = hold.pressedAt ?? now
            if hold.release(at: now) {
                model.arming = false
                log.write("listen_cancelled", ["held_ms": String(Int((now - startedAt) * 1000))])
            }
            return
        }
        let (right, side) = rightOptionDown()
        guard right else { log.write("listen_ignored", ["option": side]); return }
        guard hold.press(at: now) else { return }  // key repeat while held
        model.arming = true
        log.write("listen_pressed", ["option": side])
        DispatchQueue.main.asyncAfter(deadline: .now() + HOLD_SECONDS) { [weak self] in
            self?.holdElapsed()
        }
    }

    func holdElapsed() {
        let fired = uptime()
        guard hold.check(at: fired) else { return }
        let (right, side) = rightOptionDown()
        model.arming = false
        guard right else { log.write("listen_cancelled", ["reason": "option_released", "option": side]); return }
        model.listening = true
        showPanel()
        let shownMs = Int((uptime() - fired) * 1000)
        log.write("listening", ["panel_ms": String(shownMs)])
    }
}

MainActor.assumeIsolated {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.setActivationPolicy(.accessory)
    app.run()
}
