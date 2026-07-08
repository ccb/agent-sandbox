import WebKit

/// Serves the bundled `dist/` folder at tomb://app/... — no local HTTP
/// server, no network (design §1.2). fetch() from the page arrives here too,
/// so the manifest, the wheel, and the vendored Pyodide runtime all resolve
/// against the app bundle.
final class DistSchemeHandler: NSObject, WKURLSchemeHandler {
    private static let mimeTypes: [String: String] = [
        "html": "text/html",
        "js": "text/javascript",
        "mjs": "text/javascript",
        "css": "text/css",
        "json": "application/json",
        "wasm": "application/wasm",  // streaming-compile eligible
        "zip": "application/zip",
        "whl": "application/octet-stream",
        "png": "image/png",
    ]

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return }
        var relative = url.path.drop(while: { $0 == "/" })
        if relative.isEmpty { relative = "index.html" }

        let fileURL = Bundle.main.resourceURL!
            .appendingPathComponent("dist")
            .appendingPathComponent(String(relative))

        guard let data = try? Data(contentsOf: fileURL) else {
            task.didFailWithError(URLError(.fileDoesNotExist))
            return
        }
        let ext = fileURL.pathExtension.lowercased()
        let mime = Self.mimeTypes[ext] ?? "application/octet-stream"
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: [
                "Content-Type": mime,
                "Content-Length": String(data.count),
                "Cache-Control": "no-cache",
            ]
        )!
        task.didReceive(response)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {
        // Single-shot bundle reads: nothing in flight to cancel.
    }
}
