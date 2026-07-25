"""The repo-root .env loader (backend/env.py).

Pins the two contracts the backend CLIs stand on: the file's KEY=VALUE lines
reach ``os.environ``, and a variable that is already exported is NEVER
overridden by the file (one-off ``FOO=bar cmd`` runs and CI settings keep
working). Fully offline.
"""

import os

from backend.env import load_dotenv


def test_loads_pairs_and_never_overrides_the_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "DOTENV_TEST_NEW=plain\n"
        'export DOTENV_TEST_EXPORTED="quoted value"\n'
        "DOTENV_TEST_SINGLE='single'\n"
        "DOTENV_TEST_EXISTING=from-file\n"
        "not a key value line\n"
        "=no-key\n"
    )
    for name in ("DOTENV_TEST_NEW", "DOTENV_TEST_EXPORTED", "DOTENV_TEST_SINGLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DOTENV_TEST_EXISTING", "from-env")

    assert load_dotenv(env_file) is True
    try:
        assert os.environ["DOTENV_TEST_NEW"] == "plain"
        assert os.environ["DOTENV_TEST_EXPORTED"] == "quoted value"
        assert os.environ["DOTENV_TEST_SINGLE"] == "single"
        # The exported environment wins over the file, always.
        assert os.environ["DOTENV_TEST_EXISTING"] == "from-env"
    finally:  # the loader writes os.environ directly; clean up after ourselves
        for name in ("DOTENV_TEST_NEW", "DOTENV_TEST_EXPORTED", "DOTENV_TEST_SINGLE"):
            os.environ.pop(name, None)


def test_missing_file_is_fine(tmp_path):
    assert load_dotenv(tmp_path / "no-such.env") is False


def test_default_path_is_the_repo_root():
    # The default resolves relative to this source tree, not the cwd -- so the
    # loader finds the checkout's own .env no matter where the CLI is launched
    # from. Regression for #776: assert what _REPO_ROOT *means* -- the checkout
    # root, where pyproject.toml and the .env.example template live, i.e. where
    # the docs tell you to put your .env. (The old self-referential check
    # re-derived _REPO_ROOT from env.py's location, so it kept passing when
    # #399 moved backend/ a level deeper and the default silently became
    # godot-generative-agents/.env.)
    from backend import env

    assert (env._REPO_ROOT / "pyproject.toml").is_file()
    assert (env._REPO_ROOT / ".env.example").is_file()
