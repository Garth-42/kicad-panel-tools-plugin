"""The PCM zip must load the way pcbnew actually loads installed packages.

PCM extracts the zip's plugins/ tree into 3rdparty/plugins/<identifier>/ and
pcbnew imports that directory as ONE package -- but only if it carries a
top-level __init__.py. KiCad's PCM guidance also says the plugin itself must be
placed directly inside plugins/, not in a second-level subdirectory. Emulate the
loader, import the generated package, and assert the action plugin registers.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import types
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _ActionPlugin:
    registered = []

    def register(self):
        self.defaults()
        self.__class__.registered.append(self)


class _FakeWxApp:
    @staticmethod
    def GetInstance():
        return object()


def main():
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_pcm.py")],
                   check=True, stdout=subprocess.DEVNULL)
    out = os.path.join(ROOT, "dist", "harness_docs_pcm.zip")

    names = zipfile.ZipFile(out).namelist()
    assert "metadata.json" in names, "metadata.json must sit at the archive root"
    assert "plugins/__init__.py" in names, \
        "plugins/ needs a top-level __init__.py or pcbnew never imports the package"
    assert "plugins/core.py" in names, "action support must be directly in plugins/"
    assert "plugins/panel_device_wizard.py" in names, "wizard must be directly in plugins/"
    assert "plugins/review_dialog.py" in names, "native review editor must be bundled"
    assert "plugins/wire_numbers_dialog.py" in names, \
        "interactive wire-numbers dialog must be bundled"
    assert "plugins/icon.xpm" in names, "toolbar icon must be bundled next to the action plugin"
    assert not any(n.startswith("plugins/kicad_plugin/") for n in names), \
        "PCM action plugin must not be hidden inside a second-level plugin directory"

    tmp = tempfile.mkdtemp(prefix="pcm_pkg_")
    old_pcbnew = sys.modules.get("pcbnew")
    old_wx = sys.modules.get("wx")
    try:
        # Install like PCM: plugins/* -> 3rdparty/plugins/<identifier>/*.
        # Keep the dashes: pcbnew's loader must cope with non-identifier chars.
        pkg_dir = os.path.join(tmp, "com_github_garth-42_kicad-panel-tools-plugin")
        with zipfile.ZipFile(out) as z:
            for n in z.namelist():
                if n.startswith("plugins/") and not n.endswith("/"):
                    dest = os.path.join(pkg_dir, os.path.relpath(n, "plugins"))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(n) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        # Import like kicadplugins.i: the directory as one package, by path.
        # Shadowing matters: the extracted copies must win over the repo tree.
        for m in [m for m in sys.modules if m.split(".")[0] in
                  ("kicad_plugin", "harness") or m.startswith("com_github_pcm_test")]:
            del sys.modules[m]
        _ActionPlugin.registered.clear()
        sys.modules["pcbnew"] = types.SimpleNamespace(ActionPlugin=_ActionPlugin)
        sys.modules["wx"] = types.SimpleNamespace(App=_FakeWxApp)
        spec = importlib.util.spec_from_file_location(
            "com_github_pcm_test", os.path.join(pkg_dir, "__init__.py"),
            submodule_search_locations=[pkg_dir])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        assert hasattr(mod, "HarnessDocsPlugin")
        assert hasattr(mod, "WireNamesPlugin")
        assert len(_ActionPlugin.registered) == 2
        plugin = _ActionPlugin.registered[0]
        wire_plugin = _ActionPlugin.registered[1]
        assert plugin.name == "Generate harness docs"
        assert plugin.show_toolbar_button is True
        assert plugin.icon_file_name.endswith("icon.xpm")
        assert os.path.exists(plugin.icon_file_name)
        assert wire_plugin.name == "Generate wire numbers"
        assert wire_plugin.show_toolbar_button is True
        assert wire_plugin.icon_file_name.endswith("icon.xpm")
        assert os.path.exists(wire_plugin.icon_file_name)
        assert "com_github_pcm_test.panel_device_wizard" in sys.modules, \
            "wizard module must be imported so it can self-register"
        h = sys.modules.get("harness")
        assert h is not None and os.path.realpath(h.__file__).startswith(
            os.path.realpath(pkg_dir)), "harness must resolve from the package"
    finally:
        if old_pcbnew is None:
            sys.modules.pop("pcbnew", None)
        else:
            sys.modules["pcbnew"] = old_pcbnew
        if old_wx is None:
            sys.modules.pop("wx", None)
        else:
            sys.modules["wx"] = old_wx
        shutil.rmtree(tmp, ignore_errors=True)

    print("OK pcm package loads and registers from the top-level plugins directory")


if __name__ == "__main__":
    main()
