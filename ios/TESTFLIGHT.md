# Getting the Tomb onto TestFlight — CCB's checklist

Everything the repo can do is done (M1–M4: the web terminal, saves, the
dressing, the simulator-verified app). What remains needs **your Apple
identity** — none of it can be scripted from here.

## 0. One-time prerequisites (~15 min + Apple's processing)

- [ ] **Apple Developer Program** membership on your Apple ID ($99/yr) —
      [developer.apple.com/programs](https://developer.apple.com/programs/).
      (An existing Penn/SEAS team also works if you have the App Manager role.)
- [ ] In Xcode: **Settings → Accounts → add your Apple ID**, confirm the team
      appears.

## 1. Open the project

```bash
uv run python app/build_dist.py --with-pyodide   # the offline bundle the app ships
cd ios && xcodegen generate                       # brew install xcodegen (already installed)
open TombOfNassakAnRah.xcodeproj
```

## 2. Signing (~2 min)

- [ ] Select the **Tomb** target → **Signing & Capabilities** → check
      *Automatically manage signing* → pick your **Team**.
- [ ] If Xcode complains about the bundle id `edu.upenn.ccb.tomb`, change the
      prefix to anything your team owns (also update `bundleIdPrefix` +
      `PRODUCT_BUNDLE_IDENTIFIER` in `ios/project.yml` so regeneration keeps it).

## 3. App icon (~10 min)

- [ ] TestFlight requires a 1024×1024 icon. Add an **App Icon** asset
      (Assets.xcassets → AppIcon) — a blue-glow glyph on black fits the
      phosphor. *(Ask Claude for generated candidates, or drop in any PNG.)*

## 4. Prove it on your phone first (~5 min)

- [ ] Plug in your iPhone, select it as the run destination, hit **Run**
      (first run: trust the developer cert under Settings → General → VPN &
      Device Management).
- [ ] Play a few turns, **force-quit, relaunch** — confirm the
      *RESTORE AUTO* banner appears. (This re-verifies save persistence on
      real hardware; it's confirmed in the simulator. If it ever fails on
      device, tell Claude — the fallback is a small UserDefaults bridge.)
- [ ] Feel the haptics: take a wound (the jackals oblige).

## 5. Archive → TestFlight (~15 min + Apple review ~1 day)

- [ ] In App Store Connect: **Apps → + → New App** (platform iOS, the bundle
      id from step 2, name "Tomb of Nassak An-Rah" or similar).
- [ ] In Xcode: destination **Any iOS Device (arm64)** → **Product → Archive**
      → Organizer opens → **Distribute App → TestFlight & App Store → Upload**.
- [ ] In App Store Connect → TestFlight: fill the export-compliance question
      (the answer is **no encryption** — `ITSAppUsesNonExemptEncryption` is
      already false in the Info.plist) and the beta description.
- [ ] Add testers: **Internal** (instant, up to 100 App Store Connect users)
      or an **external group** with a public link for the summer students —
      external builds get a light Apple review (~1 day; text-only offline
      game, low risk).

## 6. Each new build after engine/game changes

```bash
uv run python app/build_dist.py --with-pyodide
cd ios && xcodegen generate      # only needed if project.yml changed
# Xcode: bump build number → Product → Archive → Distribute
```

## Also worth doing (not blocking)

- [ ] **Deploy the web version** — `app/dist/` is static files; GitHub Pages
      or any static host gives the students a zero-install URL. (Build
      *without* `--with-pyodide` for the CDN runtime, or with it for a fully
      self-hosted ~25 MB deploy.)
- [ ] A short **How to Play** note in the TestFlight beta description
      (typing + chips, SAVE/RESTORE, the gear for settings).
