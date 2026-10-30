from codeland_analyzer.parse import ImportRef, analyze_source

SOURCE = b"""\
// leading comment
import { a } from "./a";
import type { B } from "../b.js";
import fs = require("node:fs");
export { c } from "./c";

/* block
   comment */
export function pick(x: number, y?: number): number {
  if (x > 0 && y) {
    return x;
  } else if (x < 0) {
    return -x;
  }
  const inner = (v: number) => (v ? 1 : 0);
  return y ?? inner(x);
}

class Box {
  open(): void {
    for (const i of [1, 2]) {
      try { void i; } catch { }
    }
  }
}

const lazy = () => import("./lazy");
const legacy = require("./legacy");
"""


def test_metrics_of_typescript_source():
    metrics = analyze_source(SOURCE, tsx=False)

    # pick: 1 + if + && + else-if + ?? = 5; inner: 1 + ternary = 2; open: 1 + for + catch = 3;
    # lazy: 1. Nested functions are counted on their own, not inside pick.
    assert metrics.functions == 4
    assert metrics.complexity == 5 + 2 + 3 + 1
    assert metrics.max_function_complexity == 5
    # 29 lines in total; 3 comment lines and 4 blank lines are not code.
    assert metrics.loc == 22
    assert metrics.imports == sorted(
        [
            ImportRef("./a", "import"),
            ImportRef("../b.js", "import"),
            ImportRef("node:fs", "import"),
            ImportRef("./c", "reexport"),
            ImportRef("./lazy", "dynamic-import"),
            ImportRef("./legacy", "require"),
        ]
    )


def test_large_source_does_not_crash():
    # Regression: tree-sitter 0.26.0 crashed natively on trees of a few thousand nodes.
    body = "".join(
        f'import {{ f{i} }} from "./m{i}.js";\n'
        f"export function g{i}(x: number) {{ return x > {i} ? f{i}(x) : {{ v: [x, {i}] }}; }}\n"
        for i in range(300)
    )
    metrics = analyze_source(body.encode(), tsx=False)

    assert metrics.functions == 300
    assert len(metrics.imports) == 300


def test_tsx_source_is_parsed_with_jsx_grammar():
    source = b"""\
import React from "react";
export const View = ({ ok }: { ok: boolean }) => (
  <div>{ok ? <span>yes</span> : null}</div>
);
"""
    metrics = analyze_source(source, tsx=True)

    assert metrics.functions == 1
    assert metrics.complexity == 2
    assert metrics.loc == 4
    assert metrics.imports == [ImportRef("react", "import")]
