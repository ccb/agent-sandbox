#!/usr/bin/env python3
"""Print the input schema (params + style enum) for the Retro Diffusion models."""
import json, requests
from pathlib import Path
from generate_tingen_assets import load_token, DEFAULT_ENV_FILE

tok = load_token(DEFAULT_ENV_FILE)
for model in ("retro-diffusion/rd-plus", "retro-diffusion/rd-fast"):
    r = requests.get(f"https://api.replicate.com/v1/models/{model}",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    d = r.json()
    schema = (d.get("latest_version", {}) or {}).get("openapi_schema", {})
    inp = schema.get("components", {}).get("schemas", {}).get("Input", {})
    props = inp.get("properties", {})
    print(f"\n===== {model} =====")
    for name, spec in sorted(props.items(), key=lambda kv: kv[1].get("x-order", 99)):
        t = spec.get("type", spec.get("allOf", spec.get("$ref", "?")))
        default = spec.get("default", "")
        line = f"  {name}: {t}"
        if default != "":
            line += f"  (default={default})"
        print(line)
        # resolve enum (style etc.)
        ref = None
        if "allOf" in spec and spec["allOf"]:
            ref = spec["allOf"][0].get("$ref")
        elif "$ref" in spec:
            ref = spec["$ref"]
        if ref:
            enum_name = ref.split("/")[-1]
            enum_def = schema.get("components", {}).get("schemas", {}).get(enum_name, {})
            if "enum" in enum_def:
                print(f"      enum: {enum_def['enum']}")
