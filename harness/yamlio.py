"""YAML import chooser: system PyYAML if available, else the vendored copy.

KiCad's bundled Python often lacks PyYAML, and that used to mean no spec file
and no WireViz output there. The pure-Python PyYAML vendored under `_vendor/`
removes that failure mode entirely; an installed PyYAML still wins (it may be
newer and C-accelerated).
"""
from __future__ import annotations


def import_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        from ._vendor import yaml as vendored
        return vendored
