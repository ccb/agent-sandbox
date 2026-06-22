import generate_tingen_anim as g


def test_cast_has_four_characters():
    assert set(g.ANIM_CAST) == {
        "player_detective", "nighthawk_captain", "priest", "bieber_monster"}


def test_sheet_counts_per_character():
    # design spec §6: 12 / 8 / 8 / 8 action sheets.
    def n(ch):
        return sum(len(v) for v in g.SHEETS[ch].values())
    assert n("player_detective") == 12
    assert n("nighthawk_captain") == 8
    assert n("priest") == 8
    assert n("bieber_monster") == 8


def test_total_jobs_all_stages():
    jobs = list(g.iter_anim_jobs("all", None))
    design = [j for j in jobs if j[0] == "design"]
    action = [j for j in jobs if j[0] == "action"]
    assert len(design) == 4
    assert len(action) == 36
    assert len(jobs) == 40


def test_stage_filter():
    assert len(list(g.iter_anim_jobs("design", None))) == 4
    assert len(list(g.iter_anim_jobs("action", None))) == 36


def test_character_filter():
    jobs = list(g.iter_anim_jobs("all", "player_detective"))
    assert all(j[1] == "player_detective" for j in jobs)
    assert len(jobs) == 13  # 1 design + 12 action


def test_design_prompt_content():
    p = g.build_design_prompt("player_detective")
    assert "model sheet" in p
    assert "palette" in p
    assert "back view" in p
    assert "NO sepia" in p
    assert "Klein Moretti" in p


def test_action_prompt_has_eight_and_facing_and_keyframes():
    p = g.build_action_prompt("player_detective", "revolver_fire", "side")
    assert "8 equal cells" in p
    assert "right-facing side profile" in p
    assert "muzzle flash" in p          # from the revolver_fire keyframes
    assert "NO sepia" in p


def test_action_prompt_loop_note_only_for_loops():
    looped = g.build_action_prompt("priest", "idle", "down")
    oneshot = g.build_action_prompt("priest", "examine", "down")
    assert "loops seamlessly" in looped
    assert "loops seamlessly" not in oneshot


def test_action_prompt_facing_up_is_from_behind():
    p = g.build_action_prompt("nighthawk_captain", "walk", "up")
    assert "from behind" in p


from pathlib import Path


def test_output_paths():
    d = g.output_path("design", "priest", None, None)
    a = g.output_path("action", "priest", "walk", "side")
    assert d == g.ANIM_DIR / "priest" / "_design.png"
    assert a == g.ANIM_DIR / "priest" / "walk_side.png"


def test_design_ref_is_hero_sprite():
    r = g.resolve_ref("design", "bieber_monster")
    assert r == g.OUT_DIR / "enemies/bieber_monster.png"


def test_action_ref_is_design_sheet():
    r = g.resolve_ref("action", "player_detective")
    assert r == g.ANIM_DIR / "player_detective" / "_design.png"


def test_build_prompt_dispatches_by_kind():
    assert "model sheet" in g.build_prompt("design", "priest", None, None)
    assert "8 equal cells" in g.build_prompt("action", "priest", "idle", "down")
