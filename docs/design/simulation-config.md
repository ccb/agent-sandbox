# Simulation configuration

`backend.sim_config.SimulationConfig` composes reusable engine configuration with
runtime, retrieval, cognition, and optional embedding sections. Empty sections
retain defaults; unknown keys fail validation. YAML and JSON round-trip through
the same typed model.

World content such as Penn's cast and locations remains in world data, while
cross-world runtime/cognition knobs belong here. CLI options can override a
loaded config for one invocation. Secrets never belong in configuration objects
that may be serialized into a manifest.
