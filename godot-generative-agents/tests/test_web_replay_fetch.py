"""#938: the web replay fetch must not double-decompress.

On web exports Godot's HTTPRequest rides the browser's fetch layer, which
negotiates Content-Encoding itself and hands over an already-decompressed
body. With ``accept_gzip`` left on (the default), Godot sees the response's
gzip header and runs its own StreamPeerGZIP pass over that plaintext -- it
fails, feeds garbage to ``JSON.parse_string``, and the #928 one-button flow
ships a silent blank campus behind any compressing host (Vercel included).

Pinned on the source the way test_export_boot_scene.py pins the boot scene:
a revert should fail loudly here, not in a browser three days before demo.
"""

from pathlib import Path

VIEWER = Path(__file__).resolve().parents[1] / "godot" / "scripts" / "viewer.gd"


def _web_loader_body() -> str:
    text = VIEWER.read_text(encoding="utf-8")
    start = text.index("func _load_replay_web")
    end = text.index("\nfunc ", start + 1)
    return text[start:end]


def test_web_replay_fetch_disables_godot_side_gunzip():
    body = _web_loader_body()
    assert "accept_gzip = false" in body, (
        "#938: _load_replay_web must set accept_gzip = false -- the browser "
        "already decompressed the body; Godot gunzipping it again blanks the "
        "web viewer behind any gzip-serving host."
    )
    # Setting the flag after the request went out would be too late.
    assert body.index("accept_gzip = false") < body.index(".request(")
