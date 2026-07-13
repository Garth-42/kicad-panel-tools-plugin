"""Render WireViz YAML, preferring real WireViz and falling back to bundled support."""
from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys

from .yamlio import import_yaml
from ._vendor import wireviz_renderer

_OUTPUT_EXTS = (".png", ".svg", ".html", ".bom.tsv")

# GUI-launched apps on macOS/Windows inherit a minimal PATH that misses the
# usual install prefixes, so KiCad can't see a `wireviz`/`dot` that works fine
# in a terminal (Homebrew, MacPorts, the Graphviz MSI).
if sys.platform == "darwin":
    _EXTRA_TOOL_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")
elif sys.platform.startswith("win"):
    _EXTRA_TOOL_DIRS = (r"C:\Program Files\Graphviz\bin",)
else:
    _EXTRA_TOOL_DIRS = ()


def _extend_path_for_tools():
    """Add known tool prefixes to PATH so wireviz/dot are found.

    Mutating os.environ (not just probing) is deliberate: the WireViz Python
    API and CLI spawn `dot` themselves via PATH, so a lookup on our side alone
    wouldn't help them.
    """
    parts = [p for p in (os.environ.get("PATH") or "").split(os.pathsep) if p]
    extra = [d for d in _EXTRA_TOOL_DIRS if os.path.isdir(d) and d not in parts]
    if extra:
        os.environ["PATH"] = os.pathsep.join(parts + extra)


def _expected_outputs(yaml_path: str) -> list[str]:
    stem, _ = os.path.splitext(os.path.abspath(yaml_path))
    return [stem + ext for ext in _OUTPUT_EXTS]


def _find_wireviz_api():
    """Return a WireViz ``parse`` callable from installed or vendored WireViz."""
    for package_name, module_name in (
        ("wireviz", "wireviz.wireviz"),
        ("harness._vendor.wireviz", "harness._vendor.wireviz.wireviz"),
    ):
        if importlib.util.find_spec(package_name) is None:
            continue
        if importlib.util.find_spec(module_name) is None:
            continue
        module = importlib.import_module(module_name)
        parse = getattr(module, "parse", None)
        if callable(parse):
            return parse
    return None


def _render_with_wireviz_api(yaml_path: str) -> list[str] | None:
    parse = _find_wireviz_api()
    if parse is None:
        return None
    output_dir = os.path.dirname(os.path.abspath(yaml_path))
    output_name = os.path.splitext(os.path.basename(yaml_path))[0]
    parse(
        yaml_path,
        output_formats=("png", "svg", "html", "tsv"),
        output_dir=output_dir,
        output_name=output_name,
    )
    return _expected_outputs(yaml_path)


def _render_with_wireviz_cli(yaml_path: str) -> list[str] | None:
    cli = shutil.which("wireviz")
    if not cli:
        return None
    proc = subprocess.run(
        [cli, os.path.abspath(yaml_path)],
        cwd=os.path.dirname(os.path.abspath(yaml_path)),
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "wireviz failed")
    return _expected_outputs(yaml_path)


def render_wireviz(yaml_path: str) -> list[str]:
    """Render ``yaml_path`` to PNG/SVG/HTML/BOM outputs.

    The real WireViz Python API is used first, whether installed normally or
    vendored under ``harness._vendor.wireviz``. The WireViz CLI is used next
    when available. The bundled fallback renderer handles the subset emitted by
    this project. All paths require Graphviz ``dot`` for image generation.
    """
    yaml_path = os.path.abspath(yaml_path)
    _extend_path_for_tools()
    for renderer in (_render_with_wireviz_api, _render_with_wireviz_cli):
        rendered = renderer(yaml_path)
        if rendered is not None:
            return rendered

    yaml = import_yaml()
    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return wireviz_renderer.render(data, yaml_path)
