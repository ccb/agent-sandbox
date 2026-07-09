"""The Issue 1 character generator (vaarn_chargen)."""

import random

import pytest

from text_adventure_games import vaarn_chargen as vc


def test_ability_rolls_follow_the_lowest_die_rule():
    rng = random.Random(1)
    for _ in range(200):
        bonus, defence = vc.roll_ability(rng)
        assert 1 <= bonus <= 6
        assert defence == 10 + bonus


def test_generate_is_deterministic_under_a_seed():
    a = vc.generate(random.Random(9), ancestry="newbeast")
    b = vc.generate(random.Random(9), ancestry="newbeast")
    assert (a.name, a.sparks, a.hp, a.abilities) == (
        b.name,
        b.sparks,
        b.hp,
        b.abilities,
    )


@pytest.mark.parametrize("ancestry", vc.ANCESTRIES)
def test_every_ancestry_generates_complete(ancestry):
    pc = vc.generate(random.Random(4), ancestry=ancestry)
    assert pc.ancestry == ancestry
    assert pc.name
    assert set(pc.abilities) == set(vc.ABILITIES)
    assert 1 <= pc.hp <= 8
    assert pc.slots == pc.abilities["Constitution"][1]  # slots = CON defence
    assert pc.special  # every ancestry ships its zine special
    assert pc.epithet.startswith(pc.name)
    assert vc.sheet(pc)  # renders without error


def test_unknown_ancestry_is_refused():
    with pytest.raises(ValueError):
        vc.generate(random.Random(0), ancestry="mycomorph")  # not yet tabled


def test_the_spark_tables_are_d20_shaped():
    for table in (
        vc.NEWBEAST_NAMES,
        vc.NEWBEAST_HUES,
        vc.NEWBEAST_MASKS,
        vc.NEWBEAST_ODDITIES,
        vc.TRUEKIN_NAMES,
        vc.TRUEKIN_DEMEANOURS,
        vc.TRUEKIN_FEATURES,
        vc.CACOGEN_NAMES,
        vc.CACOGEN_DEMEANOURS,
        vc.CACOGEN_MISFORTUNES,
        vc.CACOGEN_ECCENTRICITIES,
        vc.SYNTH_NAMES,
        vc.SYNTH_FORMS,
        vc.SYNTH_HEADS,
        vc.SYNTH_MADE_FOR,
        vc.SYNTH_REALISATIONS,
    ):
        assert len(table) == 20
    assert len(vc.NEWBEAST_BEASTS) == 80  # d20 x four columns
