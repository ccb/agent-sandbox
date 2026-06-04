from text_adventure_games import parsing


class WebParser(parsing.Parser):
    """Parser that records messages instead of printing them."""

    def __init__(self, game, echo_commands=False):
        super().__init__(game, echo_commands=echo_commands)
        self.messages = []

    def ok(self, description: str):
        msg = parsing.Parser.wrap_text(description)
        self.messages.append({"type": "output", "text": msg})
        self.add_description_to_history(description)

    def fail(self, description: str):
        self.last_fail_message = description
        msg = parsing.Parser.wrap_text(description)
        self.messages.append({"type": "error", "text": msg})

    def npc_ok(self, description: str):
        msg = parsing.Parser.wrap_text(description)
        self.messages.append({"type": "npc_action", "text": msg})
        self.add_description_to_history(description)

    def npc_log(self, message: str):
        # Agent trace (labeled reasoning/action); never added to history.
        msg = parsing.Parser.wrap_text(message)
        self.messages.append({"type": "npc_log", "text": msg})

    def get_messages(self):
        msgs = list(self.messages)
        self.messages = []
        return msgs
