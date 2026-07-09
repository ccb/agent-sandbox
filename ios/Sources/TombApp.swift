import SwiftUI

/// The whole app: one full-screen terminal (design §1.2 — the Swift layer is
/// packaging, not development; the UI lives in app/dist's HTML/CSS/JS).
@main
struct TombApp: App {
    var body: some Scene {
        WindowGroup {
            TerminalView()
                // Respect the TOP safe area (the island/notch reads as
                // bezel over black); extend under the home indicator and
                // let the page manage the keyboard itself.
                .ignoresSafeArea(.container, edges: .bottom)
                .ignoresSafeArea(.keyboard)
                .background(Color.black)
                .preferredColorScheme(.dark)
                .persistentSystemOverlays(.hidden)
        }
    }
}
