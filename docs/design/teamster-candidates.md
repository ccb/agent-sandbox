# Teamster Candidates (rolled slate)

The caravan teamster was originally rolled per-seed on the Issue 1 spark
tables. CCB picked **Critch** (2026-07-10); the rest of the slate is kept
here for future NPCs. Seeds are the `teamster-{n}` strings fed to
`vaarn_chargen.generate(..., ancestry="newbeast")`.

| seed | name        | coat & beast          | mask       | oddity                    |
|-----:|-------------|-----------------------|------------|---------------------------|
|    0 | **Critch**  | Golden New-Hyena      | Cracked    | Won't wear clothes        |
|    3 | Typhon      | Lazulite New-Anemone  | Alluring   | Ritual scarring           |
|    7 | Vodalus     | Orange New-Tiger      | Sorrowful  | Missing limb              |
|   11 | Abandon     | Golden New-Mandrill   | Sage       | Communicates via puppet   |
|   19 | Anzah       | Tan New-Ferret        | Sage       | Gold teeth                |
|   23 | Wermouth    | Smoke New-Spider      | Joyful     | Religious paraphernalia   |
|   42 | Lurch       | Rose New-Scarab       | Patriarch  | Loves the animal he resembles |
|   77 | Plutarch    | Lazulite New-Python   | Mirrored   | Missing limb              |
|  101 | Wellbeloved | Black New-Baboon      | Judge      | Religious paraphernalia   |
|  137 | Dolm        | Indigo New-Coyote     | Blank      | Believes himself human    |

The random generator itself lives on as the `EXAMINE SELF` easter egg
(`vaarn_selves.py`, one hundred pregenerated selves, rolled once per game).
