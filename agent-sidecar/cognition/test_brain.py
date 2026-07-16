"""Integration test for the stateful brain (SPEC §6), offline with a mock LLM. Proves the
behaviours that make Option B worth it: a per-agent memory stream that PERSISTS across beats,
retrieval that resurfaces a relevant past memory, the hard veto governing the chosen action, and
secret-goal filtering in the live decision prompt.

    python3 cognition/test_brain.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brain import BrainSession  # noqa: E402

_passed = 0
_failed = 0


def check(cond: bool, label: str) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


_last_prompt = {"text": ""}


def mock_llm(action: dict):
    def f(prompt: str) -> dict:
        _last_prompt["text"] = prompt
        return dict(action)
    return f


GOALS = [
    {"description": "Summon the descending god to escape mortality", "tier": "long", "done": False, "secret": True},
    {"description": "Work the rite at the cathedral crypt", "tier": "medium", "done": False, "secret": False},
]
PERC = {"role": "leader", "display_name": "Clerk Voss", "task": {"ritual": "summoning_descent"}}


def main() -> int:
    brain = BrainSession()

    # Beat 1 — ingest an observation; agent moves. Stream grows to 1.
    r1 = brain.decide({"session_id": "s", "agent_id": "voss", "turn": 1,
        "events": [{"text": "a Nighthawk watched me near the docks", "importance": 7}],
        "perception": PERC, "goals": GOALS, "world_state": {}},
        mock_llm({"verb": "move_to", "args": {"target": "cathedral_crypt"}}))
    check(r1["stream_size"] == 1, "beat1: memory stream grows to 1")
    check(r1["verdict"] == "approve" and r1["action"]["verb"] == "move_to", "beat1: move approved")
    check("Summon the descending god" not in _last_prompt["text"], "secret goal is hidden from the decision prompt")
    check("Work the rite at the cathedral crypt" in _last_prompt["text"], "non-secret goal shown in the prompt")

    # Beat 2 — off-site rite -> hard veto amends to idle. Stream grows to 2.
    r2 = brain.decide({"session_id": "s", "agent_id": "voss", "turn": 2,
        "events": [{"text": "the chapel bell tolled once", "importance": 2}],
        "perception": PERC, "goals": GOALS, "world_state": {"actor_at_rite_site": False}},
        mock_llm({"verb": "perform_ritual_step", "args": {"step": "x"}}))
    check(r2["stream_size"] == 2, "beat2: memory stream grows to 2")
    check(r2["verdict"] == "amend" and r2["action"]["verb"] == "idle", "beat2: off-site rite amended to idle")
    check("STANDING ON the rite site" not in _last_prompt["text"], "beat2: off-site -> no on-site cue (agent keeps moving)")

    # Beat 3 — on-site, altar fully stocked -> the rite is approved. Stream grows to 3.
    r3 = brain.decide({"session_id": "s", "agent_id": "voss", "turn": 3,
        "events": [{"text": "I reached the cathedral crypt", "importance": 5}],
        "perception": {**PERC, "rite_materials": {"ready": True, "outstanding": {}, "deposited": 3, "required": 3}},
        "goals": GOALS, "world_state": {"actor_at_rite_site": True}},
        mock_llm({"verb": "perform_ritual_step", "args": {"step": "x"}}))
    check(r3["verdict"] == "approve" and r3["action"]["verb"] == "perform_ritual_step", "beat3: on-site rite approved")
    check(r3["stream_size"] == 3, "beat3: memory stream grows to 3")
    check("task site" in _last_prompt["text"] and "every item" in _last_prompt["text"]
          and "has been laid" in _last_prompt["text"] and "perform_ritual_step" not in _last_prompt["text"],
          "beat3: the on-site stocked cue states the objective FACT only — no command, no suggested verb")

    # Beat 4 — a Nighthawk is nearby; retrieval resurfaces the beat-1 memory from 3 beats ago.
    r4 = brain.decide({"session_id": "s", "agent_id": "voss", "turn": 4, "events": [],
        "perception": {**PERC, "nearby": [{"id": "nighthawk_dunn"}]}, "goals": GOALS, "world_state": {}},
        mock_llm({"verb": "move_to", "args": {"target": "x"}}))
    check(any("Nighthawk watched me" in m for m in r4["retrieved"]),
          "beat4: retrieval resurfaces the persisted Nighthawk memory")
    check("Nighthawk watched me" in _last_prompt["text"], "beat4: the retrieved memory is in the prompt")

    # Beat 5 — secrecy is PURELY BEHAVIORAL: a "revealing" public action is NOT hard-vetoed. The
    # character keeps cover only because its persona drives it; governance never blocks the act.
    r5 = brain.decide({"session_id": "s", "agent_id": "voss", "turn": 5, "events": [],
        "perception": PERC, "goals": GOALS, "world_state": {"player_triggered": False}},
        mock_llm({"verb": "talk_to", "args": {}}))
    check(r5["verdict"] == "approve" and r5["action"]["verb"] == "talk_to",
          "beat5: secrecy is behavioral — a 'revealing' social act is never vetoed by governance")

    # Beat 6 — a different agent has an INDEPENDENT stream (no leakage from voss).
    r6 = brain.decide({"session_id": "s", "agent_id": "dalia", "turn": 6,
        "events": [{"text": "I moved the crates", "importance": 2}],
        "perception": {"faction": "cult"}, "goals": [], "world_state": {}},
        mock_llm({"verb": "idle", "args": {}}))
    check(r6["stream_size"] == 1, "beat6: a second agent has its own stream (1, not voss's 3)")

    # --- seq-based idempotent ingest: the long-game capping fix (#1/#4/#9) ---
    b2 = BrainSession()
    idle = mock_llm({"verb": "idle", "args": {}})

    def sreq(turn, events):
        return {"session_id": "sq", "agent_id": "k", "turn": turn, "events": events,
                "perception": {"faction": "cult"}, "goals": [], "world_state": {}}

    r = b2.decide(sreq(1, [{"text": "a", "seq": 0}, {"text": "b", "seq": 1}, {"text": "c", "seq": 2}]), idle)
    check(r["stream_size"] == 3, "seq: first window ingests all 3")
    r = b2.decide(sreq(2, [{"text": "a", "seq": 0}, {"text": "b", "seq": 1}, {"text": "c", "seq": 2}]), idle)
    check(r["stream_size"] == 3, "seq: re-sending the SAME window ingests nothing (idempotent)")
    r = b2.decide(sreq(3, [{"text": "b", "seq": 1}, {"text": "c", "seq": 2}, {"text": "d", "seq": 3}]), idle)
    check(r["stream_size"] == 4, "seq: a window slid past the cap still delivers the new entry (#1 fix)")
    r = b2.decide(sreq(4, [{"text": "x", "seq": 0}, {"text": "y", "seq": 1}]), idle)
    check(r["stream_size"] == 6, "seq: a backwards jump (save-load reload) re-ingests the restored window (#9 fix)")

    # --- reflection is edge-triggered, not latched forever (#5/#12) ---
    b3 = BrainSession()

    def rreq(turn, imp):
        return {"session_id": "rf", "agent_id": "k", "turn": turn,
                "events": [{"text": "big", "importance": imp, "seq": turn}],
                "perception": {"faction": "cult"}, "goals": [], "world_state": {}}

    check(b3.decide(rreq(1, 35.0), idle)["reflected"] is True, "reflection: trips True when importance crosses 30")
    check(b3.decide(rreq(2, 1.0), idle)["reflected"] is False, "reflection: resets after firing (one-beat pulse, not a latch)")

    # --- secrecy is purely behavioral: NO governance veto blocks a "revealing" act, with or without a
    #     witness present. The only governance left is physics/legality (the rite needs a site). ---
    b4 = BrainSession()

    def creq(turn, nearby, world=None):
        return {"session_id": "cs", "agent_id": "voss", "turn": turn, "events": [],
                "perception": {"task": {"ritual": "summoning_descent"}, "nearby": nearby},
                "goals": [], "world_state": dict({"player_triggered": False}, **(world or {}))}

    v_seen = b4.decide(creq(1, [{"id": "dunn"}]), mock_llm({"verb": "recruit", "args": {"agent": "x"}}))
    check(v_seen["verdict"] == "approve" and v_seen["action"]["verb"] == "recruit",
          "secrecy is behavioral: an open recruit with a stranger watching is NOT vetoed")
    v_rite = b4.decide(creq(2, [{"id": "dunn"}], {"actor_at_rite_site": True}),
                       mock_llm({"verb": "perform_ritual_step", "args": {"step": "s"}}))
    check(v_rite["verdict"] == "approve" and v_rite["action"]["verb"] == "perform_ritual_step",
          "the rite is approved at its site even with a witness present (climax stays reachable)")

    # --- persona prose reaches the prompt; the character KNOWS its own secrets (concealment is behavioral) ---
    bP = BrainSession()
    perc = {"description": "a tired dockhand with nothing on his mind but home",
            "voice": "friendly and weary", "knowledge": ["the day's dock gossip"],
            "secrets": ["this NPC secretly hates the harbor"]}
    bP.decide({"session_id": "p", "agent_id": "pell", "turn": 1, "events": [],
        "perception": perc, "goals": [], "world_state": {}}, idle)
    check("a tired dockhand with nothing on his mind but home" in _last_prompt["text"],
          "persona description reaches the decide prompt")
    check("friendly and weary" in _last_prompt["text"], "persona voice reaches the decide prompt")
    check("dock gossip" in _last_prompt["text"], "persona knowledge reaches the decide prompt")
    check("secretly hates the harbor" in _last_prompt["text"],
          "a character's own secrets ARE in its prompt — it knows them; whether it reveals them is behavioral")

    # --- converse(): say is free, the action is governed, the utterance is heard + remembered,
    #     secrecy holds, and a refusal is just a say ---
    bC = BrainSession()
    GOALS_CULT = [
        {"description": "Summon the descending god and escape mortality", "tier": "long", "secret": True},
        {"description": "Work the rite at the cathedral crypt", "tier": "medium", "secret": False},
    ]
    VERBS = {"adopt_goal": ["goal"], "drop_goal": ["goal"], "perform_ritual_step": ["step"], "idle": []}

    def conv(utter, reply, perc=None, world=None, revealed=False, sess="cv", agent="orin"):
        def f(prompt):
            _last_prompt["text"] = prompt
            return reply
        req = {"session_id": sess, "agent_id": agent, "turn": 1, "speaker": "player", "utterance": utter,
               "events": [], "perception": perc or {"faction": "cult", "display_name": "Orin"},
               "goals": GOALS_CULT, "world_state": world or {}, "revealed": revealed}
        return bC.converse(req, f, VERBS)

    r = conv("You don't have to go through with this.",
             {"say": "Quiet— Voss will hear you.",
              "action": {"verb": "adopt_goal", "args": {"goal": "Help the investigator stop the rite"}},
              "replies": [{"id": "press", "text": "Then help me."}, {"id": "leave", "text": "(Leave.)"}]})
    check(r["say"] == "Quiet— Voss will hear you.", "converse returns the NPC's spoken line verbatim")
    check(r["action"] and r["action"]["verb"] == "adopt_goal" and r["verdict"] == "approve",
          "an approved mechanical action is returned alongside the say")
    check(len(r["replies"]) >= 1, "suggested player replies are returned")
    check(r["stream_size"] >= 1, "the player's utterance + the reply grew the memory stream")
    check("You don't have to go through with this." in _last_prompt["text"],
          "the player's utterance is in the converse prompt")

    # Secrecy in conversation is PURELY BEHAVIORAL: the character KNOWS its own goals and secrets (they
    # ride in its own cognition, framed as "keep hidden"), and the LLM decides in character whether to let
    # any slip — nothing hard-gates them out of the prompt.
    conv("What are you really doing down here?",
         {"say": "Lighting the lamps, same as any night.", "action": None, "replies": []},
         perc={"display_name": "Orin", "secrets": ["doubts the summoning"]})
    check("doubts the summoning" in _last_prompt["text"],
          "converse: the character knows its own secret (it's in its prompt) — concealment is behavioral")

    # Speech is free; ONLY the action is governed. An off-site rite action is amended away, but the
    # spoken line survives verbatim.
    r2 = conv("Confess what you've done.",
              {"say": "We move the offerings through the harbor, if you must know.",
               "action": {"verb": "perform_ritual_step", "args": {"step": "x"}}, "replies": []},
              world={"actor_at_rite_site": False})
    check(r2["say"] == "We move the offerings through the harbor, if you must know.",
          "the say survives verbatim even when the action is governed")
    check(r2["verdict"] in ("amend", "veto") or (r2["action"] or {}).get("verb") == "idle",
          "an off-site rite action is amended/vetoed, not committed")

    # Refusal is just a say with no action.
    r3 = conv("Tell me everything.", {"say": "I've nothing to say to you.", "action": None, "replies": []})
    check(r3["say"] == "I've nothing to say to you." and r3["action"] is None,
          "a refusal is an in-character say with action=null")

    # --- the situation cue is gated on the agent HAVING A TASK (not a faction), and a perceived outsider
    #     is left as OBJECTIVE fact in Nearby — the cult-subjective "…not one of the faithful" line is gone.
    bO = BrainSession()

    def decide_prompt(perc, world=None):
        req = {"session_id": "ts", "agent_id": "x", "turn": 1, "events": [], "perception": perc,
               "goals": GOALS, "world_state": world or {}}
        bO.decide(req, mock_llm({"verb": "idle", "args": {}}))
        return _last_prompt["text"]

    _outsider = [{"id": "player", "role": "investigator", "faction": "player", "distance": 0.0}]
    _ready_mats = {"ready": True, "outstanding": {}, "deposited": 3, "required": 3}
    p_task = decide_prompt({"role": "leader", "display_name": "X", "nearby": _outsider,
                            "task": {"ritual": "summoning_descent"}, "rite_materials": _ready_mats},
                           {"actor_at_rite_site": True})
    check("SITUATION" in p_task, "an agent WITH a task gets the task-situation cue")
    check("faithful" not in p_task,
          "a perceived outsider is objective fact in Nearby — no engine-authored 'not one of the faithful'")

    p_no_task = decide_prompt({"role": "clerk", "display_name": "Y", "nearby": _outsider})
    check("SITUATION" not in p_no_task, "an agent with NO task gets no task-situation cue")

    p_noncult_task = decide_prompt({"faction": "civilian", "role": "courier", "display_name": "Z", "nearby": [],
                                    "task": {"ritual": "summoning_descent"}, "rite_materials": _ready_mats},
                                   {"actor_at_rite_site": True})
    check("SITUATION" in p_noncult_task, "the task-situation is gated on the task, not on a faction")

    # --- a peer's committed action rides in Nearby as an objective `doing` fact (concurrency
    #     phase 1: this is what lets same-task agents divide work instead of converging), and an
    #     actionless peer renders without one.
    p_doing = decide_prompt({"role": "clerk", "display_name": "W", "nearby": [
        {"id": "fishwife_dalia", "role": "fishwife", "distance": 20.0, "doing": "gather_item candle"},
        {"id": "lamplighter_orin", "role": "lamplighter", "distance": 25.0, "doing": ""},
    ]})
    check("fishwife_dalia (fishwife, doing gather_item candle)" in p_doing,
          "a peer's committed action renders as an objective doing fact in Nearby")
    check("lamplighter_orin (lamplighter)" in p_doing,
          "an actionless peer renders id (role) with no doing clause")

    # --- the Coordinator's allocation renders as a FACT in the task situation (no imperative verb
    #     before the item), and absent focus renders no allocation line.
    _out_mats = {"ready": False, "outstanding": {"candle": 1, "ritual_salt": 1}, "deposited": 1, "required": 3}
    p_focus = decide_prompt({"role": "clerk", "display_name": "V", "nearby": [],
                             "task": {"ritual": "summoning_descent", "site": "crypt_altar", "cache": "ritual_cache"},
                             "rite_materials": _out_mats,
                             "focus": {"subtask": "candle", "why": "unclaimed"}})
    check("the plan currently allocates to you: candle (unclaimed)" in p_focus,
          "the Coordinator's allocation renders as a plain fact")
    p_nofocus = decide_prompt({"role": "clerk", "display_name": "V", "nearby": [],
                               "task": {"ritual": "summoning_descent", "site": "crypt_altar", "cache": "ritual_cache"},
                               "rite_materials": _out_mats})
    check("allocates to you" not in p_nofocus, "no focus -> no allocation line")
    p_claimed = decide_prompt({"role": "clerk", "display_name": "V", "nearby": [],
                               "task": {"ritual": "summoning_descent", "site": "crypt_altar", "cache": "ritual_cache"},
                               "rite_materials": _out_mats, "focus": {"all_claimed": True}})
    check("already in a plan-member's hands" in p_claimed,
          "all-claimed renders the everything-is-carried fact")

    # --- combat M1: the agent's own condition renders as a FACT (banded word + exact self numbers),
    #     and a peer's hp_band rides in Nearby as a band only — never an exact number for peers.
    p_hurt = decide_prompt({"role": "clerk", "display_name": "K", "hp": 61.0, "max_hp": 100.0,
                            "downed": False, "nearby": []})
    check("Your condition: hurt (61/100)." in p_hurt,
          "self condition renders banded word + exact self hp as a fact")
    p_healthy = decide_prompt({"role": "clerk", "display_name": "K", "hp": 100.0, "max_hp": 100.0,
                               "downed": False, "nearby": []})
    check("Your condition: healthy (100/100)." in p_healthy, "full hp renders the healthy band")
    p_crit = decide_prompt({"role": "clerk", "display_name": "K", "hp": 10.0, "max_hp": 100.0,
                            "downed": False, "nearby": []})
    check("Your condition: critical (10/100)." in p_crit, "hp in (0,1/3] renders critical")
    p_down = decide_prompt({"role": "clerk", "display_name": "K", "hp": 0.0, "max_hp": 100.0,
                            "downed": True, "nearby": []})
    check("Your condition: downed (0/100)." in p_down, "a downed agent's condition says downed")
    p_nohp = decide_prompt({"role": "clerk", "display_name": "K", "nearby": []})
    check("Your condition" not in p_nohp, "no hp in perception -> no condition line (legacy shape)")
    p_band = decide_prompt({"role": "clerk", "display_name": "K", "nearby": [
        {"id": "clerk_voss", "role": "clerk", "hp_band": "hurt", "doing": "move_to x"},
        {"id": "old_neil", "role": "alchemist", "hp_band": "downed"},
    ]})
    check("clerk_voss (clerk, hurt, doing move_to x)" in p_band,
          "a peer's hp_band renders between role and doing in the Nearby roster")
    check("old_neil (alchemist, downed)" in p_band, "a doing-less peer still renders its band")
    check("61" not in p_band.split("Nearby:")[-1].split("\n")[0],
          "peers render a band only — no exact hp number rides the roster")

    # --- combat M4: the COMBAT SITUATION block is facts only — the fight, who struck you, your own
    #     published intent, which visible neighbors are also fighting, and (own-body knowledge) the
    #     arts of the worn form. NEVER a command; the neutrality principle is load-bearing.
    KIT = [
        {"id": "cleaver_swipe", "class": "strike",
         "description": "a heavy cleaver swing at whoever stands within arm's reach"},
        {"id": "assume_form", "class": "transform",
         "description": "let the worn shape fall away and become the monstrous thing beneath it"},
    ]
    p_fight = decide_prompt({
        "role": "butcher", "display_name": "Kell", "hp": 48.0, "max_hp": 100.0, "downed": False,
        "in_combat": True, "last_attacker": "player",
        "combat_intent": {"mode": "engage", "target": "player", "style": "aggressive",
                          "set_at_beat": 5, "set_beats_ago": 2},
        "kit": KIT,
        "nearby": [
            {"id": "player", "role": "investigator", "hp_band": "healthy", "doing": "attack kell",
             "in_combat": True},
            {"id": "old_neil", "role": "alchemist", "hp_band": "healthy"},
        ]})
    check("COMBAT: you are in a fight." in p_fight, "combat M4: the in-fight fact renders")
    check("Your condition: hurt (48/100)." in p_fight, "combat M4: own condition still renders beside it")
    check("Engaged by: player." in p_fight, "combat M4: the last-to-strike fact renders as engaged-by")
    check("Your standing intent: engage player (aggressive), set 2 beats ago." in p_fight,
          "combat M4: the OWN standing intent renders in full detail with its age")
    fight_line = [l for l in p_fight.split("\n") if "Also in the fight nearby" in l]
    check(len(fight_line) == 1 and "player (investigator, healthy, doing attack kell)" in fight_line[0],
          "combat M4: a visibly fighting neighbor renders with hp_band + doing")
    check(len(fight_line) == 1 and "old_neil" not in fight_line[0],
          "combat M4: a non-fighting bystander stays out of the combatant roster (Nearby only)")
    check("Your arts: cleaver_swipe (strike; a heavy cleaver swing at whoever stands within arm's reach)"
          in p_fight, "combat M4: own-kit facts render id + class + the authored description")
    check("assume_form (transform; let the worn shape fall away and become the monstrous thing beneath it)"
          in p_fight,
          "combat M4: assume_form is neutral-but-known — the authored description IS the text source")
    low = p_fight.lower()
    check("you should" not in low and "you must" not in low and "must attack" not in low,
          "combat M4: the block is facts only — no imperative 'you should/must attack' anywhere")

    # Intent-less fight: the absence of a standing intent is itself a fact, not a nudge.
    p_nointent = decide_prompt({"role": "butcher", "display_name": "Kell", "hp": 90.0, "max_hp": 100.0,
                                "downed": False, "in_combat": True, "nearby": []})
    check("You hold no standing combat intent." in p_nointent,
          "combat M4: no published intent renders as the plain fact")
    check("Engaged by" not in p_nointent, "combat M4: no known attacker -> no engaged-by line")
    # A protect intent renders its ward; a disengage renders its exit.
    p_protect = decide_prompt({"role": "guard", "display_name": "G", "in_combat": True, "nearby": [],
                               "combat_intent": {"mode": "protect", "agent": "old_neil", "set_beats_ago": 1}})
    check("Your standing intent: protect old_neil, set 1 beat ago." in p_protect,
          "combat M4: a protect intent renders its ward (singular beat)")
    p_diseng = decide_prompt({"role": "clerk", "display_name": "C", "in_combat": True, "nearby": [],
                              "combat_intent": {"mode": "disengage", "via": "crypt_door", "set_beats_ago": 0}})
    check("Your standing intent: disengage (via crypt_door), set 0 beats ago." in p_diseng,
          "combat M4: a disengage intent renders its via")

    # Out of combat: no combat block, no arts roster — the peaceful prompt is untouched.
    p_peace = decide_prompt({"role": "butcher", "display_name": "Kell", "hp": 48.0, "max_hp": 100.0,
                             "downed": False, "nearby": [], "kit": KIT})
    check("COMBAT:" not in p_peace and "Your arts:" not in p_peace,
          "combat M4: no in_combat flag -> no combat block, no arts (kit is combat-beat knowledge)")

    # --- combat M4: verb-menu guidance is neutral descriptions; cast_ability never reaches the menu.
    bV = BrainSession()

    def decide_prompt_verbs(perc, verbs):
        req = {"session_id": "vm", "agent_id": "x", "turn": 1, "events": [], "perception": perc,
               "goals": [], "world_state": {}}
        bV.decide(req, mock_llm({"verb": "idle", "args": {}}), verbs)
        return _last_prompt["text"]

    verbs_full = {"engage": ["target"], "disengage": [], "protect": ["agent"],
                  "cast_ability": ["ability"], "move_to": ["target"], "idle": []}
    p_menu = decide_prompt_verbs({"role": "butcher", "display_name": "K", "in_combat": True, "nearby": []},
                                 verbs_full)
    check("cast_ability" not in p_menu,
          "combat M4: cast_ability is excluded from the /decide menu (GM-directive verb only)")
    check("- engage: requires ['target']" in p_menu, "combat M4: engage still rides the menu normally")
    check("engage: commit to fighting a target; style is one of aggressive|cautious|defensive|desperate"
          in p_menu, "combat M4: engage guidance is a neutral description with the style vocabulary")
    check("disengage: break off from the fight" in p_menu, "combat M4: disengage guidance renders")
    check("protect: shield another agent" in p_menu, "combat M4: protect guidance renders")
    low_menu = p_menu.lower()
    check("you should" not in low_menu and "you must" not in low_menu,
          "combat M4: verb guidance carries no imperative")
    # The exclusion also holds for a bare list menu, and guidance only names verbs actually offered.
    p_list = decide_prompt_verbs({"role": "clerk", "display_name": "K", "nearby": []},
                                 ["move_to", "cast_ability", "engage", "idle"])
    check("cast_ability" not in p_list, "combat M4: list-form menus exclude cast_ability too")
    check("engage: commit to fighting a target" in p_list
          and "disengage: break off" not in p_list,
          "combat M4: guidance covers only the combat verbs present in this menu")
    p_nocombat_menu = decide_prompt_verbs({"role": "clerk", "display_name": "K", "nearby": []},
                                          {"move_to": ["target"], "idle": []})
    check("commit to fighting" not in p_nocombat_menu,
          "combat M4: a menu without combat verbs renders no combat guidance")

    # --- P1 (lab pull-in): one-shot just_* transition markers render for exactly this beat ------
    bJ = BrainSession()

    def decide_prompt_just(perc):
        req = {"session_id": "just", "agent_id": "j", "turn": 1, "events": [], "perception": perc,
               "goals": [], "world_state": {}}
        bJ.decide(req, mock_llm({"verb": "idle", "args": {}}))
        return _last_prompt["text"]

    p_just = decide_prompt_just({"role": "clerk", "display_name": "J", "nearby": [],
                                 "just_happened": ["just_entered_combat", "just_changed_room"]})
    check("Just now: just entered combat; just changed room." in p_just,
          "P1: just_* markers render as one plain 'Just now' fact line")
    p_nojust = decide_prompt_just({"role": "clerk", "display_name": "J", "nearby": []})
    check("Just now:" not in p_nojust, "P1: no markers -> no 'Just now' line (one-shot semantics)")

    # --- P4 (lab pull-in): ONE bounded repair round on invalid LLM output, outcome-stamped -----
    # Ports the lab's is_error tool_result pattern: an invalid reply's validation error is fed
    # back to the model exactly ONCE; still invalid -> the existing idle fallback. The result is
    # stamped valid | repaired | failed for the usage/cost record.
    bR = BrainSession()
    verbs_schema = {"move_to": ["target"], "idle": []}

    def scripted_llm(replies: list, calls: list):
        """Scripted mock client: returns replies in order (repeats the last); records prompts."""
        def f(prompt: str) -> dict:
            calls.append(prompt)
            return dict(replies[min(len(calls) - 1, len(replies) - 1)])
        return f

    def decide_r(turn: int, llm) -> dict:
        return bR.decide({"session_id": "rep", "agent_id": "r", "turn": turn, "events": [],
                          "perception": {"role": "x"}, "goals": [], "world_state": {}},
                         llm, verbs_schema)

    calls1: list = []
    rv1 = decide_r(1, scripted_llm([{"verb": "move_to", "args": {"target": "site"}}], calls1))
    check(rv1.get("outcome") == "valid" and len(calls1) == 1,
          "P4: a well-formed reply passes with outcome=valid and exactly ONE call")

    calls2: list = []
    rv2 = decide_r(2, scripted_llm([{"verb": "move_to", "args": {}},              # missing arg
                                    {"verb": "move_to", "args": {"target": "site"}}], calls2))
    check(rv2.get("outcome") == "repaired" and rv2["action"]["verb"] == "move_to"
          and rv2["action"]["args"].get("target") == "site",
          "P4: malformed-then-valid recovers with outcome=repaired")
    check(len(calls2) == 2 and "INVALID" in calls2[1] and "missing arg" in calls2[1],
          "P4: the repair prompt feeds the exact validation error back to the model")

    calls3: list = []
    rv3 = decide_r(3, scripted_llm([{"verb": "fly", "args": {}},
                                    {"verb": "teleport", "args": {}}], calls3))
    check(rv3.get("outcome") == "failed" and rv3["action"]["verb"] == "idle",
          "P4: malformed-twice falls back to idle with outcome=failed")
    check(len(calls3) == 2, "P4: exactly one repair round EVER (2 calls total, never a third)")

    # A non-dict reply (parse garbage) enters the same single repair round.
    calls4: list = []

    def garbage_then_valid(prompt: str) -> dict:
        calls4.append(prompt)
        return {} if len(calls4) == 1 else {"verb": "idle", "args": {}}

    rv4 = decide_r(4, garbage_then_valid)
    check(rv4.get("outcome") == "repaired" and rv4["action"]["verb"] == "idle" and len(calls4) == 2,
          "P4: an unparseable reply gets the same single repair round")

    print(f"\n=== {_passed} passed, {_failed} failed ===")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
