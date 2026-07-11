"""Ingest KiCad connectivity from an exported netlist XML.

Produce the netlist with either:
    kicad-cli sch export netlist --format kicadxml -o out.net.xml design.kicad_sch
or an eeschema BOM/netlist export command. The 'kicadxml' intermediate format is
the same one BOM generators consume: <export><components/><nets/></export>.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from .base import ConnectivitySource
from ..model import Connectivity, Component, Net, Node


class KicadNetlistSource(ConnectivitySource):
    def __init__(self, path: str):
        self.path = path

    def load(self) -> Connectivity:
        root = ET.parse(self.path).getroot()
        conn = Connectivity()

        comps = root.find("components")
        if comps is not None:
            for comp in comps.findall("comp"):
                ref = comp.get("ref", "")
                value = (comp.findtext("value") or "").strip()
                fields = {}
                fnode = comp.find("fields")
                if fnode is not None:
                    for f in fnode.findall("field"):
                        if f.get("name"):
                            fields[f.get("name")] = (f.text or "").strip()
                conn.components[ref] = Component(ref=ref, value=value, fields=fields)

        nets = root.find("nets")
        if nets is not None:
            for net in nets.findall("net"):
                # KiCad 9/10 kicad-cli emits the net class (composite, same
                # "X,Default" form the board reports); older exports lack it.
                n = Net(code=net.get("code", ""), name=net.get("name", ""),
                        netclass=net.get("class", "") or "")
                for node in net.findall("node"):
                    n.nodes.append(Node(
                        ref=node.get("ref", ""),
                        pin=node.get("pin", ""),
                        pinfunction=node.get("pinfunction", "") or "",
                    ))
                conn.nets.append(n)
        return conn
