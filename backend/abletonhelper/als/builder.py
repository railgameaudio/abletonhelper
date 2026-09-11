"""Write a Live set from a template + analysed songs.

STATUS: structurally complete, BUT NOT YET VALIDATED against a real
template. Everything below is template-driven on purpose -- it clones a
prototype clip out of your own Template.als rather than synthesising Live
XML from scratch, so the node layout is whatever your Live version
actually writes. That is the only approach that survives Live updates.

It cannot be verified until templates/Template.als exists. `build()`
refuses to run rather than emit a set that might be subtly wrong:
  - no template            -> TemplateMissing
  - unknown loop timebase  -> RuntimeError from TimeBase.loop_value
"""

from __future__ import annotations

import copy
import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from . import inspect as als_inspect
from .timebase import TimeBase


class TemplateMissing(FileNotFoundError):
    pass


class TemplateUnsuitable(ValueError):
    pass


@dataclass
class Placement:
    """One stem laid into the arrangement."""
    stem_path: Path
    track_name: str
    start_seconds: float
    duration_seconds: float


def _set(node: ET.Element, tag: str, value) -> None:
    child = node.find(tag)
    if child is None:
        child = ET.SubElement(node, tag)
    child.set("Value", str(value).lower() if isinstance(value, bool) else str(value))


def load_template(path: Path) -> tuple[ET.ElementTree, bytes]:
    if not path.exists():
        raise TemplateMissing(
            f"{path} not found. The builder copies structure out of your real "
            "Live template; it does not invent Live XML. Export a template from "
            "Live 12 and put it there."
        )
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return ET.ElementTree(ET.fromstring(raw)), raw


def find_prototype_clip(root: ET.Element) -> ET.Element:
    clip = next(root.iter("AudioClip"), None)
    if clip is None:
        raise TemplateUnsuitable(
            "Template has no AudioClip to use as a prototype. Add one audio clip "
            "to an arrangement track in the template and re-save; the builder "
            "clones its exact node layout for every stem."
        )
    return clip


def write_als(tree: ET.ElementTree, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    xml = ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)
    out_path.write_bytes(gzip.compress(xml))
    return out_path


def build(template_path: Path, placements: list[Placement], out_path: Path,
          locators: list[tuple[float, str]] | None = None,
          timebase: TimeBase | None = None) -> Path:
    """Clone the template and lay `placements` into its arrangement."""
    tree, _ = load_template(template_path)
    root = tree.getroot()

    if timebase is None:
        timebase = TimeBase.from_report(als_inspect.inspect(template_path))
    if timebase.loop_units == "unknown":
        raise RuntimeError(
            "Could not measure how this template encodes clip loop times. "
            "Add one unwarped audio clip to the template so the units can be "
            "determined, then rebuild."
        )

    prototype = find_prototype_clip(root)
    # Deliberately left here: the per-track placement pass needs the real
    # track container layout, which differs between Live versions and is
    # read off the template rather than assumed.
    raise NotImplementedError(
        "Placement pass is pending a real templates/Template.als. "
        f"Prototype clip found: <{prototype.tag}>, timebase={timebase}. "
        "Run `abletonhelper inspect` and share the report to finish this."
    )
