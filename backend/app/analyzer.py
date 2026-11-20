import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path
from symtable import SymbolTable

from .scanner import PythonFile, scan_python

MAX_SYMBOLS = 3_000
MAX_CALLS = 12_000


@dataclass
class Symbol:
    id: str
    name: str
    qualified_name: str
    file: str
    line: int
    end_line: int
    source: str
    source_truncated: bool


@dataclass
class Call:
    caller: str
    target: str | None
    expression: str
    line: int
    column: int
    status: str


@dataclass
class Analysis:
    root: str
    files: list[str]
    symbols: list[Symbol]
    calls: list[Call]
    warnings: list[str]


@dataclass(frozen=True)
class Import:
    module: str
    attributes: tuple[str, ...] = ()
    member: str | None = None


class ModuleBindings(ast.NodeVisitor):
    """Count possible module-level definitions and writes before resolving by name."""

    def __init__(self) -> None:
        self.names: Counter[str] = Counter()
        self.wildcard = False

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names[node.id] += 1

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.names[node.name] += 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names[node.name] += 1

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.wildcard = True
            else:
                self.names[alias.asname or alias.name] += 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.names[node.name] += 1
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs | ast.MatchStar) -> None:
        if node.name:
            self.names[node.name] += 1
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.names[node.rest] += 1
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass


def symbol_id(file: PythonFile, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return f"{file.path}:{node.lineno}:{node.col_offset}"


class ModuleIndex:
    def __init__(self, files: list[PythonFile], warnings: list[str]) -> None:
        self.bindings: dict[str, ModuleBindings] = {}
        self.functions: dict[str, dict[str, str]] = defaultdict(dict)
        self.imports: dict[str, dict[str, Import]] = defaultdict(dict)
        counts = Counter(file.module for file in files)
        for file in files:
            if counts[file.module] == 1:
                try:
                    self.index_module(file)
                except RecursionError:
                    warnings.append(f"{file.path}：模块绑定过深，无法解析调用目标")

    def index_module(self, file: PythonFile) -> None:
        bindings = ModuleBindings()
        bindings.visit(file.tree)
        self.bindings[file.module] = bindings
        if bindings.wildcard:
            return

        for statement in file.tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not statement.decorator_list and bindings.names[statement.name] == 1:
                    self.functions[file.module][statement.name] = symbol_id(file, statement)
            elif isinstance(statement, ast.Import):
                for alias in statement.names:
                    base, *attributes = alias.name.split(".")
                    local = alias.asname or base
                    if bindings.names[local] == 1:
                        self.imports[file.module][local] = Import(
                            alias.name, () if alias.asname else tuple(attributes)
                        )
            elif isinstance(statement, ast.ImportFrom):
                module = statement.module or ""
                if statement.level:
                    package = file.module if file.is_package else file.module.rpartition(".")[0]
                    try:
                        module = resolve_name("." * statement.level + module, package)
                    except ImportError:
                        continue
                for alias in statement.names:
                    local = alias.asname or alias.name
                    if bindings.names[local] == 1:
                        self.imports[file.module][local] = Import(module, member=alias.name)

    def resolve(self, module: str, parts: list[str]) -> str | None:
        name, *attributes = parts
        if not attributes and name in self.functions[module]:
            return self.functions[module][name]

        imported = self.imports[module].get(name)
        if imported is None:
            return None
        if imported.member is not None:
            if not attributes:
                return self.functions[imported.module].get(imported.member)
            bindings = self.bindings.get(imported.module)
            if bindings and (bindings.wildcard or bindings.names[imported.member]):
                return None
            submodule = f"{imported.module}.{imported.member}"
            return self.functions[submodule].get(attributes[0]) if len(attributes) == 1 else None

        prefix = imported.attributes
        if tuple(attributes[:-1]) == prefix and attributes:
            return self.functions[imported.module].get(attributes[-1])
        return None


def name_parts(expression: ast.expr) -> list[str]:
    attributes: list[str] = []
    while isinstance(expression, ast.Attribute):
        attributes.append(expression.attr)
        expression = expression.value
    return [expression.id, *reversed(attributes)] if isinstance(expression, ast.Name) else []


def child_scope(
    scope: SymbolTable | None,
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> SymbolTable | None:
    if scope is None:
        return None
    matches = [child for child in scope.get_children()
               if child.get_name() == node.name and child.get_lineno() == node.lineno]
    return matches[0] if len(matches) == 1 else None


class FileAnalyzer(ast.NodeVisitor):
    def __init__(self, file: PythonFile, index: ModuleIndex, result: Analysis) -> None:
        self.file = file
        self.index = index
        self.result = result
        self.scope: SymbolTable | None = file.scope
        self.owner: str | None = None
        self.parents: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if len(self.result.symbols) >= MAX_SYMBOLS:
            return
        owner = symbol_id(self.file, node)
        end_line = node.end_lineno or node.lineno
        last_preview_line = min(end_line, node.lineno + 119)
        source = "\n".join(self.file.lines[node.lineno - 1:last_preview_line])
        self.result.symbols.append(Symbol(
            owner, node.name, ".".join([*self.parents, node.name]),
            self.file.path, node.lineno, end_line, source[:4_000],
            last_preview_line < end_line or len(source) > 4_000,
        ))
        self.visit_body(node, owner)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.visit_body(node, None)

    def visit_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
                   owner: str | None) -> None:
        previous_scope, previous_owner = self.scope, self.owner
        self.scope, self.owner = child_scope(self.scope, node), owner
        self.parents.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.parents.pop()
        self.scope, self.owner = previous_scope, previous_owner

    def visit_nested_expression(self, node: ast.AST) -> None:
        previous_scope = self.scope
        self.scope = None
        self.generic_visit(node)
        self.scope = previous_scope

    visit_Lambda = visit_nested_expression
    visit_ListComp = visit_nested_expression
    visit_SetComp = visit_nested_expression
    visit_DictComp = visit_nested_expression
    visit_GeneratorExp = visit_nested_expression

    def visit_Call(self, node: ast.Call) -> None:
        if self.owner is not None and len(self.result.calls) < MAX_CALLS:
            parts = name_parts(node.func)
            target = None
            if parts and self.scope is not None:
                try:
                    binding = self.scope.lookup(parts[0])
                    is_global = binding.is_global() and not (binding.is_assigned() or binding.is_imported())
                except KeyError:
                    is_global = False
                if is_global:
                    target = self.index.resolve(self.file.module, parts)
            self.result.calls.append(Call(
                self.owner, target, ".".join(parts)[:160] or "<动态调用>",
                node.lineno, node.col_offset, "resolved" if target else "unresolved",
            ))
        self.generic_visit(node)


def analyze_python(root: Path) -> Analysis:
    result = Analysis(str(root), [], [], [], [])
    files = scan_python(root, result.warnings)
    result.files = [file.path for file in files]
    index = ModuleIndex(files, result.warnings)
    for file in files:
        symbol_count, call_count = len(result.symbols), len(result.calls)
        try:
            FileAnalyzer(file, index, result).visit(file.tree)
        except RecursionError:
            del result.symbols[symbol_count:]
            del result.calls[call_count:]
            result.warnings.append(f"{file.path}：语法嵌套过深，已跳过")

    symbol_ids = {symbol.id for symbol in result.symbols}
    if len(result.symbols) == MAX_SYMBOLS:
        result.warnings.append(f"已达到 {MAX_SYMBOLS} 个函数的上限，结果可能不完整")
    if len(result.calls) == MAX_CALLS:
        result.warnings.append(f"已达到 {MAX_CALLS} 个调用点的上限，结果可能不完整")
    for call in result.calls:
        if call.target is not None and call.target not in symbol_ids:
            call.target, call.status = None, "unresolved"
    return result
