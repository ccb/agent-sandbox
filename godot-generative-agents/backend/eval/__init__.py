"""Offline evaluation tools for exported run artifacts (issue #584).

Nothing here touches a live simulation: every tool in this package reads a
*finished* run's artifacts -- a baked ``penn_replay.json`` or a #304 RunStore
run directory -- and writes a report. See :mod:`backend.eval.believability`.
"""
