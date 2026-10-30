"""Per-file metrics for TypeScript sources, computed from a single tree-sitter parse."""

from dataclasses import dataclass, field

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

_PARSERS = {
    False: Parser(Language(tree_sitter_typescript.language_typescript())),
    True: Parser(Language(tree_sitter_typescript.language_tsx())),
}

_FUNCTION_NODES = frozenset(
    {
        "function_declaration",
        "function_expression",
        "function",
        "arrow_function",
        "method_definition",
        "generator_function_declaration",
        "generator_function",
    }
)
_DECISION_NODES = frozenset(
    {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "catch_clause",
        "ternary_expression",
    }
)
_LOGICAL_OPERATORS = frozenset({"&&", "||", "??"})


@dataclass(frozen=True, order=True)
class ImportRef:
    specifier: str
    kind: str  # one of the edge kinds in schema/city-model.schema.json


@dataclass
class FileMetrics:
    loc: int = 0
    complexity: int = 0
    max_function_complexity: int = 0
    functions: int = 0
    imports: list[ImportRef] = field(default_factory=list)

    @property
    def decisions(self) -> int:
        """Branching points only: complexity without the base 1 of each function."""
        return self.complexity - self.functions


def analyze_source(source: bytes, *, tsx: bool) -> FileMetrics:
    tree = _PARSERS[tsx].parse(source)
    code_lines: set[int] = set()
    imports: list[ImportRef] = []
    # Index 0 is top-level code (no base complexity); each function adds 1 + its own decisions,
    # so decisions inside a nested function are not counted again for the enclosing one.
    complexity_by_owner = [0]
    stack: list[tuple[Node, int]] = [(tree.root_node, 0)]

    while stack:
        node, owner = stack.pop()
        kind = node.type
        if kind == "comment":
            continue
        if node.child_count == 0:
            # Leaf token (keywords included, which is why this check comes first).
            code_lines.update(range(node.start_point.row, node.end_point.row + 1))
            continue
        if kind in _FUNCTION_NODES:
            complexity_by_owner.append(1)
            owner = len(complexity_by_owner) - 1
        elif kind in _DECISION_NODES or (
            kind == "binary_expression" and _operator(node) in _LOGICAL_OPERATORS
        ):
            complexity_by_owner[owner] += 1
        if ref := _import_ref(node):
            imports.append(ref)
        stack.extend((child, owner) for child in node.children)

    functions = complexity_by_owner[1:]
    return FileMetrics(
        loc=len(code_lines),
        complexity=sum(complexity_by_owner),
        max_function_complexity=max(functions, default=0),
        functions=len(functions),
        imports=sorted(imports),
    )


def _operator(node: Node) -> str | None:
    operator = node.child_by_field_name("operator")
    return operator.type if operator else None


def _import_ref(node: Node) -> ImportRef | None:
    match node.type:
        case "import_statement":
            source = node.child_by_field_name("source")
            if source is None:  # import x = require("y")
                clause = next((c for c in node.children if c.type == "import_require_clause"), None)
                source = clause and _first_string(clause)
            return _ref(source, "import")
        case "export_statement":
            return _ref(node.child_by_field_name("source"), "reexport")
        case "call_expression":
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            if function is None or arguments is None:
                return None
            if function.type == "import":
                kind = "dynamic-import"
            elif function.type == "identifier" and function.text == b"require":
                kind = "require"
            else:
                return None
            return _ref(_first_string(arguments), kind)
    return None


def _first_string(node: Node) -> Node | None:
    return next((c for c in node.named_children if c.type == "string"), None)


def _ref(node: Node | None, kind: str) -> ImportRef | None:
    if node is None or node.type != "string":
        return None
    return ImportRef(node.text.decode("utf-8")[1:-1], kind)
