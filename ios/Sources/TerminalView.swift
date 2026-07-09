import SwiftUI
import WebKit

/// The WKWebView that *is* the app: loads tomb://app/index.html through the
/// bundled-dist scheme handler and services the two JS bridge messages
/// (haptics on damage/death, the share sheet for transcripts).
struct TerminalView: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(DistSchemeHandler(), forURLScheme: "tomb")
        config.userContentController.add(context.coordinator, name: "haptic")
        config.userContentController.add(context.coordinator, name: "share")

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = .black
        webView.scrollView.backgroundColor = .black
        // The page owns its scroll region (#output); the outer view must not
        // bounce or fight the keyboard.
        webView.scrollView.isScrollEnabled = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        // Focusing the input makes WebKit scroll the page programmatically
        // even with user scrolling off, shoving the status bar off-screen --
        // the delegate pins the offset home.
        webView.scrollView.delegate = context.coordinator
        if #available(iOS 16.4, *) {
            webView.isInspectable = true  // Safari > Develop, for debugging
        }
        webView.load(URLRequest(url: URL(string: "tomb://app/index.html")!))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, WKScriptMessageHandler, UIScrollViewDelegate {
        func scrollViewDidScroll(_ scrollView: UIScrollView) {
            if scrollView.contentOffset != .zero {
                scrollView.contentOffset = .zero
            }
        }


        private let wound = UIImpactFeedbackGenerator(style: .medium)
        private let death = UINotificationFeedbackGenerator()

        func userContentController(
            _ controller: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            switch message.name {
            case "haptic":
                if (message.body as? String) == "death" {
                    death.notificationOccurred(.error)
                } else {
                    wound.impactOccurred()
                }
            case "share":
                guard let text = message.body as? String else { return }
                let activity = UIActivityViewController(
                    activityItems: [text], applicationActivities: nil
                )
                UIApplication.shared.connectedScenes
                    .compactMap { $0 as? UIWindowScene }
                    .first?.keyWindow?.rootViewController?
                    .present(activity, animated: true)
            default:
                break
            }
        }
    }
}
