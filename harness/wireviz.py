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


class GraphvizDotNotFound(RuntimeError):
    """Raised when WireViz is importable but Graphviz ``dot`` is unavailable."""


def _candidate_dot_paths() -> list[str]:
    """Return likely Graphviz ``dot`` executable locations for this machine."""
    candidates = []
    for env_name in ("KICAD_PANEL_TOOLS_DOT", "GRAPHVIZ_DOT"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(value)

    dot = shutil.which("dot")
    if dot:
        candidates.append(dot)

    if os.name == "nt":
        for base in (
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if base:
                candidates.append(os.path.join(base, "Graphviz", "bin", "dot.exe"))
        candidates.extend(
            os.path.join(drive + ":\\", "Program Files", "Graphviz", "bin", "dot.exe")
            for drive in ("C", "D")
        )
    else:
        candidates.extend(("/opt/homebrew/bin/dot", "/usr/local/bin/dot", "/usr/bin/dot"))

    seen = set()
    unique = []
    for candidate in candidates:
        candidate = os.path.abspath(os.path.expanduser(candidate))
        if candidate not in seen:
            unique.append(candidate)
            seen.add(candidate)
    return unique


def _can_run_dot(path: str) -> bool:
    try:
        proc = subprocess.run(
            [path, "-V"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def graphviz_dot_path() -> str | None:
    """Return a runnable Graphviz ``dot`` executable for this Python process."""
    for candidate in _candidate_dot_paths():
        if os.path.isfile(candidate) and _can_run_dot(candidate):
            return candidate
    return None


def _ensure_dot_on_path(dot: str) -> None:
    """Make a discovered ``dot`` visible to renderers that shell out by name."""
    dot_dir = os.path.dirname(dot)
    path_parts = (os.environ.get("PATH") or "").split(os.pathsep)
    if dot_dir and dot_dir not in path_parts:
        os.environ["PATH"] = os.pathsep.join([dot_dir] + [p for p in path_parts if p])


def graphviz_missing_message() -> str:
    """Explain why WireViz rendering needs more than the Python package."""
    path = os.environ.get("PATH") or "<empty>"
    return (
        "Graphviz 'dot' executable not found or not runnable from this Python process. "
        "The Python packages `wireviz` and `graphviz` can import successfully, but "
        "they still need the separate Graphviz `dot` program to draw PNG/SVG/HTML "
        "diagrams. Install Graphviz (graphviz.org), restart KiCad so it receives the "
        "updated PATH, or set KICAD_PANEL_TOOLS_DOT/GRAPHVIZ_DOT to the full path of "
        f"dot. sys.executable={sys.executable!r}; PATH={path!r}; "
        f"checked={_candidate_dot_paths()!r}"
    )


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

    When Graphviz ``dot`` is available, the real WireViz Python API is used
    first, followed by the WireViz CLI. The bundled fallback renderer handles
    the subset emitted by this project and can write SVG/HTML/BOM outputs even
    when Graphviz is not installed, so a PCM-only install still produces docs.
    """
    yaml_path = os.path.abspath(yaml_path)
    dot = graphviz_dot_path()
    if dot is not None:
        _ensure_dot_on_path(dot)
        for renderer in (_render_with_wireviz_api, _render_with_wireviz_cli):
            rendered = renderer(yaml_path)
            if rendered is not None:
                return rendered

    yaml = import_yaml()
    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return wireviz_renderer.render(data, yaml_path, dot=dot)
