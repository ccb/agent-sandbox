from text_adventure_games.things.base import Thing


def test_get_property_unset_returns_false():
    t = Thing("rock", "a plain rock")
    assert t.get_property("is_locked") is False
    assert t.get_property("anything_at_all") is False


def test_get_property_returns_set_value():
    t = Thing("door", "a wooden door")
    t.set_property("is_locked", True)
    t.set_property("weight", 42)
    assert t.get_property("is_locked") is True
    assert t.get_property("weight") == 42


def test_get_property_does_not_create_entry():
    t = Thing("box", "a small box")
    t.get_property("is_open")
    assert "is_open" not in t.properties
