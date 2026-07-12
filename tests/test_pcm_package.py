"""The PCM zip must load the way pcbnew actually loads installed packages.

PCM extracts the zip's plugins/ tree into 3rdparty/plugins/<identifier>/ and
pcbnew imports that directory as ONE package -- but only if it carries a
top-level __init__.py (this was missed once: the package installed cleanly
yet nothing appeared under Tools -> External Plugins). Emulate that loader:
build the zip, extract plugins/ into a dir named like a munged identifier,
import its __init__ via importlib the way kicadplugins.i does, and assert
the action plugin + wizard modules actually got imported.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_pcm.py")],
                   check=True, stdout=subprocess.DEVNULL)
    out = os.path.join(ROOT, "dist", "harness_docs_pcm.zip")

    names = zipfile.ZipFile(out).namelist()
    assert "metadata.json" in names, "metadata.json must sit at the archive root"
    assert "plugins/__init__.py" in names, \
        "plugins/ needs a top-level __init__.py or pcbnew never imports the package"

    tmp = tempfile.mkdtemp(prefix="pcm_pkg_")
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
                  ("kicad_plugin", "harness")]:
            del sys.modules[m]
        spec = importlib.util.spec_from_file_location(
            "com_github_pcm_test", os.path.join(pkg_dir, "__init__.py"),
            submodule_search_locations=[pkg_dir])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        kp = sys.modules.get("kicad_plugin")
        assert kp is not None, "PCM __init__ must import kicad_plugin"
        assert os.path.realpath(kp.__file__).startswith(os.path.realpath(pkg_dir)), \
            f"imported the repo tree, not the extracted package: {kp.__file__}"
        assert hasattr(kp, "HarnessDocsPlugin")
        assert "kicad_plugin.panel_device_wizard" in sys.modules, \
            "wizard module must be imported so it can self-register"
        h = sys.modules.get("harness")
        assert h is not None and os.path.realpath(h.__file__).startswith(
            os.path.realpath(pkg_dir)), "harness must resolve from the package"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("OK pcm package loads via the pcbnew 3rdparty loader path")


if __name__ == "__main__":
    main()
