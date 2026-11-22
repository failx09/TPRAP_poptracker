#!/usr/bin/env python3
"""Cross-check ER_EDGES in scripts/region_rules.lua against the vanilla room
adjacency encoded in locations/rooms/*.json (@<Room> access rules).

reports:
  - rooms-adjacency pairs with no ER edge at all  -> likely missing edges
  - ER TO-category edges with no rooms-adjacency  -> suspicious (vanilla path
    should appear in rooms data), printed for manual review
Run from the pack root: python3 tools/check_edges.py
"""
import collections
import glob
import json
import re
import sys


def er_edges():
    """from -> {flag: to} list of (a, b, flag) undirected pairs."""
    edges = set()
    for line in open("scripts/region_rules.lua"):
        m = re.match(r'\s*(?:["\w]+__)?(\w+)__(\w+?)(?:_A|_B)?__(\w+)\s*=\s*function', line)
        if not m:
            m = re.match(r"\s*(\w+)__(\w+?)(?:_A|_B)?__(\w+)\s*=", line)
        if m:
            a, flag, b = m.group(1), m.group(2), m.group(3)
            edges.add((frozenset((a, b)), flag))
    return edges


def rooms_pairs():
    pairs = set()
    for f in glob.glob("locations/rooms/*.json"):
        data = json.load(open(f))
        for entry in data:
            n = entry.get("name")
            for r in entry.get("access_rules") or []:
                for x in re.findall(r"@(\w+)", r):
                    if x != n:
                        pairs.add((frozenset((n, x)), f))
    return pairs


def main():
    edges = er_edges()
    pairs = rooms_pairs()
    nodes = set()
    for pair, _ in edges:
        nodes |= set(pair)
    room_pairs = {p for p, f in pairs if set(p) <= nodes}

    edge_pairs = {p for p, f in edges}
    to_pairs = {p for p, flag in edges if flag.startswith("TO")}

    missing = room_pairs - edge_pairs
    extra_to = to_pairs - room_pairs

    print(f"ER edges: {len(edges)} (undirected pairs: {len(edge_pairs)})")
    print(f"rooms adjacency pairs within ER nodes: {len(room_pairs)}")
    print(f"\nmissing in ER_EDGES ({len(missing)}):")
    for p in sorted(missing, key=sorted):
        print(f"  {sorted(p)[0]} <-> {sorted(p)[1]}")
    print(f"\nTO edges absent from rooms data ({len(extra_to)}):")
    for p in sorted(extra_to, key=sorted):
        print(f"  {sorted(p)[0]} <-> {sorted(p)[1]}")


if __name__ == "__main__":
    sys.exit(main())
