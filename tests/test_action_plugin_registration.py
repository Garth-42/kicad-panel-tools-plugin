"""The action plugin must register even if wx.GetApp() is not visible yet.

KiCad/PCM can import plugin packages during refresh before a wx.App is exposed to
Python.  The menu entry under Tools -> External Plugins is created by
ActionPlugin.register(), so import-time registration must not be gated on wx.
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


def main():
    for name in [m for m in sys.modules if m == "kicad_plugin" or m.startswith("kicad_plugin.")]:
        del sys.modules[name]

    fake_pcbnew = types.SimpleNamespace(ActionPlugin=_ActionPlugin)
    sys.modules["pcbnew"] = fake_pcbnew

    fake_wx = types.SimpleNamespace(GetApp=lambda: None)
    sys.modules["wx"] = fake_wx

    try:
        mod = importlib.import_module("kicad_plugin")
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
        sys.modules.pop("pcbnew", None)
        sys.modules.pop("wx", None)
        for name in [m for m in sys.modules if m == "kicad_plugin" or m.startswith("kicad_plugin.")]:
            del sys.modules[name]

    print("OK action plugin registers without requiring wx.GetApp()")


if __name__ == "__main__":
    main()
