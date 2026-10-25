"""CSV spreadsheet engine with cell formulas for SigmaOS-spreadsheet.

Principles: a tiny AST-free recursive-descent formula evaluator (no eval() of
arbitrary code), fail-fast on bad refs / circular references, deterministic
evaluation order, plan vs apply separation (only 'dump' touches a file, and
self_test keeps that inside a tempdir).
"""
import argparse, os, re, sys, tempfile

ENGINE = {
    "name": "sigma-sheet",
    "summary": "CSV spreadsheet with =A1+B2 style formulas",
    "language": "python",
    "verbs": ["load", "set", "eval", "dump", "sum"],
    "principles": ["Defensive Programming", "Fail-Fast", "Least Astonishment",
                   "KISS", "Separation of Concerns", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-sheet set A1 10
$ sigma-sheet set A2 32
$ sigma-sheet set B1 "=A1 + A2"
$ sigma-sheet eval B1
42
$ sigma-sheet sum A1:A2
42
$ sigma-sheet dump --out sheet.csv
"""

DEFAULT_STORE = os.path.expanduser("~/.config/sigma-sheet/sheet.json")
_REF_RE = re.compile(r"^([A-Z]{1,3})([0-9]{1,7})$")
_TOKEN_RE = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([A-Za-z]{1,3}[0-9]{1,7})|([-+*/()]))")


class SheetError(ValueError):
    pass


def norm_ref(ref):
    r = str(ref).strip().upper()
    if not _REF_RE.match(r):
        raise SheetError(f"bad cell reference: {ref!r} (want e.g. A1)")
    return r


class Sheet:
    """Cell store with formula evaluation. Pure except dump()/load_csv()."""

    def __init__(self):
        self.cells = {}  # ref -> raw string

    # -- pure layer -------------------------------------------------------
    def set(self, ref, value):
        self.cells[norm_ref(ref)] = str(value)

    def raw(self, ref):
        return self.cells.get(norm_ref(ref), "")

    def value(self, ref):
        """Evaluate a cell (formulas included). Blank cells are 0."""
        return self.cell_value(norm_ref(ref), seen=set())

    def cell_value(self, ref, seen):
        if ref in seen:
            raise SheetError(f"circular reference at {ref}")
        raw = self.cells.get(ref, "").strip()
        if not raw:
            return 0.0
        if raw.startswith("="):
            return self._eval_formula(raw[1:], seen | {ref})
        try:
            return float(raw)
        except ValueError:
            raise SheetError(f"{ref} is not numeric: {raw!r}")

    def _eval_formula(self, expr, seen):
        tokens = tokenize(expr)
        return _Parser(self, tokens, seen).parse()

    def column_sum(self, ref):
        """Sum a column range like A1:A10 (or A:A for the used rows). Pure."""
        if ":" not in ref:
            raise SheetError(f"sum needs a range like A1:A10, got {ref!r}")
        start, end = (p.strip().upper() for p in ref.split(":", 1))
        c1, r1 = _parse_bound(start)
        c2, r2 = _parse_bound(end)
        if c1 != c2:
            raise SheetError(f"range must stay in one column: {ref!r}")
        r1 = r1 or 1
        r2 = r2 if r2 is not None else max(self.used_range()[0], r1)
        if r2 < r1:
            raise SheetError(f"range end before start: {ref!r}")
        total = 0.0
        for r in range(r1, r2 + 1):
            raw = self.cells.get(f"{c1}{r}", "").strip()
            if not raw or raw.startswith("="):
                total += self.cell_value(f"{c1}{r}", set())
            else:
                try:
                    total += float(raw)
                except ValueError:
                    pass  # text cells are skipped (like a real SUM)
        return total

    def used_range(self):
        """(rows, cols) of the used block. Pure."""
        if not self.cells:
            return 0, 0
        max_r = max_c = 0
        for ref in self.cells:
            c, r = _split(ref)
            max_r = max(max_r, r)
            max_c = max(max_c, _col_num(c))
        return max_r, max_c

    # -- apply layer (filesystem) -----------------------------------------
    def load_csv(self, text):
        import csv as _csv
        self.cells = {}
        for r, row in enumerate(_csv.reader(text.splitlines()), 1):
            for c, val in enumerate(row):
                if val.strip():
                    self.set(f"{_col_name(c + 1)}{r}", val)

    def to_csv(self):
        rows, cols = self.used_range()
        lines = []
        for r in range(1, rows + 1):
            lines.append(",".join(self.cells.get(f"{_col_name(c + 1)}{r}", "")
                                  for c in range(cols)))
        return "\n".join(lines) + ("\n" if lines else "")


def _split(ref):
    m = _REF_RE.match(ref)
    return m.group(1), int(m.group(2))


def _parse_bound(part):
    """Parse 'A1' or a bare column 'A' into (column, row|None). Pure."""
    m = re.match(r"^([A-Z]{1,3})([0-9]{1,7})?$", part)
    if not m:
        raise SheetError(f"bad range bound: {part!r}")
    return m.group(1), int(m.group(2)) if m.group(2) else None


def _col_num(col):
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def _col_name(n):
    """1-based column number -> letter(s) (1 -> A, 26 -> Z, 27 -> AA)."""
    name = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        name = chr(65 + r) + name
    return name


def tokenize(expr):
    """Tokenise a formula. Pure. Raises SheetError on junk."""
    tokens, pos = [], 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            raise SheetError(f"bad token at {expr[pos:]!r}")
        pos = m.end()
        num, ref, op = m.groups()
        if num is not None:
            tokens.append(("num", float(num)))
        elif ref is not None:
            tokens.append(("ref", ref.upper()))
        else:
            tokens.append(("op", op))
    return tokens


class _Parser:
    """Recursive-descent parser: expr := term (('+'|'-') term)* ...

    No eval(), no AST module: only + - * / ( ) numbers and cell refs.
    """

    def __init__(self, sheet, tokens, seen):
        self.sheet, self.tokens, self.seen = sheet, tokens, seen
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def eat(self):
        if self.i >= len(self.tokens):
            raise SheetError("unexpected end of formula")
        t = self.tokens[self.i]
        self.i += 1
        return t

    def parse(self):
        v = self.expr()
        if self.i != len(self.tokens):
            raise SheetError(f"trailing tokens: {self.tokens[self.i:]!r}")
        return v

    def expr(self):
        v = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.eat()[1]
            rhs = self.term()
            v = v + rhs if op == "+" else v - rhs
        return v

    def term(self):
        v = self.factor()
        while self.peek()[1] in ("*", "/"):
            op = self.eat()[1]
            rhs = self.factor()
            if op == "*":
                v = v * rhs
            else:
                if rhs == 0:
                    raise SheetError("division by zero")
                v = v / rhs
        return v

    def factor(self):
        kind, val = self.peek()
        if kind == "op" and val in ("+", "-"):
            self.eat()
            v = self.factor()
            return -v if val == "-" else v
        return self.primary()

    def primary(self):
        kind, val = self.eat()
        if kind == "num":
            return val
        if kind == "ref":
            return self.sheet.cell_value(val, self.seen)
        if kind == "op" and val == "(":
            v = self.expr()
            k2, v2 = self.eat()
            if not (k2 == "op" and v2 == ")"):
                raise SheetError("missing closing parenthesis")
            return v
        raise SheetError(f"unexpected token: {val!r}")


def load_store(path):
    import json
    sheet = Sheet()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            for ref, raw in json.load(fh).items():
                sheet.set(ref, raw)
    return sheet


def save_store(path, sheet):
    import json
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".sigma-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(sheet.cells, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _fmt(v):
    return str(int(v)) if float(v) == int(v) else f"{v:g}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    p.add_argument("--store", default=DEFAULT_STORE, help="sheet store (JSON)")
    sub = p.add_subparsers(dest="cmd", required=True)
    ld = sub.add_parser("load", help="load a CSV file into the store")
    ld.add_argument("csv_path")
    st = sub.add_parser("set", help="set a cell (literal or =formula)")
    st.add_argument("ref")
    st.add_argument("value")
    ev = sub.add_parser("eval", help="evaluate a cell or expression")
    ev.add_argument("expr", help="cell ref or literal formula like '=A1+B1'")
    dp = sub.add_parser("dump", help="dump the sheet as CSV")
    dp.add_argument("--out", default=None, help="write CSV here (default: stdout)")
    sm = sub.add_parser("sum", help="sum a column range like A1:A10")
    sm.add_argument("range")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sheet = load_store(args.store)
        if args.cmd == "load":
            with open(args.csv_path, "r", encoding="utf-8") as fh:
                sheet.load_csv(fh.read())
            save_store(args.store, sheet)
            rows, cols = sheet.used_range()
            print(f"loaded {rows}x{cols}")
        elif args.cmd == "set":
            sheet.set(args.ref, args.value)
            save_store(args.store, sheet)
            print(f"{norm_ref(args.ref)} = {args.value}")
        elif args.cmd == "eval":
            expr = args.expr.strip()
            if expr.startswith("="):
                v = sheet._eval_formula(expr[1:], set())
            else:
                v = sheet.value(expr)
            print(_fmt(v))
        elif args.cmd == "dump":
            text = sheet.to_csv()
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(text)
                print(f"wrote {args.out}", file=sys.stderr)
            else:
                sys.stdout.write(text)
        elif args.cmd == "sum":
            print(_fmt(sheet.column_sum(args.range)))
        return 0
    except (SheetError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    s = Sheet()
    s.set("A1", "10")
    s.set("A2", "32")
    s.set("B1", "=A1 + A2")
    s.set("B2", "=B1 * 2")
    s.set("C1", "=B2 / 4 - (A2 - A1)")
    assert s.value("A1") == 10.0
    assert s.value("B1") == 42.0          # 10 + 32
    assert s.value("B2") == 84.0          # 42 * 2
    assert s.value("C1") == -1.0          # 84/4 - (32-10) = 21 - 22
    assert s.value("Z9") == 0.0           # blank cell -> 0
    # operator precedence & unary minus
    s.set("D1", "=1 + 2 * 3")
    s.set("D2", "=-A1 + 15")
    assert s.value("D1") == 7.0
    assert s.value("D2") == 5.0
    # column sums
    assert s.column_sum("A1:A2") == 42.0
    assert s.column_sum("B1:B2") == 126.0
    s.set("A3", "note")
    assert s.column_sum("A1:A3") == 42.0  # text skipped
    assert s.column_sum("A:A") == 42.0    # whole used column
    # fail-fast: cycles, self-reference, division by zero, junk
    s.set("E1", "=E2")
    s.set("E2", "=E1")
    s.set("F1", "=F1 + 1")
    s.set("G1", "=1/0")
    s.set("H1", "=A1 text")
    for ref in ("E1", "F1", "G1", "H1"):
        try:
            s.value(ref)
        except SheetError:
            pass
        else:
            raise AssertionError(f"expected SheetError for {ref}")
    for bad in ("=A1 +", "=(1", "=A1 ** 2", "=zz(", "", "=A1 A2"):
        try:
            s._eval_formula(bad.lstrip("="), set())
        except SheetError:
            pass
        else:
            raise AssertionError(f"should reject formula {bad!r}")
    try:
        s.value("not a ref")
    except SheetError:
        pass
    else:
        raise AssertionError("bad ref not caught")
    try:
        s.column_sum("A1:B2")
    except SheetError:
        pass
    else:
        raise AssertionError("cross-column sum not caught")
    # diamond references are fine (only true cycles fail)
    s.set("I1", "=A1+A1")
    assert s.value("I1") == 20.0
    # CSV round-trip (tempdir only)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "in.csv")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("1,2\n3,=A1+A2\n")
        t = Sheet()
        with open(p, "r", encoding="utf-8") as fh:
            t.load_csv(fh.read())
        assert t.value("B2") == 4.0   # A1(1) + A2(3)
        assert t.to_csv() == "1,2\n3,=A1+A2\n"
        out = os.path.join(d, "out.csv")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(t.to_csv())
        assert open(out, encoding="utf-8").read() == "1,2\n3,=A1+A2\n"
        store = os.path.join(d, "sheet.json")
        save_store(store, t)
        again = load_store(store)
        assert again.value("B2") == 4.0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
