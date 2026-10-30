"""Formula language for template lines.

Port of the prototype's `BomEngine` (tokenizer → recursive-descent parser → AST → evaluator), kept
byte-compatible with the formulas already written in BOM_Check.xlsx and the prototype:

    (Returns_SS_in * LOC_of_SS_Ft * 1.2) / 12
    ((Surface_Area * 2) + ...) * 22 * 0.42 if Finish == "Matt" else 0
    IF(Number_of_Connections > 10, 2, 1)
    QTY("Power Supply") * 1.5            # quantity of other lines with that cost tag
    =COST("Paint") * 0.2                 # unit-cost formula: 20% of the other Paint lines

Grammar (lowest to highest precedence):
    ternary := or ( 'if' or 'else' ternary )?
    or      := and ( 'or' and )*
    and     := not ( 'and' not )*
    not     := 'not' not | cmp
    cmp     := add ( ('=='|'!='|'<'|'>'|'<='|'>=') add )?
    add     := mul ( ('+'|'-') mul )*
    mul     := unary ( ('*'|'/') unary )*
    unary   := ('-'|'+') unary | primary
    primary := number | string | '(' ternary ')' | IDENT '(' args ')' | IDENT
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

Number = float


class FormulaError(ValueError):
    """Raised for any syntax or evaluation problem. The message is user-facing."""


# ----------------------------------------------------------------------------- tokens


@dataclass(frozen=True)
class Tok:
    kind: str  # num | id | kw | str | op
    value: Any


_NUM = re.compile(r"(\d+\.?\d*|\.\d+)")
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KEYWORDS = {"if", "else", "and", "or", "not"}
_TWO_CHAR = {"==", "!=", "<=", ">=", "<>"}
_ONE_CHAR = set("+-*/(),<>=")
_QUOTES = {'"': '"', "'": "'", "“": "”", "”": "”"}


def tokenize(src: str) -> list[Tok]:
    out: list[Tok] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        m = _NUM.match(src, i)
        if m:
            out.append(Tok("num", float(m.group(1))))
            i = m.end()
            continue
        m = _ID.match(src, i)
        if m:
            word = m.group(0)
            lw = word.lower()
            calls_fn = re.match(r"\s*\(", src[m.end() :]) is not None
            if lw in _KEYWORDS and not (lw == "if" and calls_fn):
                out.append(Tok("kw", lw))
            else:
                out.append(Tok("id", word))
            i = m.end()
            continue
        if c in _QUOTES:
            close = _QUOTES[c]
            j = i + 1
            while j < n and src[j] != close and not (close == "”" and src[j] == '"'):
                j += 1
            if j >= n:
                raise FormulaError("A text value is missing its closing quote")
            out.append(Tok("str", src[i + 1 : j]))
            i = j + 1
            continue
        two = src[i : i + 2]
        if two in _TWO_CHAR:
            out.append(Tok("op", "!=" if two == "<>" else two))
            i += 2
            continue
        if c in _ONE_CHAR:
            out.append(Tok("op", "==" if c == "=" else c))
            i += 1
            continue
        raise FormulaError(f"Unexpected character “{c}”")
    return out


# ----------------------------------------------------------------------------- AST


@dataclass(frozen=True)
class Node:
    t: str  # num | str | var | neg | bin | cmp | and | or | not | if | fn
    v: Any = None  # literal value, operator, var/function name
    kids: tuple["Node", ...] = ()


def _node(t: str, v: Any = None, *kids: Node) -> Node:
    return Node(t, v, tuple(kids))


class _Parser:
    def __init__(self, toks: list[Tok]):
        self.tk = toks
        self.p = 0

    def peek(self) -> Tok | None:
        return self.tk[self.p] if self.p < len(self.tk) else None

    def is_op(self, v: str) -> bool:
        t = self.peek()
        return t is not None and t.kind == "op" and t.value == v

    def is_kw(self, v: str) -> bool:
        t = self.peek()
        return t is not None and t.kind == "kw" and t.value == v

    def expect(self, v: str) -> None:
        if not self.is_op(v):
            raise FormulaError(f"Expected “{v}”")
        self.p += 1

    def ternary(self) -> Node:
        a = self.or_()
        if self.is_kw("if"):
            self.p += 1
            c = self.or_()
            if not self.is_kw("else"):
                raise FormulaError("“if” needs a matching “else”")
            self.p += 1
            b = self.ternary()
            return _node("if", None, c, a, b)
        return a

    def or_(self) -> Node:
        left = self.and_()
        while self.is_kw("or"):
            self.p += 1
            left = _node("or", None, left, self.and_())
        return left

    def and_(self) -> Node:
        left = self.not_()
        while self.is_kw("and"):
            self.p += 1
            left = _node("and", None, left, self.not_())
        return left

    def not_(self) -> Node:
        if self.is_kw("not"):
            self.p += 1
            return _node("not", None, self.not_())
        return self.cmp()

    def cmp(self) -> Node:
        left = self.add()
        t = self.peek()
        if t and t.kind == "op" and t.value in ("==", "!=", "<", ">", "<=", ">="):
            self.p += 1
            return _node("cmp", t.value, left, self.add())
        return left

    def add(self) -> Node:
        left = self.mul()
        while self.is_op("+") or self.is_op("-"):
            op = self.tk[self.p].value
            self.p += 1
            left = _node("bin", op, left, self.mul())
        return left

    def mul(self) -> Node:
        left = self.unary()
        while self.is_op("*") or self.is_op("/"):
            op = self.tk[self.p].value
            self.p += 1
            left = _node("bin", op, left, self.unary())
        return left

    def unary(self) -> Node:
        if self.is_op("-"):
            self.p += 1
            return _node("neg", None, self.unary())
        if self.is_op("+"):
            self.p += 1
            return self.unary()
        return self.primary()

    def primary(self) -> Node:
        t = self.peek()
        if t is None:
            raise FormulaError("The formula ends too early")
        if t.kind == "num":
            self.p += 1
            return _node("num", t.value)
        if t.kind == "str":
            self.p += 1
            return _node("str", t.value)
        if self.is_op("("):
            self.p += 1
            e = self.ternary()
            self.expect(")")
            return e
        if t.kind == "id":
            self.p += 1
            if self.is_op("("):
                self.p += 1
                args: list[Node] = []
                if not self.is_op(")"):
                    args.append(self.ternary())
                    while self.is_op(","):
                        self.p += 1
                        args.append(self.ternary())
                self.expect(")")
                return _node("fn", t.value.upper(), *args)
            return _node("var", t.value)
        raise FormulaError(f"Unexpected “{t.value}”")


def parse(src: str | None) -> Node:
    s = ("" if src is None else str(src)).strip()
    if s.startswith("="):
        s = s[1:]
    if s == "":
        return _node("num", 0.0)
    parser = _Parser(tokenize(s))
    ast = parser.ternary()
    if parser.p < len(parser.tk):
        bad = parser.tk[parser.p].value
        raise FormulaError(f"Unexpected “{bad}”. Check for a missing + - * or /")
    return ast


# ----------------------------------------------------------------------------- evaluation

_FN_ARITY: dict[str, tuple[int, int]] = {
    "QTY": (1, 1),
    "COST": (1, 1),
    "IF": (3, 3),
    "MIN": (1, 99),
    "MAX": (1, 99),
    "ROUND": (1, 2),
    "ROUNDUP": (1, 2),
    "CEILING": (1, 1),
    "FLOOR": (1, 1),
    "ABS": (1, 1),
}


def _num(v: Any) -> Number:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    raise FormulaError(f"Text “{v}” was used in a calculation")


def _truthy(v: Any) -> bool:
    if isinstance(v, str):
        return v != ""
    return bool(v)


def _norm_str(s: Any) -> str:
    return str(s).strip().lower()


def _round_half_up(x: float, d: int) -> float:
    f = 10**d
    return math.floor(x * f + 0.5) / f if x >= 0 else -math.floor(-x * f + 0.5) / f


@dataclass
class Context:
    """Cross-line lookups available to a formula while a template is being calculated."""

    tag_qty: Callable[[str], Number] | None = None
    tag_cost: Callable[[str], Number] | None = None


def evaluate(ast: Node, vars: dict[str, Any], ctx: Context | None = None) -> Any:
    t = ast.t
    if t in ("num", "str"):
        return ast.v
    if t == "var":
        key = ast.v.lower()
        if key not in vars:
            raise FormulaError(f"Unknown input “{ast.v}”")
        return vars[key]
    if t == "neg":
        return -_num(evaluate(ast.kids[0], vars, ctx))
    if t == "bin":
        left = _num(evaluate(ast.kids[0], vars, ctx))
        right = _num(evaluate(ast.kids[1], vars, ctx))
        op = ast.v
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if right == 0:
            raise FormulaError("Division by zero")
        return left / right
    if t == "cmp":
        left = evaluate(ast.kids[0], vars, ctx)
        right = evaluate(ast.kids[1], vars, ctx)
        op = ast.v
        if isinstance(left, str) or isinstance(right, str):
            ls, rs = _norm_str(left), _norm_str(right)
            if op == "==":
                return ls == rs
            if op == "!=":
                return ls != rs
            raise FormulaError("Text can only be compared with == or !=")
        ln, rn = _num(left), _num(right)
        return {
            "==": ln == rn,
            "!=": ln != rn,
            "<": ln < rn,
            ">": ln > rn,
            "<=": ln <= rn,
            ">=": ln >= rn,
        }[op]
    if t == "and":
        return _truthy(evaluate(ast.kids[0], vars, ctx)) and _truthy(evaluate(ast.kids[1], vars, ctx))
    if t == "or":
        return _truthy(evaluate(ast.kids[0], vars, ctx)) or _truthy(evaluate(ast.kids[1], vars, ctx))
    if t == "not":
        return not _truthy(evaluate(ast.kids[0], vars, ctx))
    if t == "if":
        c, a, b = ast.kids
        return evaluate(a, vars, ctx) if _truthy(evaluate(c, vars, ctx)) else evaluate(b, vars, ctx)
    if t == "fn":
        name = ast.v
        if name not in _FN_ARITY:
            raise FormulaError(f"Unknown function “{name}”")
        lo, hi = _FN_ARITY[name]
        if not (lo <= len(ast.kids) <= hi):
            raise FormulaError(f"{name} has the wrong number of values")
        if name == "IF":
            c, a, b = ast.kids
            return evaluate(a, vars, ctx) if _truthy(evaluate(c, vars, ctx)) else evaluate(b, vars, ctx)
        if name in ("COST", "QTY"):
            arg = ast.kids[0]
            if arg.t != "str":
                example = 'COST("Paint")' if name == "COST" else 'QTY("Power Supply")'
                raise FormulaError(f"{name} needs a cost tag in quotes, like {example}")
            fn = (ctx.tag_cost if name == "COST" else ctx.tag_qty) if ctx else None
            if fn is None:
                raise FormulaError(f"{name} works only in a material’s formula")
            return fn(arg.v)
        args = [evaluate(k, vars, ctx) for k in ast.kids]
        if name == "MIN":
            return min(_num(a) for a in args)
        if name == "MAX":
            return max(_num(a) for a in args)
        if name == "ROUND":
            return _round_half_up(_num(args[0]), int(_num(args[1])) if len(args) > 1 else 0)
        if name == "ROUNDUP":
            d = int(_num(args[1])) if len(args) > 1 else 0
            f = 10**d
            return math.ceil(_num(args[0]) * f - 1e-9) / f
        if name == "CEILING":
            return float(math.ceil(_num(args[0]) - 1e-9))
        if name == "FLOOR":
            return float(math.floor(_num(args[0])))
        if name == "ABS":
            return abs(_num(args[0]))
    raise FormulaError("Bad formula")


# ----------------------------------------------------------------------------- static analysis


def _walk(ast: Node):
    yield ast
    for k in ast.kids:
        yield from _walk(k)


def variables_used(ast: Node) -> set[str]:
    return {n.v for n in _walk(ast) if n.t == "var"}


def norm_tag(tag: str | None) -> str:
    """Tags compare ignoring case, spaces and plurals: "Wire" == "Wires", "Power Supplies" == "Power Supply"."""
    k = re.sub(r"\s+", " ", ("" if tag is None else str(tag)).strip().lower())
    if k.endswith("ies"):
        k = k[:-3] + "y"
    elif k.endswith("s"):
        k = k[:-1]
    return k


def _tags_used(ast: Node, fn_name: str) -> set[str]:
    out: set[str] = set()
    for n in _walk(ast):
        if n.t == "fn" and n.v == fn_name:
            if len(n.kids) != 1 or n.kids[0].t != "str":
                example = 'COST("Paint")' if fn_name == "COST" else 'QTY("Power Supply")'
                raise FormulaError(f"{fn_name} needs one cost tag in quotes, like {example}")
            out.add(norm_tag(n.kids[0].v))
    return out


def qty_tags_used(ast: Node) -> set[str]:
    return _tags_used(ast, "QTY")


def cost_tags_used(ast: Node) -> set[str]:
    return _tags_used(ast, "COST")


_PLAIN_NUMBER = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)$")


def is_cost_formula(v: Any) -> bool:
    """A unit cost is either a number or a formula such as `=COST("Paint") * 0.1`."""
    if v is None or isinstance(v, (int, float)):
        return False
    t = str(v).strip()
    return t != "" and not _PLAIN_NUMBER.match(t.replace(",", ""))


def check_formula(formula: str | None, param_names: list[str]) -> str | None:
    """Return None when the formula is valid against these parameter names, else a user-facing message."""
    try:
        ast = parse(formula)
        qty_tags_used(ast)
        cost_tags_used(ast)
        known = {p.strip().lower() for p in param_names}
        for v in variables_used(ast):
            if v.lower() not in known:
                return f"Unknown input “{v}”"
        return None
    except FormulaError as e:
        return str(e)
    except Exception:  # pragma: no cover - defensive
        return "Bad formula"


# ----------------------------------------------------------------------------- template calculation


@dataclass
class LineSpec:
    """What the calculator needs to know about one template line (ORM-agnostic)."""

    key: Any  # caller's identifier for the line (ORM id or index)
    name: str
    qty_formula: str | None
    unit_cost: float | str | None  # number, or a formula string
    cost_tag: str | None = None
    uom: str | None = None
    usage: str | None = None
    work_centre: str | None = None
    wastage_pct: float | None = None


@dataclass
class ParamSpec:
    param_name: str
    input_type: str = "number"  # number | select
    options: list[str] = field(default_factory=list)


@dataclass
class LineResult:
    key: Any
    name: str
    qty_auto: float
    qty_final: float
    unit_cost: float
    unit_cost_is_formula: bool
    total: float
    cost_tag: str | None
    error: str | None
    overridden: bool = False


@dataclass
class CalcResult:
    lines: list[LineResult]
    input_errors: dict[str, str]
    by_tag: dict[str, float]
    base_total: float

    @property
    def has_errors(self) -> bool:
        return bool(self.input_errors) or any(ln.error for ln in self.lines)


def build_vars(params: list[ParamSpec], raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Turn raw input values into the variable map (keys lower-cased). Blank numbers count as 0."""
    vars: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for p in params:
        key = p.param_name.strip()
        v = raw.get(key)
        if p.input_type == "select":
            vars[key.lower()] = (p.options[0] if p.options else "") if v in (None, "") else str(v)
            continue
        if v in (None, ""):
            vars[key.lower()] = 0.0
            continue
        try:
            n = float(v) if isinstance(v, (int, float)) else float(str(v).replace(",", ""))
        except ValueError:
            errors[key] = "Enter a number"
            vars[key.lower()] = 0.0
            continue
        if math.isnan(n) or math.isinf(n):
            errors[key] = "Enter a number"
            vars[key.lower()] = 0.0
        elif n < 0:
            errors[key] = "Can’t be negative"
            vars[key.lower()] = 0.0
        else:
            vars[key.lower()] = n
    return vars, errors


def calculate(
    params: list[ParamSpec],
    lines: list[LineSpec],
    raw_inputs: dict[str, Any],
    extra_vars: dict[str, Any] | None = None,
    overrides: dict[Any, float] | None = None,
    extra_lines: list[tuple[str, float, float]] | None = None,
) -> CalcResult:
    """Evaluate every line's quantity (and unit-cost formula) in dependency order.

    overrides: {line.key: typed quantity} — a typed quantity is what other lines see through QTY().
    extra_lines: [(cost_tag, qty, unit_cost)] ad-hoc lines that also count toward QTY()/COST().
    """
    vars, input_errors = build_vars(params, raw_inputs)
    merged: dict[str, Any] = {k.lower(): v for k, v in (extra_vars or {}).items()}
    merged.update(vars)  # a template input with the same name wins
    overrides = overrides or {}
    n = len(lines)
    tag_of = [norm_tag(ln.cost_tag) for ln in lines]

    prepped: list[dict[str, Any]] = []
    for ln in lines:
        try:
            ast = parse(ln.qty_formula)
            cost_ast = parse(ln.unit_cost) if is_cost_formula(ln.unit_cost) else None
            qty_deps = qty_tags_used(ast) | (qty_tags_used(cost_ast) if cost_ast else set())
            cost_deps = cost_tags_used(ast) | (cost_tags_used(cost_ast) if cost_ast else set())
            prepped.append({"ast": ast, "cost_ast": cost_ast, "qty_deps": qty_deps, "deps": qty_deps | cost_deps})
        except FormulaError as e:
            prepped.append({"err": str(e)})

    auto = [0.0] * n
    eff = [0.0] * n
    unit = [0.0] * n
    eff_cost = [0.0] * n
    err: list[str | None] = [None] * n
    done = [False] * n

    extra_by_tag: dict[str, float] = {}
    extra_cost_by_tag: dict[str, float] = {}
    for tag, q, c in extra_lines or []:
        if not q or q <= 0:
            continue
        k = norm_tag(tag)
        extra_by_tag[k] = extra_by_tag.get(k, 0.0) + q
        if c and c > 0:
            extra_cost_by_tag[k] = extra_cost_by_tag.get(k, 0.0) + q * c

    def plain_unit(i: int) -> float:
        uc = lines[i].unit_cost
        if uc is None or is_cost_formula(uc):
            return 0.0
        try:
            return float(str(uc).replace(",", "")) if isinstance(uc, str) else float(uc)
        except ValueError:
            return 0.0

    def typed(i: int) -> float | None:
        v = overrides.get(lines[i].key)
        if v is None:
            return None
        try:
            q = float(v)
        except (TypeError, ValueError):
            return None
        return None if (math.isnan(q) or q < 0) else q

    def ctx_for(self_i: int) -> Context:
        def tag_qty(t: str) -> float:
            k = norm_tag(t)
            return extra_by_tag.get(k, 0.0) + sum(eff[j] for j in range(n) if tag_of[j] == k)

        def tag_cost(t: str) -> float:
            k = norm_tag(t)
            # the line itself is left out, so a paint-misc line can be a % of the *other* paint lines
            return extra_cost_by_tag.get(k, 0.0) + sum(eff_cost[j] for j in range(n) if j != self_i and tag_of[j] == k)

        return Context(tag_qty=tag_qty, tag_cost=tag_cost)

    def finish(i: int, q: float, e: str | None, u: float) -> None:
        auto[i] = q
        err[i] = e
        t = typed(i)
        eff[i] = t if t is not None else q
        unit[i] = u or 0.0
        eff_cost[i] = eff[i] * unit[i]
        done[i] = True

    progress = True
    while progress:
        progress = False
        for i in range(n):
            if done[i]:
                continue
            p = prepped[i]
            if "err" in p:
                finish(i, 0.0, p["err"], 0.0)
                progress = True
                continue
            if tag_of[i] and tag_of[i] in p["qty_deps"]:
                finish(i, 0.0, f'QTY("{lines[i].cost_tag}") can’t be used in a line that has that cost tag itself', 0.0)
                progress = True
                continue
            if any(j != i and not done[j] and tag_of[j] in p["deps"] for j in range(n)):
                continue  # wait for dependencies
            ctx = ctx_for(i)
            try:
                q = _num(evaluate(p["ast"], merged, ctx))
                if math.isnan(q) or math.isinf(q):
                    raise FormulaError("Result is not a number")
                u = plain_unit(i)
                if p["cost_ast"] is not None:
                    u = _num(evaluate(p["cost_ast"], merged, ctx))
                    if math.isnan(u) or math.isinf(u):
                        raise FormulaError("The unit cost formula doesn’t give a number")
                finish(i, q, None, u)
            except FormulaError as e:
                finish(i, 0.0, str(e), 0.0)
            progress = True

    for i in range(n):
        if not done[i]:
            finish(i, 0.0, "These QTY() or COST() formulas depend on each other in a circle", 0.0)

    results: list[LineResult] = []
    by_tag: dict[str, float] = {}
    for i, ln in enumerate(lines):
        is_formula = prepped[i].get("cost_ast") is not None
        total = eff[i] * unit[i]
        results.append(
            LineResult(
                key=ln.key,
                name=ln.name,
                qty_auto=auto[i],
                qty_final=eff[i],
                unit_cost=unit[i],
                unit_cost_is_formula=is_formula,
                total=total,
                cost_tag=ln.cost_tag,
                error=err[i],
                overridden=typed(i) is not None,
            )
        )
        by_tag[ln.cost_tag or "Other"] = by_tag.get(ln.cost_tag or "Other", 0.0) + total
    return CalcResult(lines=results, input_errors=input_errors, by_tag=by_tag, base_total=sum(r.total for r in results))


def order_vars(length_in: float | None, width_in: float | None) -> dict[str, float]:
    """Variables every template gets for free from the order's size."""
    ln = float(length_in or 0)
    w = float(width_in or 0)
    ln = ln if ln > 0 else 0.0
    w = w if w > 0 else 0.0
    return {"Length_in": ln, "Width_in": w, "Area_sqft": ln * w / 144.0}
