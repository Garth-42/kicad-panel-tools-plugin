"""v2 seam: live ingest via the KiCad schematic IPC API.

As of KiCad 9/10 the IPC API (kicad-python / kipy) covers only the PCB editor;
schematic-editor support is planned but not yet shipped, and headless operation
lands in KiCad 11. When schematic support arrives, implement load() here to pull
components/pins/nets from a running KiCad session. Nothing above this file needs
to change -- it already programs against ConnectivitySource.

Sketch of the eventual implementation:

    from kipy import KiCad
    class KicadIpcSource(ConnectivitySource):
        def load(self) -> Connectivity:
            kicad = KiCad()                       # connects to running instance
            sch = kicad.get_schematic()           # <-- not available yet
            ... walk symbols/pins/nets -> Connectivity ...
"""
from __future__ import annotations
from .base import ConnectivitySource
from ..model import Connectivity


class KicadIpcSource(ConnectivitySource):
    def __init__(self, *_, **__):
        pass

    def load(self) -> Connectivity:
        raise NotImplementedError(
            "The KiCad schematic IPC API is not available in KiCad 9/10. "
            "Use KicadNetlistSource for now; implement this adapter when "
            "schematic API support ships (targeted post-10)."
        )
