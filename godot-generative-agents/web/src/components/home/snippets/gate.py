def __call__(self):
    self._preconditions_passed = False
    if self.check_preconditions():
        self._preconditions_passed = True
        return self.apply_effects()
