# Tingen SFX staging manifest (2026-07-12)

All files 44.1kHz WAV, peak-normalized (~-4.4 dBFS; ambience -6.9). License: **CC0**.
Sources: Kenney.nl packs (impact-sounds, rpg-audio, ui-audio, interface-sounds, music-jingles — License.txt in each zip, scratchpad/audio_dl/) + procedural synthesis (numpy, deterministic seeds — CC0 by construction).
Vetting: durations/loudness checked programmatically; key sounds verified by SPECTROGRAM inspection (shot = broadband crack + low tail; slam = heavy low-mid impact; whoosh = swept band noise; ambience = smooth LF noise, comb-null-free, 58s seamless loop via 2s tail-head crossfade). Nobody has LISTENED to these — first human playtest should sanity-check levels/taste; every sound routes through one mixer/map so swaps are one-line.

## Event mapping (EventBus vocabulary -> file)
| game event | file | source |
|---|---|---|
| player shot fired | shot_revolver.wav | SYNTH (noise crack + low thud + impactMetal_heavy_001 layer) |
| dry fire / no ammo | shot_dry.wav | rpg-audio metalClick |
| hit lands (flesh) | hit_flesh_1.wav, hit_flesh_2.wav (alternate) | impactPunch_medium_000/002 |
| heavy hit / poise break | hit_hard.wav | impactPunch_heavy_001 |
| agent downed / body fall | body_fall.wav | impactSoft_heavy_002 |
| mask-drop transform slam | slam_mask_drop.wav | SYNTH (impactPlate_heavy_002 + impactWood_heavy_003, -20% pitch) |
| mask-drop sting (layer over slam) | sting_mask_drop.wav | jingles_HIT14 (darkest by spectral centroid 1954Hz) |
| meter threshold crossed | sting_threshold.wav | jingles_HIT11 |
| dash | dash_whoosh.wav | SYNTH (one-pole swept noise 1800->400Hz) |
| item ground pickup | pickup_item.wav | rpg-audio handleSmallLeather |
| ammo/metal pickup | pickup_metal.wav | rpg-audio metalLatch |
| door / room transition | door_open.wav, door_close.wav | rpg-audio doorOpen_1/doorClose_1 |
| footsteps (pool of 3, cycle) | step_1.wav step_2.wav step_3.wav | rpg-audio footstep00/01/05 |
| UI click | ui_click.wav | interface-sounds click_002 |
| toast / hint surfaced | ui_toast.wav (toast), hint_chime.wav (hint) | interface confirmation_001, ui-audio switch2 |
| refusal cue (no_spirit etc) | ui_error.wav | interface-sounds error_004 |
| city/night ambience loop | ambience_night.wav (58s seamless) | SYNTH (one-pole brown noise + LFO + air hiss) |

## Wiring notes for the audio milestone
- New AudioManager autoload: subscribes EventBus (same _is_live() headless gate as CombatFeedback — headless emits nothing, sims stay byte-identical), one AudioStreamPlayer pool, data-driven event->file map in data/audio_map.json (NOT hardcoded), Settings master-volume bus finally does something.
- Place files at tingen/assets/audio/. Alternate-pool for repeated events (hits/steps) to avoid machine-gun repetition.
- Deferred gaps: combat music sting/loop, per-surface footsteps, Hermit cast sounds (star_brand needs its own shimmer — synth candidate), ritual-night bell.
