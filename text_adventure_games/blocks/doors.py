from .base import Block


class Locked_Door(Block):
    """
    Blocks progress in this direction until a character unlocks the door.
    """

    def __init__(self, location, door, connection):
        super().__init__("locked door", "The door is locked")
        self.location = location
        self.door = door
        self.connection = connection

        loc_direction = self.location.get_direction(self.connection)
        self.location.add_item(self.door)
        self.location.add_block(loc_direction, self)

        con_direction = self.connection.get_direction(self.location)
        self.connection.add_item(self.door)
        self.connection.add_block(con_direction, self)

        self.door.set_property("is_locked", True)
        self.door.add_command_hint("unlock door")

    def is_blocked(self) -> bool:
        # Conditions of block:
        # * There is a door
        # * The door locked
        if self.door and self.door.get_property("is_locked"):
            return True
        return False

    def to_primitive(self):
        data = super().to_primitive()

        if self.location and hasattr(self.location, "name"):
            data["location"] = self.location.name
        elif "location" in data:
            data["location"] = self.location

        if self.door and hasattr(self.door, "name"):
            data["door"] = self.door.name
        elif "door" in data:
            data["door"] = self.door

        if self.connection and hasattr(self.connection, "name"):
            data["connection"] = self.connection.name
        elif "connection" in data:
            data["connection"] = self.connection

        return data

    @classmethod
    def from_primitive(cls, data):
        location = data["location"]
        door = data["door"]
        connection = data["connection"]
        instance = cls(location, door, connection)
        return instance
