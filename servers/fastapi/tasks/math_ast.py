"""JSON Math AST: ASCII → AST → TeX / OMML (dual-emit compile targets)."""

from __future__ import annotations

import html
import re
from typing import Any

_GREEK = {
    "alpha": ("\\alpha", "α"),
    "beta": ("\\beta", "β"),
    "gamma": ("\\gamma", "γ"),
    "delta": ("\\delta", "δ"),
    "epsilon": ("\\epsilon", "ε"),
    "zeta": ("\\zeta", "ζ"),
    "eta": ("\\eta", "η"),
    "theta": ("\\theta", "θ"),
    "iota": ("\\iota", "ι"),
    "kappa": ("\\kappa", "κ"),
    "lambda": ("\\lambda", "λ"),
    "mu": ("\\mu", "μ"),
    "nu": ("\\nu", "ν"),
    "xi": ("\\xi", "ξ"),
    "pi": ("\\pi", "π"),
    "rho": ("\\rho", "ρ"),
    "sigma": ("\\sigma", "σ"),
    "tau": ("\\tau", "τ"),
    "phi": ("\\phi", "φ"),
    "chi": ("\\chi", "χ"),
    "psi": ("\\psi", "ψ"),
    "omega": ("\\omega", "ω"),
    "Alpha": ("\\Alpha", "Α"),
    "Beta": ("\\Beta", "Β"),
    "Gamma": ("\\Gamma", "Γ"),
    "Delta": ("\\Delta", "Δ"),
    "Theta": ("\\Theta", "Θ"),
    "Lambda": ("\\Lambda", "Λ"),
    "Pi": ("\\Pi", "Π"),
    "Sigma": ("\\Sigma", "Σ"),
    "Phi": ("\\Phi", "Φ"),
    "Psi": ("\\Psi", "Ψ"),
    "Omega": ("\\Omega", "Ω"),
}

_OP_TEX = {
    "*": "\\cdot ",
    "/": "/",
    "+": "+",
    "-": "-",
    "=": "=",
    "~=": "\\approx ",
    "≈": "\\approx ",
    "<=": "\\leq ",
    ">=": "\\geq ",
    "!=": "\\neq ",
}

_OP_OMML = {
    "*": "⋅",
    "/": "/",
    "+": "+",
    "-": "−",
    "=": "=",
    "~=": "≈",
    "≈": "≈",
    "<=": "≤",
    ">=": "≥",
    "!=": "≠",
}


class MathAstError(ValueError):
    """Raised when ASCII cannot be parsed into a Math AST."""


def _node(type_: str, **kwargs: Any) -> dict[str, Any]:
    out = {"type": type_}
    out.update(kwargs)
    return out


def ascii_to_ast(raw: str) -> dict[str, Any] | None:
    """Parse Strategist-dialect ASCII math into a JSON Math AST.

    Returns None on empty/unparseable input (fail-soft).
    """
    text = str(raw or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    try:
        parser = _Parser(text)
        tree = parser.parse_expression()
        parser.skip_ws()
        if parser.pos < len(parser.s):
            # Trailing junk — wrap remainder as opaque text run if mostly ok
            rest = parser.s[parser.pos :].strip()
            if rest and tree is not None:
                tree = _node(
                    "op",
                    op=" ",
                    left=tree,
                    right=_node("sym", name=rest),
                )
        return tree
    except MathAstError:
        return None
    except Exception:
        return None


def ast_to_tex(ast: dict[str, Any] | None) -> str:
    """Compile Math AST → TeX for KaTeX."""
    if not isinstance(ast, dict):
        return ""
    return _tex(ast).strip()


def ast_to_omml(ast: dict[str, Any] | None) -> str:
    """Compile Math AST → OMML fragment inside ``m:oMath`` (no outer wrapper)."""
    if not isinstance(ast, dict):
        return ""
    inner = _omml(ast)
    return f"<m:oMath>{inner}</m:oMath>"


def ast_to_omml_para(ast: dict[str, Any] | None) -> str:
    """Full OMML paragraph for DrawingML text body."""
    omath = ast_to_omml(ast)
    if not omath:
        return ""
    return (
        "<m:oMathPara>"
        '<m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        f"{omath}"
        "</m:oMathPara>"
    )


_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SUP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")


def ast_to_unicode(ast: dict[str, Any] | None) -> str:
    """Readable Unicode math for preview when the SVG worker is unavailable."""
    if not isinstance(ast, dict):
        return ""
    return _unicode(ast).strip()


def _unicode(n: dict[str, Any]) -> str:
    t = str(n.get("type") or "")
    if t == "num":
        return str(n.get("value") or "")
    if t == "sym":
        name = str(n.get("name") or "")
        if name in _GREEK:
            return _GREEK[name][1]
        return name
    if t == "group":
        return "(" + _unicode(n["expr"]) + ")"
    if t == "sub":
        base = _unicode(n["base"])
        script = _unicode(n["script"])
        mapped = script.translate(_SUB)
        if mapped != script or script.isdigit():
            return base + (mapped if mapped else script)
        return f"{base}_{script}"
    if t == "sup":
        base = _unicode(n["base"])
        script = _unicode(n["script"])
        mapped = script.translate(_SUP)
        if mapped != script or script.isdigit():
            return base + (mapped if mapped else script)
        return f"{base}^{script}"
    if t == "frac":
        return f"({_unicode(n['num'])})/({_unicode(n['den'])})"
    if t == "eq":
        return f"{_unicode(n['lhs'])} = {_unicode(n['rhs'])}"
    if t == "approx":
        return f"{_unicode(n['lhs'])} ≈ {_unicode(n['rhs'])}"
    if t == "op":
        op = str(n.get("op") or "")
        left = _unicode(n["left"]) if isinstance(n.get("left"), dict) else ""
        right = _unicode(n["right"]) if isinstance(n.get("right"), dict) else ""
        if op == "/":
            return f"({left})/({right})"
        if op == " ":
            return f"{left} {right}"
        return f"{left}{_OP_OMML.get(op, op)}{right}"
    if t == "neg":
        return "−" + _unicode(n["expr"])
    return ""


# --- TeX ---


def _tex(n: dict[str, Any]) -> str:
    t = str(n.get("type") or "")
    if t == "num":
        return str(n.get("value") or "")
    if t == "sym":
        name = str(n.get("name") or "")
        if name in _GREEK:
            return _GREEK[name][0]
        return name.replace("_", "\\_")
    if t == "group":
        return "{" + _tex(n["expr"]) + "}"
    if t == "sub":
        return "{" + _tex(n["base"]) + "}_{" + _tex(n["script"]) + "}"
    if t == "sup":
        return "{" + _tex(n["base"]) + "}^{" + _tex(n["script"]) + "}"
    if t == "frac":
        return "\\frac{" + _tex(n["num"]) + "}{" + _tex(n["den"]) + "}"
    if t == "eq":
        return _tex(n["lhs"]) + " = " + _tex(n["rhs"])
    if t == "approx":
        return _tex(n["lhs"]) + " \\approx " + _tex(n["rhs"])
    if t == "op":
        op = str(n.get("op") or "")
        left = _tex(n["left"]) if isinstance(n.get("left"), dict) else ""
        right = _tex(n["right"]) if isinstance(n.get("right"), dict) else ""
        tex_op = _OP_TEX.get(op, op)
        if op == " ":
            return f"{left}\\ {right}"
        if op == "/":
            # Prefer fraction for simple division
            if isinstance(n.get("left"), dict) and isinstance(n.get("right"), dict):
                return "\\frac{" + left + "}{" + right + "}"
        return f"{left}{tex_op}{right}"
    if t == "neg":
        return "-" + _tex(n["expr"])
    return ""


# --- OMML ---


def _esc_t(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _omml_run(text: str, *, italic: bool = False) -> str:
    sty = '<m:sty m:val="i"/>' if italic else ""
    return (
        f"<m:r><m:rPr>{sty}</m:rPr>"
        f'<m:t xml:space="preserve">{_esc_t(text)}</m:t></m:r>'
    )


def _omml(n: dict[str, Any]) -> str:
    t = str(n.get("type") or "")
    if t == "num":
        return _omml_run(str(n.get("value") or ""))
    if t == "sym":
        name = str(n.get("name") or "")
        if name in _GREEK:
            return _omml_run(_GREEK[name][1], italic=True)
        # Multi-letter identifiers stay upright; single letters italic.
        return _omml_run(name, italic=len(name) == 1)
    if t == "group":
        return (
            _omml_run("(")
            + _omml(n["expr"])
            + _omml_run(")")
        )
    if t == "sub":
        return (
            "<m:sSub>"
            f"<m:e>{_omml(n['base'])}</m:e>"
            f"<m:sub>{_omml(n['script'])}</m:sub>"
            "</m:sSub>"
        )
    if t == "sup":
        return (
            "<m:sSup>"
            f"<m:e>{_omml(n['base'])}</m:e>"
            f"<m:sup>{_omml(n['script'])}</m:sup>"
            "</m:sSup>"
        )
    if t == "frac":
        return (
            "<m:f>"
            f"<m:num>{_omml(n['num'])}</m:num>"
            f"<m:den>{_omml(n['den'])}</m:den>"
            "</m:f>"
        )
    if t == "eq":
        return _omml(n["lhs"]) + _omml_run("=") + _omml(n["rhs"])
    if t == "approx":
        return _omml(n["lhs"]) + _omml_run("≈") + _omml(n["rhs"])
    if t == "op":
        op = str(n.get("op") or "")
        if op == "/" and isinstance(n.get("left"), dict) and isinstance(n.get("right"), dict):
            return (
                "<m:f>"
                f"<m:num>{_omml(n['left'])}</m:num>"
                f"<m:den>{_omml(n['right'])}</m:den>"
                "</m:f>"
            )
        left = _omml(n["left"]) if isinstance(n.get("left"), dict) else ""
        right = _omml(n["right"]) if isinstance(n.get("right"), dict) else ""
        return left + _omml_run(_OP_OMML.get(op, op)) + right
    if t == "neg":
        return _omml_run("−") + _omml(n["expr"])
    return ""


# --- Parser ---


class _Parser:
    def __init__(self, s: str) -> None:
        self.s = s
        self.pos = 0

    def skip_ws(self) -> None:
        while self.pos < len(self.s) and self.s[self.pos].isspace():
            self.pos += 1

    def peek(self) -> str:
        self.skip_ws()
        return self.s[self.pos] if self.pos < len(self.s) else ""

    def starts(self, token: str) -> bool:
        self.skip_ws()
        return self.s.startswith(token, self.pos)

    def eat(self, token: str) -> bool:
        self.skip_ws()
        if self.s.startswith(token, self.pos):
            self.pos += len(token)
            return True
        return False

    def parse_expression(self) -> dict[str, Any]:
        """equality / approx chain."""
        left = self.parse_add()
        self.skip_ws()
        if self.eat("~=") or self.eat("≈"):
            right = self.parse_add()
            return _node("approx", lhs=left, rhs=right)
        if self.eat("="):
            right = self.parse_add()
            return _node("eq", lhs=left, rhs=right)
        return left

    def parse_add(self) -> dict[str, Any]:
        left = self.parse_mul()
        while True:
            self.skip_ws()
            if self.eat("+"):
                left = _node("op", op="+", left=left, right=self.parse_mul())
            elif self._is_binary_minus():
                self.pos += 1
                left = _node("op", op="-", left=left, right=self.parse_mul())
            else:
                break
        return left

    def _is_binary_minus(self) -> bool:
        self.skip_ws()
        if not self.starts("-"):
            return False
        # Unary minus handled in parse_mul/primary
        return True

    def parse_mul(self) -> dict[str, Any]:
        left = self.parse_unary()
        while True:
            self.skip_ws()
            if self.eat("*") or self.eat("·") or self.eat("⋅"):
                left = _node("op", op="*", left=left, right=self.parse_unary())
            elif self.eat("/"):
                left = _node("op", op="/", left=left, right=self.parse_unary())
            else:
                # Implicit multiplication: number/sym next to group/sym
                ch = self.peek()
                if ch and (ch.isalpha() or ch == "(" or ch.isdigit()):
                    # Avoid swallowing relational ops
                    if ch in "=~<>!":
                        break
                    right = self.parse_unary()
                    left = _node("op", op="*", left=left, right=right)
                else:
                    break
        return left

    def parse_unary(self) -> dict[str, Any]:
        self.skip_ws()
        if self.eat("-"):
            return _node("neg", expr=self.parse_postfix())
        return self.parse_postfix()

    def parse_postfix(self) -> dict[str, Any]:
        base = self.parse_primary()
        while True:
            self.skip_ws()
            if self.eat("_"):
                script = self.parse_script()
                base = _node("sub", base=base, script=script)
            elif self.eat("^"):
                script = self.parse_script()
                base = _node("sup", base=base, script=script)
            else:
                break
        return base

    def parse_script(self) -> dict[str, Any]:
        self.skip_ws()
        if self.eat("{"):
            expr = self.parse_expression()
            if not self.eat("}"):
                raise MathAstError("unclosed script brace")
            return expr
        # Single atom
        return self.parse_primary()

    def parse_primary(self) -> dict[str, Any]:
        self.skip_ws()
        if self.eat("("):
            expr = self.parse_expression()
            if not self.eat(")"):
                raise MathAstError("unclosed paren")
            return _node("group", expr=expr)
        ch = self.peek()
        if not ch:
            raise MathAstError("unexpected end")
        if ch.isdigit() or (ch == "." and self.pos + 1 < len(self.s) and self.s[self.pos + 1].isdigit()):
            return self._parse_number()
        if ch.isalpha() or ch == "\\":
            return self._parse_ident()
        raise MathAstError(f"unexpected {ch!r}")

    def _parse_number(self) -> dict[str, Any]:
        self.skip_ws()
        start = self.pos
        while self.pos < len(self.s) and (self.s[self.pos].isdigit() or self.s[self.pos] == "."):
            self.pos += 1
        return _node("num", value=self.s[start : self.pos])

    def _parse_ident(self) -> dict[str, Any]:
        self.skip_ws()
        if self.eat("\\"):
            start = self.pos
            while self.pos < len(self.s) and self.s[self.pos].isalpha():
                self.pos += 1
            name = self.s[start : self.pos]
            if not name:
                raise MathAstError("empty latex command")
            # Map known greek commands without backslash for sym table
            key = name if name in _GREEK else name
            if key in _GREEK or name in _GREEK:
                return _node("sym", name=name if name in _GREEK else key)
            return _node("sym", name=name)
        start = self.pos
        # Multi-letter identifiers (Equity, Norm, CV) or single greek words
        while self.pos < len(self.s) and (self.s[self.pos].isalnum() or self.s[self.pos] in "'_"):
            # Stop before underscore used as subscript operator: C_0
            if self.s[self.pos] == "_" and self.pos > start:
                break
            if self.s[self.pos] == "'":
                self.pos += 1
                break
            self.pos += 1
        name = self.s[start : self.pos]
        if not name:
            raise MathAstError("empty ident")
        return _node("sym", name=name)
