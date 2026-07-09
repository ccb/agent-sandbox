import SwiftUI
import WebKit

/// Remove the system `^ v (done)` accessory strip above the keyboard: it is
/// redundant with the terminal's own chips and costs 44pt of tomb (CCB). The
/// first responder inside a WKWebView is the private WKContentView, so we
/// swap in a runtime subclass whose inputAccessoryView is nil -- the standard
/// technique for accessory-free web views.
private func removeInputAccessory(from webView: WKWebView) {
    guard
        let target = webView.scrollView.subviews.first(where: {
            String(describing: type(of: $0)).hasPrefix("WKContent")
        })
    else { return }
    let className = "NoAccessory_\(String(describing: type(of: target)))"
    var cls: AnyClass? = NSClassFromString(className)
    if cls == nil, let targetClass = object_getClass(target) {
        cls = objc_allocateClassPair(targetClass, className, 0)
        if let cls = cls {
            let selector = #selector(getter: UIResponder.inputAccessoryView)
            let block: @convention(block) (AnyObject) -> UIView? = { _ in nil }
            class_addMethod(
                cls, selector, imp_implementationWithBlock(block), "@@:"
            )
            objc_registerClassPair(cls)
        }
    }
    if let cls = cls { object_setClass(target, cls) }
}

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
        removeInputAccessory(from: webView)
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
