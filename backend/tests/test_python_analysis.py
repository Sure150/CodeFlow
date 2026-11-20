import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from app.analyzer import analyze_python


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content).lstrip("\n"), encoding="utf-8")
        return path

    def test_direct_calls_keep_same_named_definitions_separate(self):
        self.write("helpers.py", "def normalize(value): return value.strip()")
        self.write("main.py", """
            from helpers import normalize as imported
            import helpers as module

            def normalize(value):
                return value.upper()

            def run(value, callback):
                callback(module.normalize(imported(normalize(value))))
        """)
        result = analyze_python(self.root)
        symbols = {symbol.id: symbol for symbol in result.symbols}
        calls = {
            call.expression: (symbols[call.target].file if call.target else None, call.status)
            for call in result.calls if symbols[call.caller].name == "run"
        }
        self.assertEqual(calls, {
            "callback": (None, "unresolved"),
            "module.normalize": ("helpers.py", "resolved"),
            "imported": ("helpers.py", "resolved"),
            "normalize": ("main.py", "resolved"),
        })
        self.assertIn("callback(module.normalize", next(s.source for s in result.symbols if s.name == "run"))

    def test_relative_imports_and_recursive_calls(self):
        self.write("pkg/__init__.py", "")
        self.write("pkg/formatting.py", "def render(): return 'ok'")
        self.write("pkg/main.py", """
            from . import formatting as helpers
            from .formatting import render as relative_render

            async def run(repeat):
                if repeat:
                    await run(False)
                return helpers.render(), relative_render()
        """)
        result = analyze_python(self.root)
        symbols = {symbol.name: symbol.id for symbol in result.symbols}
        calls = {call.expression: call.target for call in result.calls}
        self.assertEqual(calls, {
            "run": symbols["run"],
            "helpers.render": symbols["render"],
            "relative_render": symbols["render"],
        })

    def test_shadowed_and_reassigned_names_stay_unresolved(self):
        self.write("main.py", """
            def stable(): pass
            def replaced(): pass
            replaced = stable

            def run(stable):
                stable()
                replaced()
        """)
        result = analyze_python(self.root)
        self.assertEqual(len(result.calls), 2)
        self.assertTrue(all(call.target is None and call.status == "unresolved" for call in result.calls))

    def test_nested_functions_and_methods_have_qualified_names(self):
        self.write("main.py", """
            def helper(): pass

            class Worker:
                def run(self):
                    def inner():
                        helper()
                    self.finish()
        """)
        result = analyze_python(self.root)
        symbols = {symbol.qualified_name: symbol.id for symbol in result.symbols}
        calls = {call.expression: (call.caller, call.target) for call in result.calls}
        self.assertEqual(calls, {
            "helper": (symbols["Worker.run.inner"], symbols["helper"]),
            "self.finish": (symbols["Worker.run"], None),
        })

    def test_skips_other_languages_venvs_and_syntax_errors_without_executing_code(self):
        self.write("healthy.py", """
            raise RuntimeError("analyzed only")
            def available(): pass
        """)
        self.write("broken.py", "def broken(")
        self.write(".venv/generated.py", "def ignored(): pass")
        self.write("component.vue", "<template></template>")
        result = analyze_python(self.root)
        self.assertEqual(result.files, ["healthy.py"])
        self.assertEqual([symbol.name for symbol in result.symbols], ["available"])
        self.assertTrue(any("broken.py" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
