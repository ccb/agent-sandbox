import SwiftUI

/// The whole app: one full-screen terminal (design §1.2 — the Swift layer is
/// packaging, not development; the UI lives in app/dist's HTML/CSS/JS).
@main
struct TombApp: App {
    var body: some Scene {
        WindowGroup {
            TerminalView()
                // Respect the TOP safe area (the island/notch reads as
                // bezel over black); extend under the home indicator. The
                // KEYBOARD region is NOT ignored: WKWebView doesn't honor
                // interactive-widget=resizes-content, so SwiftUI shrinking
                // the webview is what keeps the input and chips above the
                // keyboard.
                .ignoresSafeArea(.container, edges: .bottom)
                .background(Color.black)
                .preferredColorScheme(.dark)
                .persistentSystemOverlays(.hidden)
        }
    }
}
