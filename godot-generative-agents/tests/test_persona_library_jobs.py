"""Job-expansion pass (2026-08-19 spike -> approved plan): giving more of the
persona library a real job, following the existing wage_rate + is_work
pattern (drives.accrue_wage) that 10 personas already used (Rosa, Walt,
Debra, Gus, Leon, Marcus, Ellis, Tanaka, Ravi, Nadia).

Each of the 8 new job holders below gets it via tagging ONE of their own
existing schedule stops `is_work: true` -- a pure metadata flag that never
touches a stop's place/steps/activity, so it can't desync any authored
meeting's timing. Fatima Al-Rashid was deliberately left out: her persona
text says she "volunteers" as an orientation buddy, and tagging that as paid
work would contradict her own authored backstory.

Run with: uv run pytest godot-generative-agents/tests/test_persona_library_jobs.py -v
"""

from backend.build_world import library_personas
from backend.penn.penn_world import WORLD_DATA, build_penn_world

NEW_JOB_PERSONAS = {
    "Diego Torres": "Meyerson Hall",
    "Elena Vasquez": "Van Pelt — Circulation Desk",
    "Theo Lindqvist": "Van Pelt — Circulation Desk",
    "Tessa Byrne": "Houston Hall — Reading Room",
    "Wesley Okafor": "Van Pelt — Digital Scholarship Exchange",
    "Desmond Clarke": "Houston Hall — Billiard Room",
    "Priya Nair": "Van Pelt — Digital Scholarship Exchange",
    "Maya Chen": "Van Pelt — Study Booths",
}

PRE_EXISTING_JOB_HOLDERS = {
    "Rosa Delgado",
    "Walt Higgins",
    "Debra Hollis",
    "Gus Kowalski",
    "Leon Brooks",
    "Marcus Webb",
    "Professor Ellis",
    "Professor Tanaka",
    "Ravi Deshmukh",
    "Nadia Osei",
}


def _all_persona_ids():
    return [e["id"] for e in library_personas(WORLD_DATA)]


def test_full_library_still_loads_cleanly():
    """A cast of every library persona builds without error -- catches any
    YAML syntax mistake or bad place-name typo introduced by the job edits."""
    ids = _all_persona_ids()
    pw = build_penn_world(cast=ids)
    assert len(pw.personas) == len(ids)


def test_new_job_personas_have_wage_rate_and_the_expected_is_work_stop():
    pw = build_penn_world(cast=_all_persona_ids())
    by_name = {p["name"]: p for p in pw.personas}
    for name, expected_place in NEW_JOB_PERSONAS.items():
        persona = by_name[name]
        assert persona.get("wage_rate"), f"{name} has no wage_rate"
        work_stops = [s for s in persona["schedule"] if s["is_work"]]
        assert work_stops, f"{name} has no is_work stop"
        assert any(s["place"] == expected_place for s in work_stops), (
            f"{name}'s is_work stop isn't at {expected_place}: "
            f"{[s['place'] for s in work_stops]}"
        )


def test_fatima_stays_job_free_as_an_explicit_volunteer():
    pw = build_penn_world(cast=_all_persona_ids())
    fatima = next(p for p in pw.personas if p["name"] == "Fatima Al-Rashid")
    assert not fatima.get("wage_rate")


def test_pre_existing_job_holders_are_unaffected():
    pw = build_penn_world(cast=_all_persona_ids())
    by_name = {p["name"]: p for p in pw.personas}
    for name in PRE_EXISTING_JOB_HOLDERS:
        assert by_name[name].get("wage_rate"), f"{name} lost its wage_rate"


def test_job_holder_count_after_the_expansion():
    pw = build_penn_world(cast=_all_persona_ids())
    holders = {p["name"] for p in pw.personas if p.get("wage_rate")}
    assert holders == PRE_EXISTING_JOB_HOLDERS | set(NEW_JOB_PERSONAS)
