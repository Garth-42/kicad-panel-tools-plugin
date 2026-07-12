#!/usr/bin/env python3
"""Build the KiCad Plugin-and-Content-Manager (PCM) package.

    python3 scripts/build_pcm.py        ->  dist/harness_docs_pcm.zip

Zip layout (what PCM expects):
    metadata.json
    resources/icon.png
    plugins/__init__.py          generated action plugin entry point
    plugins/core.py              plugin implementation support
    plugins/panel_device_wizard.py
    plugins/review_dialog.py
    plugins/icon.xpm              action toolbar icon
    plugins/harness/...          engine (incl. vendored yaml fallback)

Install: KiCad -> Plugin and Content Manager -> Install from File...

PCM installs the plugins/ tree into 3rdparty/plugins/<identifier>/. KiCad's
PCM guidance says the plugin itself must live directly inside that plugins
directory, not inside a second-level subdirectory. The package `__init__.py`
is therefore copied to the PCM top level. The shared entry point adds both its
own directory and the repository root to `sys.path`, so it works from a source
checkout and from the extracted PCM package.
"""
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(DIST, "harness_docs_pcm.zip")

SKIP_DIRS = {"__pycache__"}
SKIP_EXT = {".pyc"}


def _add_tree(z, src_dir, arc_prefix):
    for base, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            if os.path.splitext(f)[1] in SKIP_EXT:
                continue
            full = os.path.join(base, f)
            rel = os.path.relpath(full, src_dir)
            z.write(full, os.path.join(arc_prefix, rel))


def main():
    meta_path = os.path.join(ROOT, "pcm", "metadata.json")
    meta = json.load(open(meta_path))          # validates JSON
    version = meta["versions"][0]["version"]

    os.makedirs(DIST, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(meta_path, "metadata.json")
        z.write(os.path.join(ROOT, "pcm", "icon.png"), "resources/icon.png")
        for name in ("__init__.py", "core.py", "panel_device_wizard.py", "review_dialog.py", "__main__.py", "icon.xpm"):
            z.write(os.path.join(ROOT, "kicad_plugin", name), os.path.join("plugins", name))
        _add_tree(z, os.path.join(ROOT, "harness"), "plugins/harness")

    names = zipfile.ZipFile(OUT).namelist()
    assert "metadata.json" in names
    assert "plugins/__init__.py" in names
    assert "plugins/core.py" in names
    assert "plugins/panel_device_wizard.py" in names
    assert "plugins/review_dialog.py" in names
    assert "plugins/icon.xpm" in names
    assert "plugins/kicad_plugin/__init__.py" not in names
    assert "plugins/harness/engine.py" in names
    assert "plugins/harness/_vendor/yaml/__init__.py" in names
    size_kb = os.path.getsize(OUT) // 1024
    print(f"{os.path.relpath(OUT, ROOT)}  v{version}  "
          f"({len(names)} files, {size_kb} KiB)")


if __name__ == "__main__":
    main()
