import ast
import unittest
from pathlib import Path

try:
    from pyrecon_connector import get_plugin_menu_spec
except ImportError:
    get_plugin_menu_spec = None


ROOT = Path(__file__).parents[1]


class PluginAssemblyTests(unittest.TestCase):
    @unittest.skipIf(get_plugin_menu_spec is None, "connector is not installed")
    def test_registered_actions_have_host_handlers(self):
        source = (ROOT / "PyReconstruct/modules/gui/main/main_window.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        main_window = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
        )
        handlers = {
            node.name for node in main_window.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        registered = {
            action["handler"]
            for group in get_plugin_menu_spec()
            for action in group["actions"]
            if action is not None
        }
        self.assertFalse(registered - handlers)

    def test_menu_is_assembled_from_connector_registry(self):
        source = (ROOT / "PyReconstruct/modules/gui/main/menubar.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("get_plugin_menu_spec", source)
        self.assertNotIn('"run_hungarian_tracking_act", "Hungarian tracking..."', source)

    def test_host_does_not_import_algorithm_engines(self):
        forbidden = ("tracking_hungarian", "tracking_BayesianTransformer")
        for path in (ROOT / "PyReconstruct").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for package_name in forbidden:
                for import_pattern in (
                    f"import {package_name}",
                    f"from {package_name}",
                ):
                    self.assertNotIn(
                        import_pattern,
                        source,
                        f"algorithm import leaked into host: {path}",
                    )


if __name__ == "__main__":
    unittest.main()
