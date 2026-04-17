"""Advanced code analyzer with AST-based deep analysis.

Provides comprehensive code understanding:
- AST-based parsing (not just regex)
- Dependency graph extraction
- Call chain analysis
- Architecture overview generation
- Design pattern detection
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict


@dataclass
class FunctionInfo:
    """Detailed function information."""

    name: str
    line_number: int
    args: list[str] = field(default_factory=list)
    returns: str | None = None
    docstring: str | None = None
    decorators: list[str] = field(default_factory=list)
    complexity: int = 1  # Cyclomatic complexity
    calls: list[str] = field(default_factory=list)  # Functions it calls
    is_async: bool = False
    is_method: bool = False


@dataclass
class ClassInfo:
    """Detailed class information."""

    name: str
    line_number: int
    docstring: str | None = None
    methods: list[FunctionInfo] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)  # Parent classes
    decorators: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """Module-level information."""

    file_path: str
    imports: list[dict] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    global_vars: list[str] = field(default_factory=list)
    docstring: str | None = None


@dataclass
class ProjectArchitecture:
    """High-level project architecture."""

    total_files: int
    total_classes: int
    total_functions: int
    entry_points: list[str] = field(default_factory=list)
    core_modules: list[str] = field(default_factory=list)
    dependency_graph: dict = field(default_factory=dict)
    layer_structure: dict = field(default_factory=dict)


class ASTCodeAnalyzer:
    """AST-based code analyzer for deep code understanding."""

    def __init__(self):
        self._cache: dict[str, ModuleInfo] = {}

    def analyze_file(self, file_path: str | Path) -> ModuleInfo | None:
        """Analyze a single Python file using AST."""
        path = Path(file_path)

        if not path.exists() or path.suffix != ".py":
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except SyntaxError:
            return None
        except Exception:
            return None

        module_info = ModuleInfo(file_path=str(path))

        # Extract module docstring
        if ast.get_docstring(tree):
            module_info.docstring = ast.get_docstring(tree)

        # Analyze all top-level nodes
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                module_info.imports.extend(self._analyze_import(node))
            elif isinstance(node, ast.ImportFrom):
                module_info.imports.append(self._analyze_import_from(node))
            elif isinstance(node, ast.ClassDef):
                module_info.classes.append(self._analyze_class(node))
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                module_info.functions.append(self._analyze_function(node))
            elif isinstance(node, ast.Assign):
                module_info.global_vars.extend(self._analyze_assignment(node))

        self._cache[str(path)] = module_info
        return module_info

    def _analyze_import(self, node: ast.Import) -> list[dict]:
        """Analyze import statements."""
        imports = []
        for alias in node.names:
            imports.append(
                {"type": "import", "module": alias.name, "as": alias.asname, "line": node.lineno}
            )
        return imports

    def _analyze_import_from(self, node: ast.ImportFrom) -> dict:
        """Analyze from ... import statements."""
        return {
            "type": "from_import",
            "module": node.module,
            "names": [{"name": a.name, "as": a.asname} for a in node.names],
            "line": node.lineno,
        }

    def _analyze_class(self, node: ast.ClassDef) -> ClassInfo:
        """Analyze a class definition."""
        class_info = ClassInfo(
            name=node.name, line_number=node.lineno, docstring=ast.get_docstring(node)
        )

        # Extract base classes
        for base in node.bases:
            if isinstance(base, ast.Name):
                class_info.bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                class_info.bases.append(self._get_annotation_name(base))

        # Extract decorators
        for decorator in node.decorator_list:
            class_info.decorators.append(self._get_decorator_name(decorator))

        # Analyze methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = self._analyze_function(item, is_method=True)
                class_info.methods.append(method)
            elif isinstance(item, ast.Assign):
                class_info.attributes.extend(self._analyze_assignment(item))

        return class_info

    def _analyze_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False
    ) -> FunctionInfo:
        """Analyze a function definition."""
        func_info = FunctionInfo(
            name=node.name,
            line_number=node.lineno,
            docstring=ast.get_docstring(node),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
        )

        # Extract arguments
        args = node.args
        # Positional args
        for arg in args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._get_annotation_name(arg.annotation)}"
            func_info.args.append(arg_str)

        # Default values
        [None] * (len(args.args) - len(args.defaults)) + [ast.dump(d) for d in args.defaults]

        # *args
        if args.vararg:
            func_info.args.append(f"*{args.vararg.arg}")

        # **kwargs
        if args.kwarg:
            func_info.args.append(f"**{args.kwarg.arg}")

        # Return type
        if node.returns:
            func_info.returns = self._get_annotation_name(node.returns)

        # Decorators
        for decorator in node.decorator_list:
            func_info.decorators.append(self._get_decorator_name(decorator))

        # Calculate complexity and find calls
        func_info.complexity = self._calculate_complexity(node)
        func_info.calls = self._find_function_calls(node)

        return func_info

    def _analyze_assignment(self, node: ast.Assign) -> list[str]:
        """Analyze variable assignments."""
        vars = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                vars.append(target.id)
        return vars

    def _get_decorator_name(self, node: ast.expr) -> str:
        """Get decorator name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_decorator_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "<unknown>"

    def _get_annotation_name(self, node: ast.expr) -> str:
        """Get type annotation name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_annotation_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return (
                f"{self._get_annotation_name(node.value)}[{self._get_annotation_name(node.slice)}]"
            )
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        return "<unknown>"

    def _calculate_complexity(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """Calculate cyclomatic complexity."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def _find_function_calls(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Find all function calls within a function."""
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return calls

    def analyze_project(self, root_path: str | Path) -> ProjectArchitecture:
        """Analyze entire project structure."""
        root = Path(root_path)

        # Find all Python files
        py_files = list(root.rglob("*.py"))
        py_files = [
            f
            for f in py_files
            if not any(part.startswith(".") or part == "__pycache__" for part in f.parts)
        ]

        # Analyze each file
        for file_path in py_files:
            self.analyze_file(file_path)

        # Build architecture overview
        total_classes = sum(len(m.classes) for m in self._cache.values())
        total_functions = sum(len(m.functions) for m in self._cache.values())

        # Find entry points (files with if __name__ == "__main__")
        entry_points = []
        for path, module in self._cache.items():
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            if "__main__" in content:
                entry_points.append(path)

        # Identify core modules (most imported)
        import_count = defaultdict(int)
        for module in self._cache.values():
            for imp in module.imports:
                if "module" in imp:
                    import_count[imp["module"]] += 1

        core_modules = sorted(import_count.keys(), key=lambda x: import_count[x], reverse=True)[:10]

        # Build dependency graph
        dependency_graph = defaultdict(list)
        for path, module in self._cache.items():
            module_name = Path(path).stem
            for imp in module.imports:
                if "module" in imp:
                    dependency_graph[module_name].append(imp["module"])

        # Layer structure analysis
        layer_structure = {"commands": [], "services": [], "tools": [], "models": [], "utils": []}
        for path in self._cache.keys():
            rel_path = str(Path(path).relative_to(root))
            if "command" in rel_path:
                layer_structure["commands"].append(rel_path)
            elif "service" in rel_path:
                layer_structure["services"].append(rel_path)
            elif "tool" in rel_path:
                layer_structure["tools"].append(rel_path)
            elif "model" in rel_path or "type" in rel_path:
                layer_structure["models"].append(rel_path)
            elif "util" in rel_path:
                layer_structure["utils"].append(rel_path)

        return ProjectArchitecture(
            total_files=len(py_files),
            total_classes=total_classes,
            total_functions=total_functions,
            entry_points=entry_points,
            core_modules=core_modules,
            dependency_graph=dict(dependency_graph),
            layer_structure=layer_structure,
        )

    def generate_architecture_report(self, root_path: str | Path) -> str:
        """Generate a comprehensive architecture report."""
        arch = self.analyze_project(root_path)

        report = f"""# Project Architecture Analysis

## Statistics
- **Total Files**: {arch.total_files}
- **Total Classes**: {arch.total_classes}
- **Total Functions**: {arch.total_functions}
- **Avg Functions/File**: {arch.total_functions / arch.total_files:.1f}

## Entry Points
"""
        for entry in arch.entry_points[:5]:
            report += f"- `{entry}`\n"

        report += "\n## Core Modules (Most Imported)\n"
        for module in arch.core_modules[:10]:
            count = sum(
                1 for m in self._cache.values() for imp in m.imports if imp.get("module") == module
            )
            report += f"- `{module}` (imported {count} times)\n"

        report += "\n## Layer Structure\n"
        for layer, files in arch.layer_structure.items():
            if files:
                report += f"\n### {layer.capitalize()} ({len(files)} files)\n"
                for f in files[:5]:
                    report += f"- `{f}`\n"
                if len(files) > 5:
                    report += f"- ... and {len(files) - 5} more\n"

        # Module details
        report += "\n## Module Details\n"
        for path, module in sorted(self._cache.items())[:10]:
            report += f"\n### {path}\n"
            if module.docstring:
                report += f"> {module.docstring[:100]}...\n\n"

            if module.classes:
                report += "**Classes**:\n"
                for cls in module.classes:
                    methods_str = ", ".join([m.name for m in cls.methods[:5]])
                    if len(cls.methods) > 5:
                        methods_str += f" and {len(cls.methods)} more"
                    report += f"- `{cls.name}`"
                    if cls.bases:
                        report += f" (extends: {', '.join(cls.bases)})"
                    report += f": {methods_str}\n"

            if module.functions:
                report += "**Functions**:\n"
                for func in module.functions[:5]:
                    args_str = ", ".join(func.args[:3])
                    if len(func.args) > 3:
                        args_str += "..."
                    report += f"- `{func.name}({args_str})`"
                    if func.docstring:
                        report += f" - {func.docstring[:50]}..."
                    report += "\n"

        return report


# Global instance
_analyzer: ASTCodeAnalyzer | None = None


def get_analyzer() -> ASTCodeAnalyzer:
    """Get global analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = ASTCodeAnalyzer()
    return _analyzer
