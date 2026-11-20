import ast
import os
import stat
import symtable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tokenize import detect_encoding

IGNORED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", "node_modules", "build", "dist"}
MAX_FILES = 500
MAX_DIRECTORIES = 2_000
MAX_FILE_BYTES = 512 * 1024
MAX_PROJECT_BYTES = 8 * 1024 * 1024


@dataclass
class PythonFile:
    path: str
    module: str
    is_package: bool
    lines: list[str]
    tree: ast.Module
    scope: symtable.SymbolTable


def scan_python(root: Path, warnings: list[str]) -> list[PythonFile]:
    files: list[PythonFile] = []
    project_bytes = 0
    candidates = 0
    package_prefix = [root.name] if (root / "__init__.py").is_file() else []

    def report_directory_error(error: OSError) -> None:
        path = Path(error.filename).relative_to(root) if error.filename else "."
        warnings.append(f"{path}：无法读取目录")

    for directory_count, (directory, dirs, names) in enumerate(
        os.walk(root, onerror=report_directory_error, followlinks=False), start=1
    ):
        if directory_count > MAX_DIRECTORIES:
            warnings.append(f"已达到 {MAX_DIRECTORIES} 个目录的扫描上限，结果可能不完整")
            break
        dirs[:] = sorted(name for name in dirs if not name.startswith(".") and name not in IGNORED_DIRECTORIES)
        for name in sorted(names):
            if not name.endswith(".py"):
                continue
            if candidates == MAX_FILES:
                warnings.append(f"已达到 {MAX_FILES} 个 Python 文件的扫描上限，结果可能不完整")
                return files
            candidates += 1
            path = Path(directory) / name
            relative = path.relative_to(root)
            label = relative.as_posix()
            try:
                if not stat.S_ISREG(path.lstat().st_mode):
                    continue
                with path.open("rb") as stream:
                    data = stream.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    warnings.append(f"{label}：超过单文件大小上限")
                    continue
                project_bytes += len(data)
                if project_bytes > MAX_PROJECT_BYTES:
                    warnings.append("已达到项目源码大小上限，结果可能不完整")
                    return files
                encoding, _ = detect_encoding(BytesIO(data).readline)
                source = data.decode(encoding)
                tree = ast.parse(source, filename=label)
                scope = symtable.symtable(source, label, "exec")
            except (SyntaxError, UnicodeError, LookupError, ValueError, RecursionError) as error:
                line = getattr(error, "lineno", None)
                warnings.append(f"{label}{f':{line}' if line else ''}：无法解析 Python 源码")
                continue
            except OSError:
                warnings.append(f"{label}：无法读取文件")
                continue

            is_package = path.name == "__init__.py"
            parts = relative.parent.parts if is_package else relative.with_suffix("").parts
            lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            files.append(PythonFile(
                label, ".".join([*package_prefix, *parts]), is_package, lines, tree, scope,
            ))
    return files
