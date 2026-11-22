"""Parse ER_EDGES rule bodies from scripts/region_rules.lua into structured,
renderable JSON.

Each edge value is `{ { function() return EXPR end } , { function() ... end } }`
- group 1 is the primary (Normal) rule, group 2 the optional SequenceBreak rule.
Expressions are calls over hasAll/hasAny wrappers, string item codes, and
canAccess("Node", "edge") references. Output shape:

    { "From__FLAG__To": {"n": <expr>, "s": <expr-or-null>}, ... }

<expr> is one of:
    "item code"            quoted string / bareword leaf
    {"item": c, "count": n}   has("c") / hasAmount("c", n)
    {"access": "Node"}     canAccess("Node", ...)
    {"and": [...]}/{"or": [...]}   hasAll/hasAny (or and/or operators)
    {"fn": name, "args": [...]}    any other call (canDefeatX(), ...)
    {"raw": "..."}         body that could not be parsed
"""
import re


def tokenize(text):
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == '"':
            j = text.find('"', i + 1)
            if j == -1:
                break
            tokens.append(("str", text[i + 1:j]))
            i = j + 1
        elif c.isalnum() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(("name", text[i:j]))
            i = j
        elif c in "(){}[]":
            tokens.append((c, c))
            i += 1
        else:
            i += 1  # skip operators/punctuation
    return tokens


def parse_call(tokens, i):
    fn = tokens[i][1]
    i += 1
    if i >= len(tokens) or tokens[i][0] != "(":
        raise ValueError("expected ( after " + fn)
    i += 1
    args = []
    while i < len(tokens) and tokens[i][0] != ")":
        t = tokens[i]
        if t[0] in "{},":
            i += 1
        elif t[0] == "name" and i + 1 < len(tokens) and tokens[i + 1][0] == "(":
            node, i = parse_call(tokens, i)
            args.append(node)
        elif t[0] == "name":
            args.append(("num", t[1]) if t[1].isdigit() else ("str", t[1]))
            i += 1
        elif t[0] == "str":
            args.append(t)
            i += 1
        else:
            i += 1
    if i >= len(tokens):
        raise ValueError("unbalanced call")
    return (fn, args), i + 1


def parse_expr(tokens, i):
    t = tokens[i]
    if t[0] == "name" and i + 1 < len(tokens) and tokens[i + 1][0] == "(":
        node, i = parse_call(tokens, i)
    elif t[0] in ("str", "name"):  # bare leaf (true/false/bareword)
        node = ("str", t[1])
        i += 1
    else:
        raise ValueError("unexpected token " + str(t))
    while i < len(tokens) and tokens[i][0] == "name" \
            and tokens[i][1] in ("and", "or"):
        op = tokens[i][1]
        i += 1
        rhs, i = parse_expr(tokens, i)
        node = (op, [node, rhs])
    return node, i


def to_json(node):
    kind, val = node
    if kind in ("str", "num"):
        return val
    if kind in ("and", "or"):
        return {kind: [to_json(v) for v in val]}
    fn, args = kind, val

    def leaf(a):
        return to_json(a) if isinstance(a, tuple) else a

    if fn == "hasAll":
        return {"and": [leaf(a) for a in args]}
    if fn == "hasAny":
        return {"or": [leaf(a) for a in args]}
    if fn == "has":
        return {"item": leaf(args[0])} if args else {"fn": fn}
    if fn == "hasAmount":
        count = 1
        if len(args) > 1:
            try:
                count = int(args[1][1] if isinstance(args[1], tuple) else args[1])
            except (ValueError, TypeError):
                pass
        return {"item": leaf(args[0]), "count": count}
    if fn == "canAccess":
        return {"access": leaf(args[0])} if args else {"fn": fn}
    return {"fn": fn, "args": [leaf(a) for a in args]}


def parse_group(tokens, i):
    """Skip to `return`, parse the expression, skip to the closing `end`."""
    while i < len(tokens) and tokens[i] != ("name", "return"):
        i += 1
    if i >= len(tokens):
        raise ValueError("no return")
    i += 1
    node, i = parse_expr(tokens, i)
    while i < len(tokens) and tokens[i] != ("name", "end"):
        i += 1
    return node, i + 1


def parse_body(body):
    """Body of one edge -> (normal_expr_or_None, seqbreak_expr_or_None)."""
    if not body or not body.strip():
        return None, None
    tokens = tokenize(body)
    groups = []
    i = 0
    while i < len(tokens):
        if tokens[i] != ("name", "function"):
            i += 1
            continue
        try:
            node, i = parse_group(tokens, i)
        except ValueError:
            cleaned = re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", body)).strip()
            return None, {"raw": cleaned[:400]}
        groups.append(node)
    normal = groups[0] if len(groups) > 0 else None
    seq = groups[1] if len(groups) > 1 else None
    return normal, seq


def parse_edge_rules(path):
    """region_rules.lua -> {edge key: {"n": expr, "s": expr}}."""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return {}
    out = {}
    for m in re.finditer(r"([\w]+__[A-Za-z]+(?:_[AB])?__[\w]+)\s*=\s*\{", text):
        key = m.group(1)
        depth, i, n = 1, m.end(), len(text)
        while i < n and depth > 0:
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif text[i:i + 2] == "--":
                j = text.find("\n", i)
                i = j if j != -1 else n
                continue
            i += 1
        body = text[m.end():i - 1]
        normal, seq = parse_body(body)
        if normal is None and seq is None:
            out[key] = {"n": None, "s": None}
        else:
            out[key] = {"n": to_json(normal) if normal else None,
                        "s": to_json(seq) if seq else None}
    return out


# --- control.lua function parsing -------------------------------------------

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_OPEN = re.compile(r"\b(function|if|do|repeat)\b")
_BLOCK_CLOSE = re.compile(r"\b(end|until)\b")
_FUNC_HEAD = re.compile(r"\s*(?:local\s+)?function\s+(\w+)\s*\(")


def _extract_functions(text):
    """Yield (name, body) for each top-level `function NAME() ... end`.

    Depth tracking counts `function`/`if`/`do`/`repeat` as openers and
    `end`/`until` as closers; `for ... do` / `while ... do` are covered by
    counting only their `do` as the opener.
    """
    depth = 0
    start = None
    name = None
    i, n = 0, len(text)
    while i < n:
        line_end = text.find("\n", i)
        if line_end == -1:
            line_end = n
        line = _LINE_COMMENT.sub("", text[i:line_end])
        opens = len(_BLOCK_OPEN.findall(line))
        closes = len(_BLOCK_CLOSE.findall(line))
        if start is None:
            m = _FUNC_HEAD.match(line)
            if m and depth == 0 and opens > 0:
                start, name = i, m.group(1)
        elif depth + opens - closes <= 0:
            ends = list(re.finditer(r"\b(?:end|until)\b", text[i:line_end]))
            if ends:
                pos = i + ends[len(ends) - (depth + opens) - (-opens)].start() \
                    if False else i + ends[-1].start()
                yield name, text[start:pos].rstrip()
            else:
                yield name, text[start:line_end].rstrip()
            start, name, depth = None, None, 0
            i = line_end + 1
            continue
        depth += opens - closes
        i = line_end + 1


def parse_functions(path):
    """control.lua -> {name: {"expr": tree|None, "src": cleaned source}}.

    Bodies that are a single `return <expr>` statement are parsed into the
    same structured tree as edge rules; everything else keeps its raw source.
    """
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return {}
    out = {}
    for name, body in _extract_functions(text):
        body = _LINE_COMMENT.sub("", body)
        src = re.sub(r"\s+", " ", body).strip()
        expr_src = re.sub(r"^function\s+\w+\s*\(\s*\)\s*", "", src)
        try:
            tokens = tokenize(expr_src)
            if tokens and tokens[0] == ("name", "return"):
                node, i = parse_expr(tokens, 1)
                if i >= len(tokens):  # consumed the whole body
                    out[name] = {"expr": to_json(node), "src": src}
                    continue
        except (ValueError, IndexError):
            pass
        out[name] = {"expr": None, "src": src}
    return out
