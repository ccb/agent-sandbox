# Playdate port -- M0 spike

Build:  `pdc -sdkpath ~/Developer/PlaydateSDK Source TombOfNassakAnRah.pdx`
Run:    open the .pdx with the Playdate Simulator, or sideload via play.date/account.

Controls (the Composer, docs/design/playdate.md section 3):
- crank .... scroll the active word lane (6 detents/rev)
- left/right lane: EXITS / VERBS / NOUNS
- up/down .. page the transcript
- A ........ speak the highlighted word (an exit alone just goes)
- B ........ unsay the last word

M0 exit criterion: compose GO NORTH on hardware.
