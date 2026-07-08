# The iOS shell (M4)

*Tomb of Nassak An-Rah* as an iPhone app: a WKWebView serving the bundled
`app/dist/` (wheel + vendored Pyodide + terminal) through a custom `tomb://`
scheme, plus the haptics/share bridge. Three Swift files, by design
([docs/design/ios-tomb-app.md](../docs/design/ios-tomb-app.md) §1.2). Fully
offline — no network entitlements, no accounts, no tracking.

## Build & run (simulator — no Apple account needed)

```bash
uv run python app/build_dist.py --with-pyodide   # the offline web bundle
cd ios && xcodegen generate                       # brew install xcodegen
xcodebuild -project TombOfNassakAnRah.xcodeproj -scheme Tomb \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
xcrun simctl boot "iPhone 17"
xcrun simctl install booted build/Build/Products/Debug-iphonesimulator/Tomb.app
xcrun simctl launch booted edu.upenn.ccb.tomb
```

Or: `xcodegen generate`, open the project in Xcode, hit Run.

## The pieces

- `project.yml` — xcodegen spec; the `.xcodeproj` is generated, not committed.
  `../app/dist` rides into the bundle as a folder reference, so an engine
  change is: rebuild dist, rebuild app.
- `Sources/TombApp.swift` — the SwiftUI entry: one full-screen terminal.
- `Sources/TerminalView.swift` — the WKWebView + the two JS bridge handlers
  (`haptic`: damage = impact, death = error buzz; `share`: transcript sheet).
- `Sources/DistSchemeHandler.swift` — serves `dist/` at `tomb://app/...` with
  correct MIME types (`.wasm` streaming-eligible). No local HTTP server.

## Device / TestFlight

Running on a real iPhone or distributing via TestFlight needs CCB's Apple
Developer account: open the project in Xcode, set the team under Signing &
Capabilities, and archive. Before the App Store: an icon set and screenshots
(design §5 v2). Known open question from the design doc: `localStorage`
persistence under custom URL schemes across app relaunches — if saves don't
survive a relaunch on device, the fallback is bridging the save store to
`UserDefaults` via a third message handler.
