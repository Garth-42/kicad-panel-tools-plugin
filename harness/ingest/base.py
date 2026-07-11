"""The swap point. Any connectivity source implements load() -> Connectivity.

Today: KicadNetlistSource (file/export based, works on KiCad 9/10).
Later: KicadIpcSource (live, interactive) once the schematic IPC API exists.
The engine depends only on this interface, so adding the IPC source later is a
drop-in with zero changes above this layer.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from ..model import Connectivity


class ConnectivitySource(ABC):
    @abstractmethod
    def load(self) -> Connectivity:
        ...
