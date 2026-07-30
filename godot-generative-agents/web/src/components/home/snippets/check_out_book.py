class CheckOutBook(base.Action):
    ACTION_NAME = "check_out_book"
    ACTION_DESCRIPTION = "Check out a library book from the shelf"
    REQUIRED_AFFORDANCES = ("book_shelf",)
    ARGUMENTS_SCHEMA = {
        "book": {
            "type": "item",
            "description": "the exact name of the book to check out",
            "required": True,
        },
    }
