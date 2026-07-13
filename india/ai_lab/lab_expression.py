"""
india/ai_lab/lab_expression.py — AST-constrained gate expression evaluator.

Replaces the earlier `eval(expr, {"__builtins__": {}}, ns)` gate evaluator, which was NOT a
robust config-language sandbox (removing builtins does not prevent arbitrary attribute walks,
data-model tricks, or accidental import-time side effects via imported classes in the namespace).

This module parses gate expressions into a Python AST and only permits:

- Numeric constants (int, float, bool) and NoneType
- Boolean OR / AND / NOT
- Comparison operators (==, !=, <, <=, >, >=)
- Arithmetic operators (+, -, *, /, //, %, **)
- Unary +/-/not
- Parentheses (implicit via AST structure)
- Attribute access from a whitelisted set of ROOT NAMES only (e.g., cand, n0, cand_stress, n0_stress).
- Attribute names may not start with underscore (dunder prevention).

Rejects (any of these → SafeExpressionError at parse time):

- Function calls
- Subscripting  a[b]
- Comprehensions / generator expressions
- Lambda / yield / await
- Import / exec / compile / class / def statements
- Any bare name not in the whitelist
- Attribute names starting with '_' (dunder or private)
- Attribute chains longer than 6 (arbitrary defense against deep walks)
- Any AST node not in ALLOWED_NODES

Usage:
    from india.ai_lab.lab_expression import compile_gate_expression
    checker = compile_gate_expression("cand.conf.ulcer - n0.conf.ulcer >= 1.0",
                                       allowed_roots=("cand", "n0", "cand_stress", "n0_stress"))
    result = checker({"cand": cand_ns, "n0": n0_ns, ...})   # bool
"""
from __future__ import annotations
import ast
from typing import Callable


class SafeExpressionError(ValueError):
    """Raised when a gate expression contains a disallowed AST node or reference."""


_ALLOWED_NODES = (
    ast.Expression, ast.Constant,
    ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Attribute, ast.Name, ast.Load,
)

_MAX_ATTR_DEPTH = 6


def _check_node(node: ast.AST, allowed_roots: tuple[str, ...]) -> None:
    """Recursively verify every node against the whitelist."""
    if not isinstance(node, _ALLOWED_NODES):
        raise SafeExpressionError(f"Disallowed AST node: {type(node).__name__}")

    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise SafeExpressionError(f"Disallowed attribute (underscore prefix): '{node.attr}'")
        # Walk down the chain: cand.conf.ulcer  → root must be a Name in whitelist.
        depth = 1
        cur = node.value
        while isinstance(cur, ast.Attribute):
            if cur.attr.startswith("_"):
                raise SafeExpressionError(f"Disallowed attribute (underscore prefix): '{cur.attr}'")
            depth += 1
            if depth > _MAX_ATTR_DEPTH:
                raise SafeExpressionError(f"Attribute chain exceeds max depth {_MAX_ATTR_DEPTH}")
            cur = cur.value
        if not isinstance(cur, ast.Name):
            raise SafeExpressionError(
                "Attribute must ultimately reference a whitelisted root Name")
        if cur.id not in allowed_roots:
            raise SafeExpressionError(
                f"Root name '{cur.id}' not in allowed roots {allowed_roots}")

    elif isinstance(node, ast.Name):
        # Bare names allowed ONLY if in whitelist AND used in a permissive load context.
        if node.id not in allowed_roots:
            raise SafeExpressionError(
                f"Bare name '{node.id}' not in allowed roots {allowed_roots}")

    elif isinstance(node, ast.Constant):
        if node.value is not None and not isinstance(node.value, (int, float, bool)):
            raise SafeExpressionError(
                f"Disallowed constant type: {type(node.value).__name__}")

    # Recurse into child nodes
    for child in ast.iter_child_nodes(node):
        _check_node(child, allowed_roots)


def compile_gate_expression(expr: str, allowed_roots: tuple[str, ...]) -> Callable[[dict], bool]:
    """Parse + validate a gate expression string. Returns a callable(namespace_dict) → bool.

    Raises SafeExpressionError if the expression contains anything outside the whitelist.
    The returned callable evaluates the expression against a dict {root_name: object}, using
    Python's normal attribute access. It does not call eval() on the raw string — it walks the
    parsed AST tree and dispatches recursively.
    """
    if not isinstance(expr, str) or not expr.strip():
        raise SafeExpressionError("Gate expression must be a non-empty string")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise SafeExpressionError(f"Gate expression syntax error: {e}") from e

    _check_node(tree, allowed_roots)

    # Compile the whitelisted tree; runtime is Python's normal evaluation of AST-produced code
    # but only via a manual walker (no exec/eval on the string).
    def _eval(node: ast.AST, ns: dict):
        if isinstance(node, ast.Expression):
            return _eval(node.body, ns)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in ns:
                raise SafeExpressionError(f"Runtime: name '{node.id}' not in namespace")
            return ns[node.id]
        if isinstance(node, ast.Attribute):
            base = _eval(node.value, ns)
            return getattr(base, node.attr)
        if isinstance(node, ast.UnaryOp):
            v = _eval(node.operand, ns)
            if isinstance(node.op, ast.USub):   return -v
            if isinstance(node.op, ast.UAdd):   return +v
            if isinstance(node.op, ast.Not):    return not v
        if isinstance(node, ast.BinOp):
            l, r = _eval(node.left, ns), _eval(node.right, ns)
            op = node.op
            if isinstance(op, ast.Add):        return l + r
            if isinstance(op, ast.Sub):        return l - r
            if isinstance(op, ast.Mult):       return l * r
            if isinstance(op, ast.Div):        return l / r
            if isinstance(op, ast.FloorDiv):   return l // r
            if isinstance(op, ast.Mod):        return l % r
            if isinstance(op, ast.Pow):        return l ** r
        if isinstance(node, ast.BoolOp):
            vs = [_eval(v, ns) for v in node.values]
            if isinstance(node.op, ast.And): return all(vs)
            if isinstance(node.op, ast.Or):  return any(vs)
        if isinstance(node, ast.Compare):
            left = _eval(node.left, ns)
            result = True
            for op, comp in zip(node.ops, node.comparators):
                right = _eval(comp, ns)
                if isinstance(op, ast.Eq):    ok = left == right
                elif isinstance(op, ast.NotEq): ok = left != right
                elif isinstance(op, ast.Lt):    ok = left < right
                elif isinstance(op, ast.LtE):   ok = left <= right
                elif isinstance(op, ast.Gt):    ok = left > right
                elif isinstance(op, ast.GtE):   ok = left >= right
                else:
                    raise SafeExpressionError(f"Disallowed compare op: {type(op).__name__}")
                result = result and ok
                left = right
            return result
        raise SafeExpressionError(f"Runtime: unhandled node {type(node).__name__}")

    def _run(ns: dict) -> bool:
        return bool(_eval(tree, ns))

    return _run
