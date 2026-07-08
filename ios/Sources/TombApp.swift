import SwiftUI

/// The whole app: one full-screen terminal (design §1.2 — the Swift layer is
/// packaging, not development; the UI lives in app/dist's HTML/CSS/JS).
@main
struct TombApp: App {
    var body: some Scene {
        WindowGroup {
            TerminalView()
                .ignoresSafeArea()
                .background(Color.black)
                .preferredColorScheme(.dark)
                .persistentSystemOverlays(.hidden)
        }
    }
}
