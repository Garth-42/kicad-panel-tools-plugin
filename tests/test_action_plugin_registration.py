"""Action plugins register only when a wx application handle exists.

KiCad 10 asserts in C++ if ActionPlugin.register() runs before its GUI
application handle exists. Headless imports must therefore be side-effect safe,
while GUI imports should still register both toolbar/menu actions.
"""
import importlib
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class _ActionPlugin:
    registered = []

    def register(self):
        self.defaults()
        self.__class__.registered.append(self)


class _FakeWxApp:
    @staticmethod
    def GetInstance():
        return object()


def _clear_plugin_modules():
    for name in [m for m in sys.modules if m == "kicad_plugin" or m.startswith("kicad_plugin.")]:
        del sys.modules[name]


def _import_with_fake_environment(wx_module):
    _clear_plugin_modules()
    _ActionPlugin.registered.clear()
    sys.modules["pcbnew"] = types.SimpleNamespace(ActionPlugin=_ActionPlugin)
    if wx_module is None:
        sys.modules.pop("wx", None)
    else:
        sys.modules["wx"] = wx_module
    return importlib.import_module("kicad_plugin")


def main():
    old_pcbnew = sys.modules.get("pcbnew")
    old_wx = sys.modules.get("wx")
    try:
        mod = _import_with_fake_environment(types.SimpleNamespace(GetApp=lambda: None))
        assert len(_ActionPlugin.registered) == 0
        assert hasattr(mod, "HarnessDocsPlugin")
        assert hasattr(mod, "WireNamesPlugin")

        mod = _import_with_fake_environment(types.SimpleNamespace(App=_FakeWxApp))
        assert len(_ActionPlugin.registered) == 2
        plugin = _ActionPlugin.registered[0]
        wire_plugin = _ActionPlugin.registered[1]
        assert plugin.name == "Generate harness docs"
        assert plugin.category == "Documentation"
        assert plugin.show_toolbar_button is True
        assert plugin.icon_file_name.endswith(os.path.join("kicad_plugin", "icon.xpm"))
        assert os.path.exists(plugin.icon_file_name)
        assert wire_plugin.name == "Apply wire numbers to net names"
        assert wire_plugin.show_toolbar_button is True
        assert wire_plugin.icon_file_name.endswith(os.path.join("kicad_plugin", "icon.xpm"))
        assert os.path.exists(wire_plugin.icon_file_name)
        assert hasattr(mod, "HarnessDocsPlugin")
        assert hasattr(mod, "WireNamesPlugin")
    finally:
        if old_pcbnew is None:
            sys.modules.pop("pcbnew", None)
        else:
            sys.modules["pcbnew"] = old_pcbnew
        if old_wx is None:
            sys.modules.pop("wx", None)
        else:
            sys.modules["wx"] = old_wx
        _clear_plugin_modules()

    print("OK action plugin registration is GUI-gated and registers with wx.App")


if __name__ == "__main__":
    main()
