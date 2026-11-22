#!/usr/bin/env python3
"""Derive overworld map coordinates for ER nodes from the pack's location data.

Sources (in priority order per node; earlier wins):
  1. access_rules containing "canAccess|<Node>" on an entry with map_locations
  2. hosted_item door codes ("<From>_TO_<To>" concatenated form) - marker sits
     at the from-door, so the From node gets the coordinate
  3. name matching: location names on the overworld maps whose token set
     contains a node's token set ("Castle Town Doctors Office Lower" ->
     CastleTownDoctorsOfficeLower, "Eldin Field Poe" -> EldinField). Multiple
     candidates: longest node name wins; multiple matching entries: average.
  4. BETWEEN table: hardcoded "node sits between refA and refB" midpoints.

Writes tools/node_positions.json: {"<Node>": [x, y], ...} preferring the
"overworldfull" map. Run from the pack root: python3 tools/derive_positions.py
"""
import collections
import glob
import json
import math
import re
import sys

MAP_PRIORITY = {"overworldfull": 0, "overworld": 1}

# Hand-read from the map image (8704x9984): overrides for anchors the data
# placed implausibly, plus key region anchors. Applied last, wins over all.
POSITIONS = {
    # Castle Town west road: bridge west of the square (square ~4700,3900)
    "CastleTownWest": [4440, 3895],
    "OutsideCastleTownWest": [4290, 3900],
    "OutsideCastleTownWestGrottoLedge": [4180, 3960],
    "OutsideCastleTownWestHelmasaurGrotto": [4060, 3990],
    # Eldin field west edge, toward the castle town bridge
    "EldinFieldNearCastleTown": [5490, 3890],
    # Eldin Lantern Cave: bomb-openable cave in Kakariko Gorge (author
    # marker "Eldin Lantern Cave" 6043,5714; NOT the lava/stock cave)
    "KakarikoGorgeCaveEntrance": [6043, 5714],
    "EldinLanternCave": [6090, 5655],
    # North street (Hyrule Castle interior nodes come from the HC dungeon map)
    "CastleTownNorth": [4730, 3530],
    "CastleTownNorthBehindFirstDoor": [4730, 3460],
    # North Eldin field: Bridge of Eldin area (bridge markers 7282-7549,
    # 2368-3159); stock cave = "lava cave" per eldin.json refs, NE field
    "NorthEldinField": [7150, 2350],
    "EldinFieldOutsideHiddenVillage": [6540, 2130],
    "EldinFieldStalfosGrotto": [7006, 1544],
    "EldinFieldFromLavaCaveLower": [7565, 2450],
    "EldinFieldLavaCaveLedge": [7650, 2360],
    "EldinFieldLavaCaveLower": [7595, 2500],
    "EldinFieldLavaCaveUpper": [7660, 2430],
    # Cave of Ordeals: figure-8 pit in the SW Gerudo desert
    "GerudoDesertCaveofOrdealsPlateau": [570, 6065],
    # Castle Town south gate (data had it 3000 px south in Faron territory)
    "CastleTownSouth": [4660, 4530],
    # Ordon Spring: north of Ordon village (Ordon Spring Golden Wolf marker
    # 4793,8527; the pond at ~4700,7550 belongs to South Faron Woods)
    "OrdonSpring": [4793, 8527],
    # the narrow strip over the gorge between the spring pond and the woods
    "OrdonBridge": [4860, 8350],
    # Snowpeak climb: SW slope of the peak (route to Zora's Domain is off-map)
    "SnowpeakClimbUpper": [1900, 1900],
    "SnowpeakClimbLower": [2000, 2500],
    # Snowpeak Ruins front doors (data had both in the void near Lake Hylia)
    "SnowpeakRuinsLeftDoor": [1080, 2900],
    "SnowpeakRuinsRightDoor": [1260, 2900],
    # Cave of Ordeals floors: vertical stack beside the figure-8 pit (no map
    # image exists for the tower; a column keeps the chain from stretching)
    "GerudoDesertCaveofOrdealsFloors0111": [700, 6130],
    "GerudoDesertCaveofOrdealsFloors1221": [700, 6230],
    "GerudoDesertCaveofOrdealsFloors2231": [700, 6330],
    "GerudoDesertCaveofOrdealsFloors3241": [700, 6430],
    "GerudoDesertCaveofOrdealsFloors4250": [700, 6530],
    # Faron Woods, canonical layout (author markers + map: mist = purple
    # blob 4340-4650 x 6980-7390; south woods = landmass with pond+portal
    # 4600-5100 x 7300-7900; grove past = floating island 3620-3730 x 6760-6920)
    "NorthFaronWoods": [4380, 7020],
    "NorthFaronLostWoodsEntrance": [4250, 7150],
    "SouthFaronWoods": [4750, 7560],
    "SouthFaronWoodsBehindGate": [4580, 7290],
    "SouthFaronWoodsCorosLedge": [4830, 7460],
    "SouthFaronWoodsOwlStatueArea": [4668, 7194],
    "SouthFaronWoodsAboveOwlStatue": [4610, 7130],
    "FaronWoodsCorosHouseLower": [4870, 7360],
    "FaronWoodsCorosHouseUpper": [4940, 7460],
    # cave bypassing the mist: south entrance at author marker
    # "South Cave" 4713,7446; interior drawn NE of the woods
    "FaronWoodsCave": [4900, 7000],
    "FaronWoodsCaveSouthernEntrance": [4740, 7430],
    "FaronWoodsCaveNorthernEntrance": [4820, 7050],
    "MistAreaInsideMist": [4480, 7180],
    "MistAreaCenterStump": [4514, 7219],
    "MistAreaNearOwlStatueChest": [4620, 7160],
    "MistAreaUnderOwlStatueChest": [4672, 7200],
    "MistAreaNearFaronWoodsCave": [4780, 7090],
    "MistAreaOutsideFaronMistCave": [4810, 7021],
    "MistAreaFaronMistCave": [4870, 7065],
    "MistAreaNearNorthFaronWoods": [4530, 7010],
    "MistAreaNearNorthFaronWoodsBehindGate": [4460, 6950],
    "SacredGroveLower": [3620, 7080],
    "SacredGroveUpper": [3702, 6867],
    "SacredGroveBeforeBlock": [3790, 6890],
    "SacredGrovePast": [3676, 6800],
    "SacredGrovePastBehindWindow": [3675, 6748],
    "TempleofTimeEntrance": [3700, 6820],
    "LostWoods": [3267, 6980],
    "LostWoodsBabaSerpentGrotto": [3502, 7114],
    "LostWoodsLowerBattleArena": [3150, 7160],
    "LostWoodsUpperBattleArena": [3390, 7130],
    "ForestTempleEntrance": [3753, 6930],
    # Lake Hylia canon (markers: Lanayru Spring 3500,5262; Lake Lantern
    # Cave 3137,5550; Shell Blade Grotto 2853,4452; Flight By Fowl 3108,4945;
    # Lakebed entrance marker 3400,4758)
    "LakeHyliaLanayruSpring": [3500, 5262],
    "LakeHyliaCaveEntrance": [3137, 5550],
    "LakeHyliaLongCave": [3095, 5620],
    "LakeHyliaShellBladeGrotto": [2853, 4452],
    "LakeHyliaBridge": [3395, 4880],  # the land strip through the lake
    "LakeHyliaFlightByFowl": [3130, 4950],
    "LakebedTempleEntrance": [3400, 4758],
    "CityinTheSkyEntrance": [3200, 4990],
}

# node sits at ref + pixel offset
OFFSETS = {
    # Ordon
    "OrdonSerasShop": ("OutsideLinksHouse", -160, -40),
    "OrdonBosHouse": ("OutsideLinksHouse", 180, -120),
    "OrdonShieldHouseLower": ("OrdonSwordHouse", -120, -40),
    "OrdonShieldHouseUpper": ("OrdonSwordHouse", 120, -40),
    "OrdonLinksHouse": ("OutsideLinksHouse", 0, 100),
    # Kakariko
    "KakarikoBarnesBombShopLower": ("KakarikoMaloMart", -140, -60),
    "KakarikoBarnesBombShopUpper": ("KakarikoMaloMart", 140, 60),
    "KakarikoEldeInn": ("KakarikoMaloMart", 0, -160),
    "KakarikoEldeInnLeftDoor": ("KakarikoMaloMart", -140, -180),
    "KakarikoEldeInnRightDoor": ("KakarikoMaloMart", 140, -180),
    "KakarikoBugHouseDoor": ("KakarikoBugHouse", 0, 120),
    "KakarikoBugHouseCeilingHole": ("KakarikoBugHouse", 0, -120),
    "KakarikoGorgeBehindGate": ("KakarikoGorge", 160, -60),
    "KakarikoGorgeKeeseGrotto": ("KakarikoGorge", -80, 160),
    "KakarikoWatchtowerUpperDoor": ("KakarikoWatchtower", 0, -120),
    "KakarikoRenadosSanctuary": ("KakarikoWatchtower", -100, -140),
    "KakarikoRenadosSanctuaryBackLeftDoor": ("KakarikoWatchtower", -140, -200),
    "KakarikoRenadosSanctuaryBackRightDoor": ("KakarikoWatchtower", -60, -200),
    "HiddenVillageImpazHouse": ("HiddenVillage", 0, 120),
    # Castle Town
    "CastleTownNorthBehindFirstDoor": ("CastleTownNorth", -60, 60),
    "OutsideCastleTownEast": ("CastleTownEast", 140, -60),
    "OutsideCastleTownWest": ("CastleTownWest", -140, -60),
    "OutsideCastleTownWestGrottoLedge": ("CastleTownWest", -200, -140),
    "OutsideCastleTownWestHelmasaurGrotto": ("CastleTownWest", -240, -40),
    "SouthCastleTownDoors": ("CastleTownSouth", 60, -60),
    "CastleTownJovanisHouse": ("CastleTownTelmasBar", -120, -80),
    "CastleTownSeerHouse": ("CastleTownTelmasBar", 120, -80),
    "CastleTownAgithasHouse": ("CastleTownMaloMart", -140, 100),
    "CastleTownGoronHouse": ("CastleTownMaloMart", 140, 120),
    "CastleTownSTARGame": ("CastleTownMaloMart", 0, -140),
    "CastleTownDoctorsOfficeEntrance": ("CastleTownDoctorsOfficeLower", 0, 120),
    "CastleTownDoctorsOfficeLeftDoor": ("CastleTownDoctorsOfficeLower", -120, 60),
    "CastleTownDoctorsOfficeRightDoor": ("CastleTownDoctorsOfficeLower", 120, 60),
    "CastleTownDoctorsOfficeUpper": ("CastleTownDoctorsOfficeLower", 0, -100),
    "CastleTownDoctorsOfficeBalcony": ("CastleTownDoctorsOfficeLower", 60, -160),
    "CastleTownGoronHouseLeftDoor": ("CastleTownMaloMart", 100, 180),
    "CastleTownGoronHouseRightDoor": ("CastleTownMaloMart", 200, 120),
    "CastleTownGoronHouseBalcony": ("CastleTownMaloMart", 200, 180),
    # Faron / Sacred Grove / Temple of Time (anchors are explicit POSITIONS)
    "FaronFieldFishingGrotto": ("FaronField", 120, 160),
    "ForestTempleLobby": ("ForestTempleEntrance", 110, -30),
    "Ook": ("ForestTempleLobby", -110, -120),
    "LanayruFieldCaveEntrance": ("LanayruIcePuzzleCave", -35, 60),
    "LakeHyliaBridgeGrottoLedge": ("LakeHyliaBridge", 40, 280),
    # Gerudo / Arbiter's / Palace
    "GerudoDesertBasin": ("GerudoDesert", -160, 100),
    "GerudoDesertNorthEastLedge": ("GerudoDesert", 160, -160),
    "GerudoDesertChuGrotto": ("GerudoDesert", 100, 160),
    "GerudoDesertCaveofOrdealsPlateau": ("MirrorChamberPortal", 120, -120),
    "ArbitersGroundsEntrance": ("OutsideArbitersGrounds", 0, 230),
    "PalaceofTwilightEntrance": ("MirrorChamberPortal", -160, -160),
    # Eldin / Death Mountain / Goron Mines
    "DeathMountainNearKakariko": ("DeathMountainTrail", -120, -120),
    "DeathMountainOutsideSumoHall": ("DeathMountainVolcano", 60, 80),
    "DeathMountainSumoHall": ("DeathMountainVolcano", 120, 140),
    "DeathMountainSumoHallElevator": ("DeathMountainVolcano", 0, 220),
    "DeathMountainElevatorLower": ("DeathMountainVolcano", -60, 260),
    "DeathMountainHotSpring": ("DeathMountainTrail", 80, -160),
    "GoronMinesEntrance": ("DeathMountainSumoHallGoronMinesTunnel", 0, 140),
    "HyruleFieldNearSpinnerRails": ("LanayruField", -140, 160),
    "LanayruFieldBehindBoulder": ("LanayruField", -120, 120),
    "LanayruFieldChuGrotto": ("LanayruField", 120, 160),
    "LanayruFieldCaveEntrance": ("LanayruField", 0, 200),
    "EldinFieldNearCastleTown": ("EldinField", -160, -60),
    "EldinFieldOutsideHiddenVillage": ("EldinField", 160, -140),
    "EldinFieldGrottoPlatform": ("EldinField", 0, -160),
    # Snowpeak / Zora
    "ZorasDomainThroneRoom": ("ZorasDomain", 100, 60),
    "ZorasDomainTopofWaterfall": ("ZorasDomain", 0, -120),
    "ZorasDomainWestLedge": ("ZorasDomain", -120, -60),
    "ZorasDomainSnowpeakEntrance": ("ZorasDomain", -160, 40),
    # remaining unpositioned odd ones
    "CityinTheSkyLobby": ("CityinTheSkyEntrance", 640, 90),  # cs void paste box
    "LakeHyliaLanayruSpring": ("LakeHylia", 60, 80),
    "SnowpeakRuinsCagedFreezardRoom": ("SnowpeakRuinsEntrance", 120, 60),
    "TempleofTimeCrumblingCorridor": ("TempleofTimeEntrance", -1400, 750),  # tt void paste
    "UpperZorasRiverIzasHouse": ("UpperZorasRiver", 120, 60),
    "SnowpeakClimbLower": ("ZorasDomain", -400, 300),
    "SnowpeakSummitUpper": ("SnowpeakSummitLower", 0, -140),
    "SnowpeakRuinsEntrance": ("SnowpeakSummitLower", -60, 160),
    "SnowpeakIceKeeseGrotto": ("SnowpeakFreezardGrotto", -100, 100),
    "FishingHoleHouse": ("FishingHole", 80, -60),
    "FishingHolePieceofHeart": ("FishingHole", -80, -60),
    # Mirror Chamber (circular pedestal far west, portal at its top)
    "MirrorChamberUpper": ("MirrorChamberPortal", 0, -100),
    "MirrorChamberLower": ("MirrorChamberPortal", 0, 60),
    # Lost Woods interior (anchors explicit; arenas stay relative)
    # Kakariko watchtower / sanctuary cluster
    "KakarikoVillageBehindGate": ("KakarikoMaloMart", -160, -40),
    "KakarikoTopofWatchtower": ("KakarikoWatchtower", 0, -200),
    "KakarikoWatchtowerLowerDoor": ("KakarikoWatchtower", 0, 140),
    "KakarikoWatchtowerDigSpot": ("KakarikoWatchtower", 120, 140),
    "KakarikoRenadosSanctuaryBasement": ("KakarikoWatchtower", -100, -260),
    "KakarikoRenadosSanctuaryFrontLeftDoor": ("KakarikoWatchtower", -140, -80),
    "KakarikoRenadosSanctuaryFrontRightDoor": ("KakarikoWatchtower", -60, -80),
    # South Faron Woods details (explicit POSITIONS; nothing relative)
    # Ordon ranch / Bo's house
    "OrdonRanchEntrance": ("OrdonRanch", 60, -60),
    "OrdonRanchStable": ("OrdonRanch", 100, -20),
    "OrdonBosHouseLeftDoor": ("OrdonBosHouse", -90, -40),
    "OrdonBosHouseRightDoor": ("OrdonBosHouse", 90, -40),
    # South Faron Woods details
    "SouthFaronWoodsCorosLedge": ("SouthFaronWoods", -160, 60),
    "SouthFaronWoodsOwlStatueArea": ("SouthFaronWoods", 60, 180),
    "SouthFaronWoodsAboveOwlStatue": ("SouthFaronWoods", 60, 120),
    "SouthFaronWoodsBehindGate": ("SouthFaronWoods", -60, 240),
}

# Nodes with no coords of their own, placed AFTER the dungeon transforms so
# they can reference dungeon-map nodes (which don't exist during offset
# resolution and must not be moved by snap-to-land).
POST_DUNGEON_OFFSETS = {
    "HyruleCastleTowerClimb": ("HyruleCastleMainHall", -90, -70),
    "HyruleCastleAfterDoubleDinalfos": ("HyruleCastleMainHall", 90, -70),
}

# node sits between two positioned refs (midpoint)
BETWEEN = {
    "OrdonVillage": ("OutsideLinksHouse", "OrdonSwordHouse"),
    "OrdonRanch": ("OrdonRanchGrotto", "OrdonBridge"),
    "LowerKakarikoVillage": ("KakarikoGorge", "KakarikoBugHouse"),
    "UpperKakarikoVillage": ("KakarikoMaloMart", "DeathMountainTrail"),
    "CastleTownCenter": ("OutsideCastleTownSouth", "CastleTownNorthInsideBarrier"),

    "GerudoDesertOutsideBulblinCamp": ("GerudoDesert", "BulblinCamp"),
}

# Dungeon map placements: dungeon Full.png images pasted into the overworld
# map's void areas, roughly where the dungeon sits in the game world.
# prefix: (anchor_node, center_dx, center_dy, scale) - image center is placed
# at anchor + offset; nodes use pos = center - 0.5*scaled_size + coord*scale
DUNGEON_PLACEMENTS = {
    "ag": ("OutsideArbitersGrounds", 95, 828, 0.25),      # void below mirror chamber
    "sr": ("SnowpeakRuinsEntrance", 931, 312, 0.25),      # void SE of Snowpeak
    "hc": ("CastleTownNorthInsideBarrier", -15, -301, 0.30),  # just above the castle gate
    "pt": ("PalaceofTwilightEntrance", 55, -579, 0.25),   # void NW corner
    "lt": ("LakebedTempleEntrance", -1300, 1232, 0.25),   # void between desert and lake
    "cs": ("CityinTheSkyEntrance", 801, 52, 0.25),        # void between lake and Castle Town
    "ft": ("ForestTempleEntrance", 1443, 814, 0.30),      # void SE of Faron Woods
    "tt": ("TempleofTimeEntrance", -1475, 792, 0.30),     # void SW of Sacred Grove
    "gm": ("GoronMinesEntrance", -49, 1262, 0.25),        # void below Death Mountain
}
DUNGEON_IMAGES = {
    "ag": "images/Dungeons/Arbiter's Grounds/Full.png",
    "sr": "images/Dungeons/Snowpeak Ruins/Full.png",
    "hc": "images/Dungeons/Hyrule Castle/Full.png",
    "pt": "images/Dungeons/Palace of Twilight/Full.png",
    "lt": "images/Dungeons/Lakebed Temple/Full.png",
    "cs": "images/Dungeons/City in the Sky/Full.png",
    "ft": "images/Dungeons/Forest Temple/Full.png",
    "tt": "images/Dungeons/Temple of Time/Full.png",
    "gm": "images/Dungeons/Goron Mines/Full.png",
}

SUFFIX_STRIP = re.compile(r"\s*->.*$")


def er_nodes():
    nodes = set()
    for line in open("scripts/region_rules.lua"):
        m = re.match(r"\s*(\w+)__\w+__(\w+)\s*=", line)
        if m:
            nodes |= {m.group(1), m.group(2)}
    return nodes


def tokens(name):
    return tuple(re.sub(r"[^a-z0-9]", " ", name.lower()).split())


def node_tokens(name):
    # CamelCase -> words, keep digits attached ("CityInTheSky" -> city in the sky)
    return tokens(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name))


def parse_hosted(code, nodes_by_len):
    """Parse 'FromA_TO_ToA' concatenated codes; returns (from, to) or None."""
    code = code.strip()
    if code.startswith("START_"):
        rest = code[len("START_"):]
        for nl in nodes_by_len:
            if rest.startswith(nl + "_"):
                return nl, rest[len(nl) + 1:]
        return None
    if "_LEADS_" in code:
        code = code.split("_LEADS_")[0]
    for nl in nodes_by_len:  # longest first
        if code.startswith(nl + "TO"):
            rest = code[len(nl) + 2:]
            if rest in nodes_by_len:
                return nl, rest
            cand = [n for n in nodes_by_len if n.startswith(rest)]
            if len(cand) == 1:
                return nl, cand[0]
            return nl, None
    return None


def dungeon_nodes():
    """node -> {fullMap: (x, y)} for dungeon rooms, from locations/dungeons:
    canAccess refs on room entries, coords from own + descendant map_locations."""
    ncoords = collections.defaultdict(dict)

    def walk(e, acc):
        if isinstance(e, dict):
            mynodes = set()
            for r in e.get("access_rules") or []:
                if isinstance(r, str):
                    mynodes |= set(re.findall(r"canAccess\|(\w+)", r))
            mls = e.get("map_locations") or []
            for n in acc | mynodes:
                for ml in mls:
                    if ml.get("x") is None:
                        continue
                    d = ncoords.setdefault(n, {})
                    if ml["map"] not in d:
                        d[ml["map"]] = (ml["x"], ml["y"])
            acc = acc | mynodes
            for c in e.get("children", []):
                walk(c, acc)
        elif isinstance(e, list):
            for c in e:
                walk(c, set())

    for f in glob.glob("locations/dungeons/*.json"):
        try:
            walk(json.load(open(f)), set())
        except Exception:
            pass
    return ncoords


def apply_dungeons(out):
    """Position dungeon room nodes on their pasted Full.png images and bake
    tools/overworld_composite.png. Returns count of newly positioned nodes."""
    nc = dungeon_nodes()
    added = 0
    pasted = []
    for prefix, (anchor, dx, dy, scale) in DUNGEON_PLACEMENTS.items():
        ap = out.get(anchor)
        if not ap:
            print(f"  dungeon {prefix}: anchor {anchor} missing")
            continue
        cx, cy = ap[0] + dx, ap[1] + dy
        try:
            from PIL import Image
            img = Image.open(DUNGEON_IMAGES[prefix]).convert("RGBA")
        except Exception as ex:
            print(f"  dungeon {prefix}: image load failed ({ex})")
            continue
        w, h = img.size
        sw, sh = int(w * scale), int(h * scale)
        ox, oy = cx - sw // 2, cy - sh // 2
        pasted.append((prefix, img, (ox, oy), (sw, sh)))
        for n, maps in nc.items():
            full = maps.get(prefix + "full")
            if full and n not in out:
                out[n] = [int(ox + full[0] * scale), int(oy + full[1] * scale)]
                added += 1
    for n, (ref, dx, dy) in POST_DUNGEON_OFFSETS.items():
        rp = out.get(ref)
        if rp and n not in out:
            out[n] = [rp[0] + dx, rp[1] + dy]
            added += 1
        elif not rp:
            print(f"  post-dungeon {n}: ref {ref} missing")
    if pasted:
        try:
            from PIL import Image
            base = Image.open("images/Overworld/Full Map Big.png").convert("RGBA")
            for _prefix, img, (ox, oy), (sw, sh) in pasted:
                base.alpha_composite(img.resize((sw, sh), Image.LANCZOS), (ox, oy))
            base.save("tools/overworld_composite.png")  # RGBA: void stays transparent
            print(f"composite written: tools/overworld_composite.png, "
                  f"dungeon nodes positioned: {added}")
        except Exception as ex:
            print(f"  composite generation failed: {ex}")
    return added


def declump(out, min_dist=100, rounds=60):
    """Push apart nodes closer than min_dist so labels stay readable.
    Gentle: capped per-round movement, runs after all positioning."""
    names = list(out)
    step = 15.0
    for _ in range(rounds):
        moved = False
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = out[names[i]], out[names[j]]
                dx, dy = b[0] - a[0], b[1] - a[1]
                d2 = dx * dx + dy * dy
                if d2 >= min_dist * min_dist or d2 == 0:
                    if d2 == 0:  # exact overlap: separate along x
                        dx, d2 = 1.0, 1.0
                    else:
                        continue
                d = d2 ** 0.5
                f = min((min_dist - d) / 2, step) / d
                a[0] -= dx * f; a[1] -= dy * f
                b[0] += dx * f; b[1] += dy * f
                moved = True
        if not moved:
            break
    for n in names:  # keep positions.json integer-clean
        out[n] = [int(round(out[n][0])), int(round(out[n][1]))]


def main():
    nodes = er_nodes()
    nodes_by_len = sorted(nodes, key=len, reverse=True)
    nt_by_len = sorted(((n, node_tokens(n)) for n in nodes),
                       key=lambda p: len(p[1]), reverse=True)

    coords = collections.defaultdict(dict)  # node -> {map: (x,y)}

    def add(node, m, x, y):
        if node and x is not None:
            coords[node].setdefault(m, (x, y))

    name_hits = collections.defaultdict(list)  # node -> [(x, y), ...]

    def add_name(node, x, y):
        if x is not None:
            name_hits[node].append((x, y))

    def walk(e, inherited_ml):
        if isinstance(e, dict):
            mls = e.get("map_locations") or inherited_ml
            targets = set()
            for r in e.get("access_rules") or []:
                if isinstance(r, str):
                    targets |= set(re.findall(r"canAccess\|(\w+)", r))
            for s in e.get("sections") or []:
                for code in (s.get("hosted_item") or "").split(","):
                    pair = parse_hosted(code, nodes_by_len)
                    if pair and pair[0]:
                        targets.add(pair[0])
                    # NOTE: only the From side gets the marker coordinate; the
                    # To node lives somewhere else entirely
            for ml in mls or []:
                for n in targets:
                    add(n, ml.get("map"), ml.get("x"), ml.get("y"))
                # name matching against overworld maps only
                if ml.get("map") in MAP_PRIORITY and e.get("name"):
                    clean = SUFFIX_STRIP.sub("", e["name"])
                    toks = tokens(clean)
                    if len(toks) >= 2:
                        cands = [(n, t) for n, t in nt_by_len
                                 if set(t) <= set(toks)]
                        if cands:
                            n = cands[0][0]  # longest token set wins
                            add_name(n, ml.get("x"), ml.get("y"))
            for c in e.get("children", []):
                walk(c, mls)
        elif isinstance(e, list):
            for c in e:
                walk(c, None)

    for f in glob.glob("locations/**/*.json", recursive=True):
        try:
            data = json.load(open(f))
        except Exception:
            continue
        walk(data, None)

    out = {}

    def best_map(maps):
        best = None
        for m, (x, y) in maps.items():
            key = MAP_PRIORITY.get(m, 9)
            if best is None or key < best[0]:
                best = (key, x, y)
        return best

    # sources 1+2
    for node, maps in coords.items():
        b = best_map(maps)
        if b:
            out[node] = [b[1], b[2]]
    # source 3: average of name hits
    for node, hits in name_hits.items():
        if node not in out:
            out[node] = [sum(h[0] for h in hits) // len(hits),
                         sum(h[1] for h in hits) // len(hits)]
    # source 4: hand-read map overrides (win over everything derived above),
    # so OFFSETS may reference them
    out.update({n: list(v) for n, v in POSITIONS.items()})
    # source 5: OFFSETS / BETWEEN (resolving refs iteratively, refs may
    # themselves be derived)
    pending = {**{n: ("off", r) for n, (r, *_ ) in OFFSETS.items()},
               **{n: ("mid", a, b) for n, (a, b) in BETWEEN.items()}}
    for _ in range(4):
        progress = False
        for node, spec in list(pending.items()):
            if node in out:
                del pending[node]
                continue
            if spec[0] == "off":
                ref, dx, dy = OFFSETS[node]
                p = out.get(ref)
                if p:
                    out[node] = [p[0] + dx, p[1] + dy]
                    del pending[node]
                    progress = True
            else:
                a, b = BETWEEN[node]
                pa, pb = out.get(a), out.get(b)
                if pa and pb:
                    out[node] = [(pa[0] + pb[0]) // 2, (pa[1] + pb[1]) // 2]
                    del pending[node]
                    progress = True
        if not progress:
            break
    for node, spec in pending.items():
        refs = OFFSETS[node][0] if spec[0] == "off" else f"{BETWEEN[node][0]}/{BETWEEN[node][1]}"
        print(f"  unresolved {node}: ref {refs} not positioned")

    # source 6: snap anchors that sit on the map's black background onto the
    # nearest land pixel, then spread exact collisions on a small circle
    try:
        from PIL import Image
        img = Image.open("images/Overworld/Full Map Big.png").convert("RGB")
        pxi = img.load()
        W, H = img.size

        def on_land(x, y):
            if not (0 <= x < W and 0 <= y < H):
                return False
            r, g, b = pxi[x, y]
            return g > 25 or r > 25 or b > 25

        def snap(x, y):
            if on_land(x, y):
                return x, y
            for rad in range(4, 601, 4):
                best = None
                for a in range(0, 360, 6):
                    nx, ny = int(x + rad * math.cos(math.radians(a))), \
                             int(y + rad * math.sin(math.radians(a)))
                    if on_land(nx, ny):
                        d = (nx - x) ** 2 + (ny - y) ** 2
                        if best is None or d < best[0]:
                            best = (d, nx, ny)
                if best:
                    return best[1], best[2]
            return None

        snapped, unsnapped = 0, []
        for n, (x, y) in list(out.items()):
            s = snap(x, y)
            if s:
                if s != (x, y):
                    out[n] = list(s)
                    snapped += 1
            else:
                unsnapped.append(n)
        # spread exact pixel collisions
        bypix = collections.defaultdict(list)
        for n, (x, y) in out.items():
            bypix[(x, y)].append(n)
        for key, group in bypix.items():
            if len(group) < 2:
                continue
            for i, n in enumerate(group):
                a = 2.4 * i
                out[n] = [key[0] + int(35 * math.cos(a)),
                          key[1] + int(35 * math.sin(a))]
                s = snap(*out[n])
                if s:
                    out[n] = list(s)
        print(f"snapped to land: {snapped}, unsnappable: {unsnapped or 'none'}")
    except ImportError:
        print("PIL unavailable, skipping land snap")
    apply_dungeons(out)
    declump(out, min_dist=100)

    # manual edits from the overlay editor win over everything
    try:
        with open("tools/overlay_edits.json") as fh:
            man = json.load(fh).get("positions") or {}
        out.update(man)
        if man:
            print(f"manual overrides applied: {len(man)}")
    except (OSError, ValueError):
        pass

    with open("tools/node_positions.json", "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)

    missing = sorted(nodes - set(out))
    print(f"nodes: {len(nodes)}, positioned: {len(out)}, missing: {len(missing)}")
    src = collections.Counter()
    for n in out:
        src["direct" if n in coords else
            ("name" if n in name_hits else "hardcoded")] += 1
    print("by source:", dict(src))
    for n in missing:
        print("  missing:", n)


if __name__ == "__main__":
    sys.exit(main())
