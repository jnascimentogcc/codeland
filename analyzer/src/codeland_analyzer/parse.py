"""Per-file metrics for TypeScript and Python sources, from a single tree-sitter parse each."""

from collections.abc import Callable
from dataclasses import dataclass, field

import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

_PARSERS = {
    False: Parser(Language(tree_sitter_typescript.language_typescript())),
    True: Parser(Language(tree_sitter_typescript.language_tsx())),
}
_PYTHON_PARSER = Parser(Language(tree_sitter_python.language()))

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

_PY_FUNCTION_NODES = frozenset({"function_definition", "lambda"})
# `elif` is its own node; comprehension clauses branch like their statement forms.
_PY_DECISION_NODES = frozenset(
    {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "except_group_clause",
        "case_clause",
        "conditional_expression",
        "for_in_clause",
        "if_clause",
    }
)


@dataclass(frozen=True, order=True)
class ImportRef:
    specifier: str
    kind: str  # one of the edge kinds in schema/city-model.schema.json
    # Python `from x import a, b`: the names, which may themselves be submodules of x.
    names: tuple[str, ...] = ()


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
    return _walk(
        _PARSERS[tsx].parse(source).root_node,
        _FUNCTION_NODES,
        _is_typescript_decision,
        _import_ref,
        lambda node: False,
    )


def analyze_python(source: bytes) -> FileMetrics:
    return _walk(
        _PYTHON_PARSER.parse(source).root_node,
        _PY_FUNCTION_NODES,
        _is_python_decision,
        _python_import_refs,
        _is_docstring_like,
    )


def analyze_file(path: str, source: bytes) -> FileMetrics:
    """Metrics of a source file, by extension."""
    if path.endswith(".py"):
        return analyze_python(source)
    return analyze_source(source, tsx=path.endswith(".tsx"))


def _walk(
    root: Node,
    function_nodes: frozenset[str],
    is_decision: Callable[[Node], bool],
    imports_of: Callable[[Node], list[ImportRef]],
    is_comment_like: Callable[[Node], bool],
) -> FileMetrics:
    code_lines: set[int] = set()
    imports: list[ImportRef] = []
    # Index 0 is top-level code (no base complexity); each function adds 1 + its own decisions,
    # so decisions inside a nested function are not counted again for the enclosing one.
    complexity_by_owner = [0]
    stack: list[tuple[Node, int]] = [(root, 0)]

    while stack:
        node, owner = stack.pop()
        kind = node.type
        if kind == "comment" or is_comment_like(node):
            continue
        if node.child_count == 0:
            # Leaf token (keywords included, which is why this check comes first).
            code_lines.update(range(node.start_point.row, node.end_point.row + 1))
            continue
        if kind in function_nodes:
            complexity_by_owner.append(1)
            owner = len(complexity_by_owner) - 1
        elif is_decision(node):
            complexity_by_owner[owner] += 1
        imports.extend(imports_of(node))
        stack.extend((child, owner) for child in node.children)

    functions = complexity_by_owner[1:]
    return FileMetrics(
        loc=len(code_lines),
        complexity=sum(complexity_by_owner),
        max_function_complexity=max(functions, default=0),
        functions=len(functions),
        imports=sorted(imports),
    )


def _is_typescript_decision(node: Node) -> bool:
    return node.type in _DECISION_NODES or (
        node.type == "binary_expression" and _operator(node) in _LOGICAL_OPERATORS
    )


def _is_python_decision(node: Node) -> bool:
    return node.type in _PY_DECISION_NODES or node.type == "boolean_operator"


def _is_docstring_like(node: Node) -> bool:
    """A statement that is only a string (docstrings): documentation, not code."""
    return (
        node.type == "expression_statement"
        and node.named_child_count == 1
        and node.named_children[0].type == "string"
    )


def _operator(node: Node) -> str | None:
    operator = node.child_by_field_name("operator")
    return operator.type if operator else None


def _import_ref(node: Node) -> list[ImportRef]:
    ref = _typescript_import_ref(node)
    return [ref] if ref else []


def _typescript_import_ref(node: Node) -> ImportRef | None:
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


def _python_import_refs(node: Node) -> list[ImportRef]:
    match node.type:
        case "import_statement":
            refs = []
            for child in node.children_by_field_name("name"):
                name = (
                    child.child_by_field_name("name") if child.type == "aliased_import" else child
                )
                if name is not None:
                    refs.append(ImportRef(name.text.decode("utf-8"), "import"))
            return refs
        case "import_from_statement":
            module = node.child_by_field_name("module_name")
            if module is None:
                return []
            names = []
            for child in node.children_by_field_name("name"):
                name = (
                    child.child_by_field_name("name") if child.type == "aliased_import" else child
                )
                if name is not None:
                    names.append(name.text.decode("utf-8"))
            return [ImportRef(module.text.decode("utf-8"), "import", tuple(names))]
        case "call":
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            if function is None or arguments is None:
                return []
            called = function.text.decode("utf-8") if function.type != "call" else ""
            if called not in ("importlib.import_module", "import_module", "__import__"):
                return []
            first = next((c for c in arguments.named_children), None)
            if first is None or first.type != "string":
                return []
            content = "".join(
                c.text.decode("utf-8") for c in first.children if c.type == "string_content"
            )
            return [ImportRef(content, "dynamic-import")] if content else []
    return []
