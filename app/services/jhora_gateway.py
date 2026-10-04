"""The one place PyJHora is called from.

Two problems have to be solved before any PyJHora function that computes its own
positions can be trusted, and both are solved here so no caller has to remember
them.

1. swisseph arity. PyJHora unpacks "longi, _ = swe.calc_ut(...)" at all 12 of its
   call sites, but the installed pyswisseph returns a 3-tuple
   (values, retflag, serr). Every PyJHora feature that computes positions -
   divisional charts, shadbala, ashtakavarga, doshas, vratha dates, moon phases,
   retrogrades - therefore raises "too many values to unpack" out of the box.
   _install_swisseph_shim gives the jhora modules a view of swisseph whose
   calc_ut returns the 2-tuple they expect. It is deliberately scoped to modules
   named "jhora*": this app's own swisseph calls still see the real 3-tuple.

2. Ayanamsha and node defaults. PyJHora's drik defaults to TRUE_PUSHYA with true
   nodes, roughly 1 degree 08 minutes from this app's Lahiri with mean nodes.
   jhora_context forces the app's convention before a call and restores swisseph
   afterwards, because sid_mode is global process state.
"""

from __future__ import annotations

import io
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Any

import swisseph as _swe

with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    from jhora import utils as jhora_utils
    from jhora.panchanga import drik, eclipse, vratha


class _SwissephShim:
    """swisseph as PyJHora expects it: calc_ut returns (values, retflag)."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_swe, name)

    def calc_ut(self, *args: Any, **kwargs: Any) -> Any:
        result = _swe.calc_ut(*args, **kwargs)
        return (result[0], result[1]) if len(result) >= 2 else result


def _install_swisseph_shim() -> int:
    shim = _SwissephShim()
    patched = 0
    for name, module in list(sys.modules.items()):
        if name.startswith("jhora") and getattr(module, "swe", None) is _swe:
            module.swe = shim  # type: ignore[attr-defined]
            patched += 1
    return patched


PATCHED_MODULE_COUNT = _install_swisseph_shim()


@contextmanager
def quiet():
    """PyJHora prints diagnostics from inside its calculations; keep them off
    the server log."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        yield


@contextmanager
def jhora_context(ayanamsha: str = "LAHIRI", true_nodes: bool = False):
    """Run a PyJHora call under this app's ayanamsha and node convention.

    Restores swisseph's sid_mode afterwards, because it is global process state
    and this app's own calculations run alongside.

    Deliberately does NOT redirect stdout around the body: swallowing a caller's
    own logging would be a trap. Compose with quiet() when calling a noisy
    PyJHora function - "with jhora_context(), quiet():".
    """
    with quiet():
        try:
            drik.set_ayanamsa_mode(ayanamsha)
        except Exception:
            pass
        try:
            drik.set_planet_list(set_rahu_ketu_as_true_nodes=true_nodes)
        except Exception:
            pass
    try:
        yield
    finally:
        with quiet():
            # The app computes with SIDM_LAHIRI; put swisseph back to it.
            _swe.set_sid_mode(_swe.SIDM_LAHIRI, 0, 0)


def place_of(latitude: float, longitude: float, timezone_offset_hours: float, label: str = ""):
    """PyJHora wants a fixed UTC offset in hours, not an IANA zone name."""
    return drik.Place(label or "place", latitude, longitude, timezone_offset_hours)


def utc_offset_hours(timezone_name: str, on: date_type) -> float:
    """The offset actually in force on that date, so DST is respected."""
    from dateutil import tz

    zone = tz.gettz(timezone_name)
    if zone is None:
        raise ValueError("Unsupported timezone.")
    moment = datetime(on.year, on.month, on.day, 12, 0, tzinfo=zone)
    offset = moment.utcoffset()
    if offset is None:
        raise ValueError("Unsupported timezone.")
    return offset.total_seconds() / 3600


def julian_day(on: date_type) -> float:
    with quiet():
        return jhora_utils.julian_day_number(drik.Date(on.year, on.month, on.day), (0, 0, 0))


def float_hours_to_hhmm(value: float) -> str:
    """PyJHora returns local clock times as float hours, sometimes negative
    (before midnight) or past 24 (after it)."""
    minutes = int(round(value * 60)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def ymd_hours_to_iso(year: int, month: int, day: int, hours: float) -> str | None:
    """PyJHora pads absent eclipse phases with julian day 0, which revjul turns
    into the year -4713. Those are not events; drop them."""
    if year < 1:
        return None
    base = datetime(year, month, day, tzinfo=timezone.utc)
    return (base + timedelta(hours=hours)).replace(microsecond=0).isoformat()


__all__ = [
    "PATCHED_MODULE_COUNT",
    "drik",
    "eclipse",
    "vratha",
    "quiet",
    "jhora_context",
    "place_of",
    "utc_offset_hours",
    "julian_day",
    "float_hours_to_hhmm",
    "ymd_hours_to_iso",
]
