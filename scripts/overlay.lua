-- Debug overlay: streams the ER graph state as "[overlay] {json}" lines to
-- stdout so an external viewer (tools/overlay_server.py) can render it.
-- Pair with:  poptracker <pack> 2>&1 | python3 tools/overlay_server.py
-- Requires scripts/graph.lua (reaches it via the canAccess upvalue; disables
-- itself silently if absent). Debug tool only - not part of the tracker UI.

local overlaySig = nil

local function getGraph()
    local g = type(GetGraphDebugRef) == "function" and GetGraphDebugRef() or nil
    if type(g) ~= "table" or type(g.edges) ~= "table" then return nil end
    return g
end

local function esc(s)
    return tostring(s):gsub("[\"\\]", "\\%0")
end

local function levelsToJson(map)
    if not map then return "null" end
    local parts = {}
    for node, level in pairs(map) do
        parts[#parts + 1] = ('"%s":%d'):format(esc(node), level or 0)
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function viaToJson(map)
    if not map then return "null" end
    local parts = {}
    for node, edges in pairs(map) do
        local eps = {}
        for key, level in pairs(edges) do
            eps[#eps + 1] = ('"%s":%d'):format(esc(key), level or 0)
        end
        parts[#parts + 1] = ('"%s":{%s}'):format(esc(node), table.concat(eps, ","))
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function viaRuleToJson(map)
    if not map then return "null" end
    local parts = {}
    for node, edges in pairs(map) do
        local eps = {}
        for key, level in pairs(edges) do
            eps[#eps + 1] = ('"%s":%d'):format(esc(key), level or 0)
        end
        parts[#parts + 1] = ('"%s":{%s}'):format(esc(node), table.concat(eps, ","))
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

-- zero-arg predicates evaluable at runtime; arg-taking helpers excluded
local OVERLAY_CODES = (function()
-- BEGIN GENERATED OVERLAY_CODES (tools/gen_overlay_codes.py)
return {
    "3",
    "ArbitersGroundsBossRoom",
    "ArbitersGroundsEntrance",
    "CastleTownGoronHouse",
    "CastleTownGoronHouseBalcony",
    "CastleTownMaloMart",
    "CastleTownSouth",
    "CityinTheSkyCentralTowerSecondFloor",
    "CityinTheSkyEntrance",
    "DeathMountainElevatorLower",
    "DeathMountainHotSpring",
    "DeathMountainSumoHall",
    "DeathMountainVolcano",
    "ELDIN_MAP_ROOMS",
    "EldinFieldNearCastleTown",
    "EldinFieldWaterBombFishGrotto",
    "EldinLanternCave",
    "FARON_MAP_ROOMS",
    "FaronField",
    "FaronWoodsCorosHouseLower",
    "ForestTempleWestWing",
    "GERUDO_MAP_ROOMS",
    "GerudoDesertBasin",
    "HyruleCastleGraveyard",
    "HyruleCastleMainHall",
    "KakarikoBarnesBombShopLower",
    "KakarikoBarnesBombShopUpper",
    "KakarikoBugHouse",
    "KakarikoEldeInn",
    "KakarikoGorge",
    "KakarikoGraveyard",
    "KakarikoMaloMart",
    "KakarikoRenadosSanctuary",
    "KakarikoRenadosSanctuaryBasement",
    "KakarikoWatchtower",
    "LANAYRU_MAP_ROOMS",
    "LakeHylia",
    "LakeHyliaLanayruSpring",
    "LakeHyliaLongCave",
    "LostWoods",
    "LowerKakarikoVillage",
    "MistAreaNearFaronWoodsCave",
    "NorthEldinField",
    "NorthFaronWoods",
    "Not",
    "ORDONA_MAP_ROOMS",
    "OrdonRanch",
    "OrdonSerasShop",
    "OrdonSpring",
    "OutsideCastleTownSouth",
    "OutsideLinksHouse",
    "SNOWPEAK_MAP_ROOMS",
    "SacredGroveBeforeBlock",
    "SouthFaronWoods",
    "UpperKakarikoVillage",
    "UpperZorasRiver",
    "ZorasDomain",
    "ZorasDomainThroneRoom",
    "agbigkey",
    "agcompleted",
    "agsmallkey",
    "allTwilightCleared",
    "aurusmemo",
    "ballchain",
    "bckey",
    "bombbag",
    "bonksdodamageoff",
    "bonksdodamageon",
    "boomerang",
    "boots",
    "bottle",
    "bow",
    "canAccess",
    "canBreakHCBarrier",
    "canBreakMonkeyCage",
    "canBreakWoodenDoor",
    "canBurnWebs",
    "canClearForest",
    "canClearForestGlitched",
    "canCompleteEldinTwilight",
    "canCompleteFaronTwilight",
    "canCompleteLanayruTwilight",
    "canCompleteMDH",
    "canCompletePrologue",
    "canDefeatAeralfos",
    "canDefeatArgorok",
    "canDefeatArmogohma",
    "canDefeatArmos",
    "canDefeatBabaSerpent",
    "canDefeatBabyGohma",
    "canDefeatBeamos",
    "canDefeatBigBaba",
    "canDefeatBlizzeta",
    "canDefeatBokoblin",
    "canDefeatBokoblinRed",
    "canDefeatBombling",
    "canDefeatBubble",
    "canDefeatBulblin",
    "canDefeatChilfos",
    "canDefeatChu",
    "canDefeatChuWorm",
    "canDefeatDangoro",
    "canDefeatDarkhammer",
    "canDefeatDarknut",
    "canDefeatDiababa",
    "canDefeatDinalfos",
    "canDefeatDodongo",
    "canDefeatFireBubble",
    "canDefeatFireKeese",
    "canDefeatFreezard",
    "canDefeatFyrus",
    "canDefeatGanondorf",
    "canDefeatGhoulRat",
    "canDefeatGoron",
    "canDefeatHangingBabaSerpent",
    "canDefeatHelmasaur",
    "canDefeatIceBubble",
    "canDefeatIceKeese",
    "canDefeatKargorok",
    "canDefeatKeese",
    "canDefeatKingBulblinDesert",
    "canDefeatLeever",
    "canDefeatLizalfos",
    "canDefeatMiniFreezard",
    "canDefeatMorpheel",
    "canDefeatOok",
    "canDefeatPoe",
    "canDefeatRat",
    "canDefeatRedeadKnight",
    "canDefeatShadowBeast",
    "canDefeatSkullKid",
    "canDefeatSkulltula",
    "canDefeatStalchild",
    "canDefeatStalfos",
    "canDefeatStalhound",
    "canDefeatStallord",
    "canDefeatTektite",
    "canDefeatTorchSlug",
    "canDefeatWalltula",
    "canDefeatYoungGohma",
    "canDefeatZant",
    "canDefeatZantHead",
    "canDestroyWebsWithoutLantern",
    "canDoAirRefill",
    "canDoBSMoonBoots",
    "canDoDifficultCombat",
    "canDoJSLJA",
    "canDoJSMoonBoots",
    "canDoLJA",
    "canDoMapGlitch",
    "canDoMoonBoots",
    "canDoNicheStuff",
    "canFreeAllMonkeys",
    "canGetHotSpringWater",
    "canKnockDownHCPainting",
    "canLaunchBombs",
    "canMidnaCharge",
    "canSmash",
    "canStepClip",
    "canStrikePedestal",
    "canUseBacksliceAsSword",
    "canUseBottledFairies",
    "canUseBottledFairy",
    "canWarpMeteor",
    "cheese",
    "clawshot",
    "csbigkey",
    "cscompleted",
    "cssmallkey",
    "dclawshot",
    "dominionrod",
    "doubleclawshot",
    "eldinTwilightCleared",
    "eldintwilightclearedon",
    "faronTwilightCleared",
    "farontwilightclearedon",
    "faronwoodskey",
    "faronwoodsopen",
    "fishingrod",
    "ftbigkey",
    "ftcompleted",
    "ftsmallkey",
    "fusedshadow",
    "fwkey",
    "gatekeys",
    "getItemWheelSlotCount",
    "glitcheson",
    "glowingmastersword",
    "gmbigkey",
    "gmcompleted",
    "gmnowrestling",
    "gmopen",
    "gmshortcuton",
    "gmsmallkey",
    "hasBombs",
    "hasBottle",
    "hasBottles",
    "hasHeavyMod",
    "hasOneHandedItem",
    "hasRangedItem",
    "hasShield",
    "hasWaterBombs",
    "hcbigkey",
    "hcshortcuton",
    "hcsmallkey",
    "hdwalletsize",
    "hiddenskill",
    "hook",
    "horsecall",
    "hylianshield",
    "iliaquestcharm",
    "iliaqueststatue",
    "invoice",
    "lanayruTwilightCleared",
    "lanayrutwilightclearedon",
    "lantern",
    "largequiver",
    "largewallet",
    "largewalletsize",
    "ltbigkey",
    "ltcompleted",
    "ltsmallkey",
    "magicarmor",
    "map",
    "mastersword",
    "mcportalactive",
    "mediumquiver",
    "mediumwallet",
    "mirrorshard",
    "ohko",
    "opendooroftimeon",
    "openmapon",
    "ordonsword",
    "powereddominionrod",
    "ptbigkey",
    "ptcompleted",
    "ptfusedshadows",
    "ptmirrorshards",
    "ptopen",
    "ptsmallkey",
    "ptvanilla",
    "pumpkin",
    "reducedwalletsize",
    "shadowcrystal",
    "shield",
    "shopitemsoff",
    "skiparbitersentranceon",
    "skipbridgedonationon",
    "skipcityintheskyentranceon",
    "skiplakebedentranceon",
    "skipmdhon",
    "skipprologueon",
    "skipsacredgroveentranceon",
    "skipsnowpeakentranceon",
    "skybook",
    "slingshot",
    "spinner",
    "srbigkey",
    "srcompleted",
    "srsmallkey",
    "stportalactive",
    "sword",
    "transformanywhereon",
    "ttbigkey",
    "ttcompleted",
    "ttlight",
    "ttmaster",
    "ttordon",
    "ttsmallkey",
    "ttwooden",
    "uzrportalactive",
    "vanillawalletsize",
    "waterbomb",
    "woodenstatue",
    "woodensword",
    "zoraarmor"
}
-- END GENERATED OVERLAY_CODES
end)()

local ARG_FUNCS = { has=true, hasAll=true, hasAny=true, hasAmount=true }
local lastFuncs = {}
local lastItems = {}

local function evalFuncs()
    local sum, out = 0, {}
    for name, fn in pairs(_G) do
        if type(fn) == "function"
            and (name:sub(1, 3) == "can" or (name:sub(1, 3) == "has"
                and not ARG_FUNCS[name])
            or name:find("Cleared$")) then
            local ok, res = pcall(fn)
            -- treat AccessibilityLevel.None (0) as not satisfied
            local sat = ok and res ~= false and res ~= 0
            out[name] = sat
            if sat then sum = sum + 1 end
        end
    end
    lastFuncs = out
    -- item/setting state for every code the rules reference
    local isum, iout = 0, {}
    for _, code in ipairs(OVERLAY_CODES) do
        local count = Tracker:ProviderCountForCode(code) or 0
        iout[code] = count
        isum = isum + count
    end
    lastItems = iout
    return sum + isum
end

local function funcsToJson()
    local parts = {}
    for name, sat in pairs(lastFuncs) do
        parts[#parts + 1] = ('"%s":%s'):format(esc(name), tostring(sat))
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function itemsToJson()
    local parts = {}
    for code, count in pairs(lastItems) do
        parts[#parts + 1] = ('"%s":%d'):format(esc(code), count)
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function snapshotToJson(G)
    -- unique sorted node list
    local seen, list = {}, {}
    for _, edge in pairs(G.edges) do
        if not seen[edge.from] then seen[edge.from] = true; list[#list + 1] = edge.from end
        if not seen[edge.to] then seen[edge.to] = true; list[#list + 1] = edge.to end
    end
    table.sort(list)
    local nodes = {}
    for i, n in ipairs(list) do nodes[i] = ('"%s"'):format(esc(n)) end

    local edges = {}
    for name, edge in pairs(G.edges) do
        local cat = name:match("__([A-Za-z]+)") or "?"
        edges[#edges + 1] = ('{"f":"%s","t":"%s","c":"%s","k":"%s"}')
            :format(esc(edge.from), esc(edge.to), esc(cat), esc(name))
    end

    return ('{"nodes":[%s],"edges":[%s],"levels":%s,"spawn":"%s","dirty":%s,"via":%s,"viarule":%s,"funcs":%s,"items":%s}')
        :format(
            table.concat(nodes, ","),
            table.concat(edges, ","),
            levelsToJson(G.levelCache),
            esc(G.spawnNode or "OutsideLinksHouse"),
            tostring(G.dirty == true),
            viaToJson(G.accessVia),
            viaRuleToJson(G.accessViaRule),
            funcsToJson(),
            itemsToJson()
        )
end

-- content-sensitive signature: sorted "key=value" concatenation. A numeric
-- hash (levelSum*31 + nLevels) can collide when the level multiset sums
-- identically across different assignments, which stalled emits until the
-- next item update changed the sum.
local function kvSig(map, tag)
    local parts = {}
    for k, v in pairs(map or {}) do
        parts[#parts + 1] = k .. "=" .. tostring(v)
    end
    table.sort(parts)
    return tag .. table.concat(parts, ",")
end

local function stateSignature(G)
    return kvSig(G.levelCache, "L")
        .. "|" .. kvSig(G.accessVia, "V")
        .. "|" .. kvSig(G.accessViaRule, "R")
        .. "|" .. kvSig(lastFuncs, "F")
        .. "|" .. kvSig(lastItems, "I")
        .. "|" .. tostring(G.spawnNode or "")
end


local acc = 0
ScriptHost:AddOnFrameHandler("graph-overlay", function(seconds)
    local G = getGraph()
    if not G then return end
    acc = acc + (seconds or 0)
    if acc < 0.25 then return end
    acc = 0
    evalFuncs()
    local sig = stateSignature(G)
    if sig == overlaySig then return end
    overlaySig = sig
    print("[overlay] " .. snapshotToJson(G))
end)

print("[overlay] ready")
