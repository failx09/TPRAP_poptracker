-- Graph backend for accessability

--- @alias AccessLevel integer

--- @class Graph
--- @field nodes table<Node, boolean>
--- @field edges table<string, Edge>
--- @field outAdj table<Node, table<Edge>>
--- @field spawn Node
--- @field avoidMaps table<Edge, table<Node, AccessLevel>>
--- @field dirty boolean
--- @field accessVia table<Node, table<string, integer>> -- debug overlay only
---
--- @alias RuleFn fun(): AccessLevel | boolean
---
--- @class Edge
--- @field from Node
--- @field to Node
--- @field flags string
--- @field rules RuleFn[][]
---
--- @alias Node string
---
--- @class Compute
--- @field gen integer
--- @field running boolean
--- @field mapQ table<Edge>
--- @field q table<Node>
--- @field visited table<Node, boolean>
--- @field ruleEvals integer
--- @field count integer
--- @field currentEdges table<Edge, boolean>
--- @field accessVia table<Node, table<string, integer>>
--- @field accessViaRule table<Node, table<string, integer>>
--- @field dirtyDuringRun boolean
---

local Compute = {
    running = false,
    mapQ = {},
    q = {},
    visited = {},
    ruleEvals = 0,
    count = 0,
    currentEdges = {},
    accessVia = {},
    accessViaRule = {}
}

local Graph = {}

local DEFAULT_SPAWN = "OutsideLinksHouse"
local FULL = ""

Graph.nodes = {}
Graph.edges = {}
Graph.outAdj = {}
Graph.spawn = DEFAULT_SPAWN
Graph.avoidMaps = {}
Graph.dirty = true

-- Debug output via print(), gated on ENABLE_DEBUG_LOG (init.lua).
-- Set Graph.debugVerbose = true for per-promotion lines.
Graph.debugVerbose = true

local function levelName(level)
    if level == AccessibilityLevel.Normal then return "Normal" end
    if level == AccessibilityLevel.SequenceBreak then return "SequenceBreak" end
    if level == AccessibilityLevel.None then return "None" end
    return tostring(level)
end

local function dbg(msg)
    if ENABLE_DEBUG_LOG or Graph.debugVerbose then
        print("[graph] " .. msg)
    end
end

local function countKeys(t)
    local n = 0
    for _ in pairs(t) do n = n + 1 end
    return n
end

--- Normalizes AccessLevel|boolean to AccessLevel
--- @param a AccessLevel|boolean|nil
--- @return AccessLevel
local function normalizeLevel(a, debug)
    if debug then
        dbg(("%s = %s"):format(tostring(a), debug))
    end
    if type(a) == "boolean" then
        return a and AccessibilityLevel.Normal or AccessibilityLevel.None
    else
        return a or AccessibilityLevel.None
    end
end

---Parses an edge string in format <from>__<flags>__<to> and returns the components
---@param edge any
---@return string from Edge source node
---@return string flags Edge flags
---@return string to Edge destination node
local function parseEdge(edge)
    local from, flags, to = edge:match("(.*)__(.*)__(.*)")
    if not from or not flags or not to then
        error(("Invalid edge format: %s. Expected format: <from>__<flags>__<to>"):format(edge))
    end
    return from, flags, to
end

--- Adds an edge to the graph
--- @param edge string Edge in format <from>__<flags>__<to>
--- @param rules RuleFn[][] Rules for the edge
function Graph:addEdge(edge, rules)
    local from, flags, to = parseEdge(edge)
    self.nodes[from] = true
    self.nodes[to] = true
    self.edges[edge] = { from = from, to = to, flags = flags, rules = rules }
    if not self.outAdj[from] then
        self.outAdj[from] = {}
    end
    table.insert(self.outAdj[from], edge)
    self.dirty = true
end

--- Checks if a node can be accessed from the spawn node
--- @param node string|nil Node to check
--- @param exclude string|nil Edge to exclude from the search
--- @return AccessLevel, boolean The access level of the node and if the calculation was finished
function Graph:reachable(m, node, exclude)
    m[self.spawn] = AccessibilityLevel.Normal
    dbg(("reachable(node=%s, exclude=%s) edges=%d nodes=%d")
        :format(tostring(node), tostring(exclude),
            countKeys(self.edges), countKeys(self.nodes)))
    local run = true
    local timeout = os.clock() + 0.02 -- 20ms time budget
    while run do
        run = false
        local promotions = 0
        Compute.count = Compute.count + 1
        if #Compute.q == 0 then
            Compute.q = { Graph.spawn }
            Compute.visited = {}
        end
        while #Compute.q > 0 do
            local current = Compute.q[1]
            if not Compute.visited[current] then
                if not Compute.currentEdges[1] then
                    local adj = self.outAdj[current]
                    Compute.currentEdges = adj and { table.unpack(adj) } or {}
                end
                while Compute.currentEdges[1] do
                    if os.clock() > timeout then
                        dbg(("reachable: timeout after %d passes, %d ruleEvals, %d reachableNodes")
                            :format(Compute.count, Compute.ruleEvals, promotions))
                        return normalizeLevel(m[node]), false
                    end
                    local e = Compute.currentEdges[1]
                    if e == exclude then
                        table.remove(Compute.currentEdges, 1)
                        goto continue
                    end
                    local edge = self.edges[e]
                    if normalizeLevel(m[edge.to]) >= AccessibilityLevel.Normal then
                        table.insert(Compute.q, edge.to)
                        table.remove(Compute.currentEdges, 1)
                        goto continue
                    end
                    local rules = edge.rules
                    local level = AccessibilityLevel.None
                    if rules then
                        Compute.ruleEvals = Compute.ruleEvals + 1
                        if not rules[1] or not rules[1][1] then
                            level = AccessibilityLevel.Normal
                        elseif normalizeLevel(rules[1][1]()) > AccessibilityLevel.None then
                            Compute.ruleEvals = Compute.ruleEvals + 1
                            level = AccessibilityLevel.Normal
                        elseif rules[2] and (not rules[2][1] or (normalizeLevel(rules[2][1]()) > AccessibilityLevel.None)) then
                            Compute.ruleEvals = Compute.ruleEvals + 1
                            level = AccessibilityLevel.SequenceBreak
                        elseif Graph.debugVerbose then
                            dbg(("  pass %d: %s = None via %s (from %s at %s)")
                                :format(Compute.count, edge.to, e,
                                    edge.from, levelName(m[edge.from])))
                        end
                    end
                    local ruleLevel = level -- rule's own result, pre-clamp
                    level = math.min(level, normalizeLevel(m[current]))
                    if level > normalizeLevel(m[edge.to]) then
                        m[edge.to] = level
                        run = true
                        promotions = promotions + 1
                        if Graph.debugVerbose then
                            dbg(("  pass %d: %s = %s via %s (from %s at %s)")
                                :format(Compute.count, edge.to, levelName(level), e,
                                    edge.from, levelName(m[edge.from])))
                        end
                    end
                    if level > AccessibilityLevel.None then
                        table.insert(Compute.q, edge.to)
                        -- debug overlay only: remember which incoming edge
                        -- granted access, for the click-info panel.
                        -- Skip while computing an avoid map: those promotions
                        -- hold only in the excluded world.
                        if m ~= Graph.avoidMaps[FULL] then
                            table.remove(Compute.currentEdges, 1)
                            goto continue
                        end
                        local via = Compute.accessVia[edge.to]
                        if not via then
                            via = {}
                            Compute.accessVia[edge.to] = via
                        end
                        via[e] = level
                        if ruleLevel > level then
                            -- the edge's conditions reach higher than the
                            -- path through the previous node allows
                            local vr = Compute.accessViaRule[edge.to]
                            if not vr then
                                vr = {}
                                Compute.accessViaRule[edge.to] = vr
                            end
                            vr[e] = ruleLevel
                        end
                    end
                    table.remove(Compute.currentEdges, 1)
                    ::continue::
                end
                Compute.visited[current] = true
            end
            table.remove(Compute.q, 1)
        end
    end

    Graph.accessVia = Compute.accessVia -- debug overlay: consumed by overlay.lua
    Graph.accessViaRule = Compute.accessViaRule -- debug overlay

    local reachable = 0
    for _, lvl in pairs(m) do
        if lvl > AccessibilityLevel.None then reachable = reachable + 1 end
    end
    dbg(("reachable done: passes=%d ruleEvals=%d reachableNodes=%d -> %s = %s")
        :format(Compute.count, Compute.ruleEvals, reachable, node,
            levelName(m[node] or AccessibilityLevel.None)))
    return normalizeLevel(m[node]), true
end


--- Returns the AccessLevel for accessibility from the spawn
---@param node string
---@param exclude string|nil
---@return AccessLevel
function canAccess(node, exclude)
    if not exclude then
        if not Graph.avoidMaps[FULL] then
            Graph.avoidMaps[FULL] = { [Graph.spawn] = AccessibilityLevel.Normal }
            Graph.levelCache = Graph.avoidMaps[FULL]
        end
        return Graph.avoidMaps[FULL][node] or AccessibilityLevel.None
    end
    if Graph.debugVerbose then
        dbg(("canAccess(node=%s, exclude=%s) edges=%d nodes=%d")
            :format(tostring(node), tostring(exclude),
                countKeys(Graph.edges), countKeys(Graph.nodes)))
    end
    if not Graph.avoidMaps[exclude] then
        Graph.avoidMaps[exclude] = { [Graph.spawn] = AccessibilityLevel.Normal }
        table.insert(Compute.mapQ, exclude)
    end
    -- pure cache lookup: the map may still be partial (pessimistic); the
    -- frame handler converges it via mapQ, then FULL is requeued
    return Graph.avoidMaps[exclude][node] or AccessibilityLevel.None
end

-- DEBUG: exposed for scripts/overlay.lua; remove when done
function GetGraphDebugRef()
    return Graph
end

function GraphInit()
	for edge, rules in pairs(ER_EDGES) do
        Graph:addEdge(edge, rules)
    end
end

-- toggling this hidden item makes PopTracker re-evaluate every location
-- rule that used canAccess (updateState -> updateLocations); without it the
-- location panels stay stale until the next real item event
local function bumpGraphState()
    if Tracker and Tracker.FindObjectForCode then
        local it = Tracker:FindObjectForCode("graphstate")
        if it then it.Active = not it.Active end
    end
end

local function startCompute()
    Compute.count = 0
    Compute.ruleEvals = 0
    Compute.accessVia = {} -- debug overlay: edge key -> granted level, per node
    Compute.accessViaRule = {} -- debug overlay: edge key -> rule's own level
    Compute.dirtyDuringRun = false
    for k in pairs(Graph.avoidMaps) do
        if k ~= FULL then Graph.avoidMaps[k] = nil end -- stale after items changed
    end
    Graph.avoidMaps[FULL] = { [Graph.spawn] = AccessibilityLevel.Normal }
    Graph.levelCache = Graph.avoidMaps[FULL] -- compat alias for overlay.lua
    Compute.mapQ = {FULL}
end

local function onFrame(seconds)
    if not Graph.dirty and #Compute.mapQ == 0 then return end
    if Graph.dirty and not Compute.running then
        startCompute()
        Compute.running = true
        Graph.dirty = false
    end
    if Graph.debugVerbose then
        dbg(("onFrame: map=%s running=%s q=%d visited=%d ruleEvals=%d count=%d")
            :format(Compute.mapQ[1], tostring(Compute.running), #Compute.q, countKeys(Compute.visited), Compute.ruleEvals, Compute.count))
    end
    if #Compute.mapQ > 0 then
        local m = Compute.mapQ[1]
        local _, fin = Graph:reachable(Graph.avoidMaps[m], FULL, m)
        if fin then
            table.remove(Compute.mapQ, 1)
            if #Compute.mapQ == 0 and m ~= FULL then
                -- avoid maps changed the picture: converge FULL once more
                table.insert(Compute.mapQ, FULL)
            end
        end
        if #Compute.mapQ == 0 then
            Compute.running = false
            Graph.dirty = Compute.dirtyDuringRun and true or false
            Compute.dirtyDuringRun = false
            bumpGraphState()
        end
    end
end

ScriptHost:AddOnFrameHandler("graph-compute", onFrame)
ScriptHost:AddWatchForCode("graph-compute", "*", function(code)
    if code and code:find("graphstate") then return end -- our own bump: no loop
    Graph.dirty = true
    if Compute.running then Compute.dirtyDuringRun = true end
end)

dbg(("loaded %d edges, %d nodes, spawn=%s")
    :format(countKeys(Graph.edges), countKeys(Graph.nodes), Graph.spawn))
