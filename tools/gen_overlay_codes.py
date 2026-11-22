#!/usr/bin/env python3
"""Regenerate the OVERLAY_CODES table in scripts/overlay.lua.

Collects every string leaf (item + setting codes) from the parsed ER edge
rules and control.lua functions, and embeds them so overlay.lua can evaluate
item state with Tracker:ProviderCountForCode. Run after logic changes:
    python3 tools/gen_overlay_codes.py
"""
import json
import re
import sys

sys.path.insert(0, "tools")
import rule_parser

EXCLUDE = {"AccessibilityLevel", "SequenceBreak", "true", "false"}

BEGIN = "-- BEGIN GENERATED OVERLAY_CODES (tools/gen_overlay_codes.py)"
END = "-- END GENERATED OVERLAY_CODES"


def collect(node, out):
    if isinstance(node, str):
        if node and node not in EXCLUDE and re.match(r"^\w+$", node):
            out.add(node)
    elif isinstance(node, dict):
        for v in node.values():
            collect(v, out)
    elif isinstance(node, list):
        for v in node:
            collect(v, out)


def main():
    codes = set()
    for v in rule_parser.parse_edge_rules("scripts/region_rules.lua").values():
        collect(v, codes)
    for v in rule_parser.parse_functions("scripts/control.lua").values():
        collect(v, codes)
    lines = ",\n".join(f'    "{c}"' for c in sorted(codes))
    table = f"{BEGIN}\nreturn {{\n{lines}\n}}\n{END}"

    src = open("scripts/overlay.lua").read()
    if BEGIN in src:
        src = re.sub(
            re.escape(BEGIN) + r".*?" + re.escape(END),
            lambda _: table.replace("\\", "\\\\"), src, flags=re.S)
    else:
        src = src.replace("local ARG_FUNCS = ",
                          f"local OVERLAY_CODES = (function()\n{table}\nend)()\n\nlocal ARG_FUNCS = ", 1)
    open("scripts/overlay.lua", "w").write(src)
    print(f"overlay codes: {len(codes)}")


if __name__ == "__main__":
    main()
