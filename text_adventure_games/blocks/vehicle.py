from .base import Block


class RequiresVehicle(Block):
    """Blocks an exit unless someone present is riding a vehicle/mount -- the
    "it's too far to go on foot" gate (see actions/vehicles.py).

    Wire it on the origin room's exit::

        drawbridge.add_block("west", RequiresVehicle(drawbridge,
                             "It's too far to travel on foot. Perhaps on horseback..."))
    """

    def __init__(self, location, description: str = "You can't go that way on foot."):
        super().__init__("You need a ride", description)
        self.location = location

    def is_blocked(self) -> bool:
        for character in self.location.characters.values():
            if getattr(character, "riding", None) is not None:
                return False
        return True

    def to_primitive(self):
        data = super().to_primitive()
        if self.location and hasattr(self.location, "name"):
            data["location"] = self.location.name
        elif "location" in data:
            data["location"] = self.location
        data["description"] = self.description
        return data

    @classmethod
    def from_primitive(cls, data):
        return cls(data["location"], description=data.get("description"))
