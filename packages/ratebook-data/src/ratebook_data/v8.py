"""Un-flatten a ``raw.urdb`` CSV row into URDB v8 nested JSON.

The bulk CSV flattens the rate structure into ~600 sparse columns named
``energyratestructure/period{p}/tier{t}{field}``. This reverses that into the nested
``[[{rate,adj,max,unit,sell}, ...], ...]`` shape that both PySAM's converter and Ratebook's
``ratebook.urdb.tariff_from_v8`` consume — one un-flattening, two consumers.
"""

from __future__ import annotations

import json
import re
from typing import Any

_CELL = re.compile(
    r"^(energy|demand|flatdemand|coincident)ratestructure/period(\d+)/tier(\d+)(\w+)$"
)
_FLAT_CELL = re.compile(r"^flatdemandstructure/period(\d+)/tier(\d+)(\w+)$")

_STRUCTURE_KEY = {
    "energy": "energyratestructure",
    "demand": "demandratestructure",
    "coincident": "coincidentratestructure",
}

#: Scalar columns carried through verbatim into the v8 record.
_SCALARS = (
    "label",
    "name",
    "utility",
    "eiaid",
    "sector",
    "startdate",
    "enddate",
    "latest_update",
    "source",
    "dgrules",
    "fixedchargefirstmeter",
    "fixedchargeunits",
    "mincharge",
    "minchargeunits",
    "rateno",
)


def _nonempty(value: Any) -> bool:
    return value is not None and value != ""


def _grow(grid: list[list[dict[str, Any]]], p: int, t: int) -> dict[str, Any]:
    while len(grid) <= p:
        grid.append([])
    while len(grid[p]) <= t:
        grid[p].append({})
    return grid[p][t]


def row_to_v8(row: dict[str, Any]) -> dict[str, Any]:
    """Re-nest a flat ``raw.urdb`` row dict into a URDB v8 JSON record."""
    out: dict[str, Any] = {}
    structures: dict[str, list[list[dict[str, Any]]]] = {}
    flatdemand: list[list[dict[str, Any]]] = []

    for key, value in row.items():
        if not _nonempty(value):
            continue

        m = _CELL.match(key)
        if m:
            family, p, t, field = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            grid = structures.setdefault(_STRUCTURE_KEY[family], [])
            _grow(grid, p, t)[field] = value
            continue

        fm = _FLAT_CELL.match(key)
        if fm:
            p, t, field = int(fm.group(1)), int(fm.group(2)), fm.group(3)
            _grow(flatdemand, p, t)[field] = value
            continue

        if key in ("energyweekdayschedule", "energyweekendschedule"):
            out[key] = json.loads(value)
            continue

        if key in _SCALARS:
            out[key] = value

    out.update(structures)
    if flatdemand:
        out["flatdemandstructure"] = flatdemand
    return out
