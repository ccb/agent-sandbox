class CheckOutBook(base.Action):
    def check_preconditions(self) -> bool:
        if not self.was_matched(self.character, "No one is checking out a book."):
            return False
        if not self.has_affordance_in_scope(
            self.character,
            "There is no library shelf to check a book out from here.",
        ):
            return False
        if self.book is not None:
            holder = self.book.get_property("checked_out_by")
            if holder:
                message = (
                    f"You already have {self.book.name} checked out."
                    if holder == self.character.name
                    else f"The {self.book.name} is already checked out by {holder}."
                )
                self.parser.fail(message)
                return False
        if not self.was_matched(self.book, "I don't see that book on the shelf."):
            return False
        if not self.book.get_property("library_book"):
            self.parser.fail(f"The {self.book.name} isn't a library book.")
            return False
        return True

    def apply_effects(self):
        # add_to_inventory removes the book from the shelf's location itself.
        self.character.add_to_inventory(self.book)
        self.book.set_property("checked_out_by", self.character.name)
        return self.parser.ok(
            f"{self.character.name} checks out {self.book.name} from the shelf."
        )
