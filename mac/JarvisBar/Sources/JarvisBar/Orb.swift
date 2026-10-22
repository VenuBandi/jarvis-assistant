// The Jarvis circle: a HUD-style orb in the middle of the screen while Jarvis is called, listening, thinking or
// speaking. It never takes the keyboard from the app in front (non-activating panel) and lets clicks through.
import AppKit
import JarvisBarCore
import SwiftUI

let ORB_SIZE: CGFloat = 440
let CYAN = Color(red: 0.37, green: 0.83, blue: 0.96)

final class OrbWindow {
    private let panel: NSPanel
    private(set) var shown = false

    @MainActor
    init(model: AppModel) {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: ORB_SIZE, height: ORB_SIZE),
                        styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: true)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .statusBar
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel.contentView = NSHostingView(rootView: OrbView(model: model))
        panel.alphaValue = 0
    }

    func show() {
        guard !shown else { return }
        shown = true
        let screen = NSScreen.screens.first { NSMouseInRect(NSEvent.mouseLocation, $0.frame, false) } ?? NSScreen.main
        if let f = screen?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: f.midX - ORB_SIZE / 2, y: f.midY - ORB_SIZE / 2))
        }
        panel.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.25
            panel.animator().alphaValue = 1
        }
    }

    func hide() {
        guard shown else { return }
        shown = false
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.45
            panel.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            if self?.shown == false { self?.panel.orderOut(nil) }
        })
    }
}

struct OrbView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        TimelineView(.animation) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate
            ZStack {
                // dark glass disc so the rings read on any background
                Circle().fill(RadialGradient(colors: [Color(red: 0.02, green: 0.06, blue: 0.09).opacity(0.94), Color.black.opacity(0.86)],
                                             center: .center, startRadius: 10, endRadius: ORB_SIZE / 2))
                    .frame(width: 400, height: 400)
                Circle().stroke(CYAN.opacity(0.25), lineWidth: 1).frame(width: 396, height: 396)
                // outer dashed ring, slow
                Circle().trim(from: 0, to: 0.82)
                    .stroke(CYAN.opacity(0.55), style: StrokeStyle(lineWidth: 2, dash: [2, 7]))
                    .frame(width: 370, height: 370)
                    .rotationEffect(.degrees(t * 8))
                // segmented arcs, counter-rotating
                ForEach(0..<4) { i in
                    Circle().trim(from: Double(i) * 0.25, to: Double(i) * 0.25 + 0.14)
                        .stroke(CYAN.opacity(0.8), style: StrokeStyle(lineWidth: 5, lineCap: .butt))
                        .frame(width: 330, height: 330)
                        .rotationEffect(.degrees(-t * (model.agentBusy ? 60 : 14)))
                }
                // hold progress (fills over the 3-s hold)
                if model.arming {
                    Circle().trim(from: 0, to: model.holdProgress(now: uptime()))
                        .stroke(CYAN, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                        .frame(width: 300, height: 300)
                        .rotationEffect(.degrees(-90))
                        .shadow(color: CYAN, radius: 8)
                }
                Circle().stroke(CYAN.opacity(0.35), lineWidth: 1).frame(width: 286, height: 286)
                WaveRing(levels: bars(t), radius: 112)
                    .stroke(CYAN.opacity(0.9), lineWidth: 2)
                    .frame(width: 280, height: 280)
                    .shadow(color: CYAN.opacity(0.8), radius: 6)
                Circle().stroke(CYAN.opacity(0.5), lineWidth: 1.5).frame(width: 196, height: 196)
                VStack(spacing: 8) {
                    Text(model.orbTitle)
                        .font(.system(size: 13, weight: .semibold, design: .monospaced))
                        .tracking(4)
                        .foregroundStyle(CYAN)
                    if model.arming {
                        Text("\(Int(model.holdProgress(now: uptime()) * 100))%")
                            .font(.system(size: 40, weight: .light, design: .rounded))
                            .foregroundStyle(.white)
                    } else {
                        Text("J.A.R.V.I.S.")
                            .font(.system(size: 22, weight: .light, design: .rounded))
                            .tracking(3)
                            .foregroundStyle(.white.opacity(0.9))
                    }
                    Text(model.orbSubtitle)
                        .font(.system(size: 10, weight: .regular, design: .monospaced))
                        .tracking(2)
                        .foregroundStyle(CYAN.opacity(0.7))
                }
                .shadow(color: CYAN.opacity(0.6), radius: 6)
            }
            .frame(width: ORB_SIZE, height: ORB_SIZE)
        }
    }

    /// 96 bar lengths (0…1): the microphone level while listening, a lively pattern while speaking,
    /// a slow travelling wave while thinking, nearly still otherwise.
    func bars(_ t: Double) -> [Double] {
        (0..<96).map { i in
            let a = Double(i) / 96 * 2 * .pi
            if model.listening {
                let lvl = Double(min(1, model.micLevel * 9))
                return 0.08 + lvl * (0.55 + 0.45 * sin(a * 7 + t * 9)) * (0.6 + 0.4 * sin(a * 3 - t * 5))
            }
            if model.speaking {
                return 0.15 + 0.35 * abs(sin(a * 5 + t * 7)) * (0.5 + 0.5 * sin(a * 11 - t * 13))
            }
            if model.agentBusy {
                return 0.08 + 0.18 * max(0, sin(a * 2 - t * 4))
            }
            return 0.05 + 0.02 * sin(a * 6 + t)
        }
    }
}

/// Radial bars around a circle; `levels` 0…1 sets each bar's length outward from `radius`.
struct WaveRing: Shape {
    var levels: [Double]
    var radius: CGFloat

    func path(in rect: CGRect) -> Path {
        var p = Path()
        let c = CGPoint(x: rect.midX, y: rect.midY)
        let maxLen = rect.width / 2 - radius
        for (i, l) in levels.enumerated() {
            let a = Double(i) / Double(levels.count) * 2 * .pi - .pi / 2
            let r2 = radius + CGFloat(l) * maxLen
            p.move(to: CGPoint(x: c.x + radius * CGFloat(cos(a)), y: c.y + radius * CGFloat(sin(a))))
            p.addLine(to: CGPoint(x: c.x + r2 * CGFloat(cos(a)), y: c.y + r2 * CGFloat(sin(a))))
        }
        return p
    }
}
