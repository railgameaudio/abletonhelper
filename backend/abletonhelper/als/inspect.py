"""Read a Live .als and report its real structure.

An .als is gzipped XML. Nothing here guesses at node names -- it reports
what is actually present so assumptions can be checked against a real
template rather than against memory of the format.

The headline question this answers:

    For an UNWARPED audio clip, are Loop/LoopStart, LoopEnd, StartRelative
    and CurrentStart/CurrentEnd expressed in BEATS or in SECONDS?

The empirical test (`timebase_evidence`) does not assume either. It takes
the clip's loop length in file units and compares it against the sample's
true length in seconds, which is derivable from SampleRef metadata
(DefaultDuration frames / SampleRate). If the ratio is ~1.0 the units are
seconds; if it is ~tempo/60 the units are beats. Anything else means the
clip is trimmed and the report says so instead of pretending.
"""

from __future__ import annotations

import gzip
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path


def load_xml(path: str | Path) -> ET.Element:
    """Parse a .als (gzipped) or a plain .xml dump of one."""
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return ET.fromstring(raw)


def _val(node: ET.Element | None, default=None):
    """Live stores scalars as <Thing Value="..."/>."""
    if node is None:
        return default
    if "Value" in node.attrib:
        return node.attrib["Value"]
    return node.text if node.text and node.text.strip() else default


def _num(node, default=None):
    v = _val(node)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _bool(node, default=None):
    v = _val(node)
    if v is None:
        return default
    return str(v).lower() == "true"


@dataclass
class ClipReport:
    track: str
    kind: str                      # AudioClip | MidiClip
    name: str | None
    is_warped: bool | None
    # raw timing fields, exactly as they appear
    current_start: float | None
    current_end: float | None
    loop_start: float | None
    loop_end: float | None
    start_relative: float | None
    hidden_loop_start: float | None
    hidden_loop_end: float | None
    # sample facts
    sample_path: str | None
    sample_frames: float | None
    sample_rate: float | None
    sample_seconds: float | None
    # derived
    loop_length_units: float | None
    timebase_verdict: str


@dataclass
class TemplateReport:
    path: str
    live_version: str | None
    minor_version: str | None
    tempo: float | None
    time_signature: str | None
    tracks: list[dict]
    clips: list[ClipReport]
    locators: list[dict]
    notes: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _tempo(root: ET.Element) -> float | None:
    # Live 9+: MasterTrack/.../Tempo/Manual, older: Tempo/ArrangerAutomation
    for xp in (
        ".//MasterTrack//Tempo/Manual",
        ".//MainTrack//Tempo/Manual",
        ".//Tempo/Manual",
        ".//Tempo/ArrangerAutomation/Events/FloatEvent",
    ):
        n = root.find(xp)
        v = _num(n)
        if v:
            return v
    return None


def _sample_seconds(clip: ET.Element) -> tuple[str | None, float | None, float | None, float | None]:
    """(path, frames, rate, seconds) from whichever SampleRef layout is present."""
    ref = clip.find(".//SampleRef")
    if ref is None:
        return None, None, None, None

    frames = _num(ref.find("./DefaultDuration"))
    rate = _num(ref.find("./DefaultSampleRate"))

    fi = ref.find("./FileRef")
    path = None
    if fi is not None:
        path = _val(fi.find("./Path")) or _val(fi.find("./Name"))
        if path is None:
            # Live 11/12 store the absolute path in RelativePath segments
            segs = [_val(d.find("./Name")) for d in fi.findall("./RelativePath/RelativePathElement")]
            segs = [s for s in segs if s]
            if segs:
                path = "/".join(segs) + "/" + (_val(fi.find("./Name")) or "")
    seconds = (frames / rate) if (frames and rate) else None
    return path, frames, rate, seconds


def timebase_evidence(loop_len: float | None, sample_seconds: float | None,
                      tempo: float | None, is_warped: bool | None) -> str:
    """Decide beats vs seconds from numbers, not from assumption."""
    if loop_len is None:
        return "no loop length in clip - cannot test"
    if sample_seconds is None:
        return "no SampleRef duration - cannot test"
    if not tempo:
        return "no tempo found - cannot test beats hypothesis"

    ratio_seconds = loop_len / sample_seconds
    beats_for_sample = sample_seconds * tempo / 60.0
    ratio_beats = loop_len / beats_for_sample if beats_for_sample else 0.0

    def close(x: float) -> bool:
        return 0.98 <= x <= 1.02

    if close(ratio_seconds) and not close(ratio_beats):
        return (f"SECONDS (loop_len {loop_len:.4f} ~= sample {sample_seconds:.4f}s; "
                f"beats hypothesis would need {beats_for_sample:.4f})")
    if close(ratio_beats) and not close(ratio_seconds):
        return (f"BEATS (loop_len {loop_len:.4f} ~= {beats_for_sample:.4f} beats "
                f"at {tempo:.3f} BPM; seconds hypothesis would need {sample_seconds:.4f})")
    if close(ratio_seconds) and close(ratio_beats):
        return ("AMBIGUOUS - tempo is 60 BPM so beats and seconds coincide; "
                "retest with a template at any other tempo")
    return (f"INCONCLUSIVE - clip is probably trimmed. loop_len={loop_len:.4f}, "
            f"sample={sample_seconds:.4f}s, ={beats_for_sample:.4f} beats @ {tempo:.3f} BPM "
            f"(ratios {ratio_seconds:.4f} / {ratio_beats:.4f}). "
            f"warped={is_warped}")


def inspect(path: str | Path) -> TemplateReport:
    root = load_xml(path)
    tempo = _tempo(root)
    notes: list[str] = []

    tracks = []
    for tag in ("AudioTrack", "MidiTrack", "ReturnTrack", "GroupTrack"):
        for t in root.iter(tag):
            name = _val(t.find("./Name/EffectiveName")) or _val(t.find("./Name/UserName"))
            tracks.append({
                "type": tag,
                "id": t.attrib.get("Id"),
                "name": name,
                "n_devices": len(t.findall(".//Devices/*")),
            })

    clips: list[ClipReport] = []
    for tag in ("AudioClip", "MidiClip"):
        for c in root.iter(tag):
            owner = "?"
            for t in root.iter():
                if t.tag.endswith("Track") and c in list(t.iter()):
                    owner = (_val(t.find("./Name/EffectiveName"))
                             or t.attrib.get("Id") or t.tag)
                    break
            spath, frames, rate, secs = _sample_seconds(c)
            ls = _num(c.find("./Loop/LoopStart"))
            le = _num(c.find("./Loop/LoopEnd"))
            loop_len = (le - ls) if (ls is not None and le is not None) else None
            warped = _bool(c.find("./IsWarped"))
            clips.append(ClipReport(
                track=owner,
                kind=tag,
                name=_val(c.find("./Name")),
                is_warped=warped,
                current_start=_num(c.find("./CurrentStart")),
                current_end=_num(c.find("./CurrentEnd")),
                loop_start=ls,
                loop_end=le,
                start_relative=_num(c.find("./Loop/StartRelative")),
                hidden_loop_start=_num(c.find("./Loop/HiddenLoopStart")),
                hidden_loop_end=_num(c.find("./Loop/HiddenLoopEnd")),
                sample_path=spath,
                sample_frames=frames,
                sample_rate=rate,
                sample_seconds=secs,
                loop_length_units=loop_len,
                timebase_verdict=timebase_evidence(loop_len, secs, tempo, warped),
            ))

    locators = [{
        "time": _num(l.find("./Time")),
        "name": _val(l.find("./Name")),
    } for l in root.iter("Locator")]

    if not clips:
        notes.append("Template contains no clips. The builder needs at least one "
                     "audio clip to copy timing structure from -- add one to the "
                     "template, or timing fields must be synthesised blind.")
    if tempo is None:
        notes.append("No tempo node found; checked MasterTrack/MainTrack/Tempo paths.")

    return TemplateReport(
        path=str(path),
        live_version=root.attrib.get("Creator"),
        minor_version=root.attrib.get("MinorVersion"),
        tempo=tempo,
        time_signature=_val(root.find(".//TimeSignature//Numerator")),
        tracks=tracks,
        clips=clips,
        locators=locators,
        notes=notes,
    )


def format_report(r: TemplateReport) -> str:
    L = []
    L.append(f"file           : {r.path}")
    L.append(f"creator        : {r.live_version}")
    L.append(f"minor version  : {r.minor_version}")
    L.append(f"tempo          : {r.tempo}")
    L.append(f"time signature : {r.time_signature}")
    L.append(f"tracks         : {len(r.tracks)}")
    for t in r.tracks:
        L.append(f"   [{t['type']:11s}] id={t['id']!s:>4}  {t['name']!r}  devices={t['n_devices']}")
    L.append(f"locators       : {len(r.locators)}")
    for l in r.locators:
        L.append(f"   {l['time']}  {l['name']!r}")
    L.append(f"clips          : {len(r.clips)}")
    for c in r.clips:
        L.append(f"   --- {c.kind} on {c.track!r} name={c.name!r}")
        L.append(f"       IsWarped        = {c.is_warped}")
        L.append(f"       CurrentStart    = {c.current_start}")
        L.append(f"       CurrentEnd      = {c.current_end}")
        L.append(f"       Loop/LoopStart  = {c.loop_start}")
        L.append(f"       Loop/LoopEnd    = {c.loop_end}")
        L.append(f"       StartRelative   = {c.start_relative}")
        L.append(f"       HiddenLoopStart = {c.hidden_loop_start}")
        L.append(f"       HiddenLoopEnd   = {c.hidden_loop_end}")
        L.append(f"       sample          = {c.sample_path}")
        L.append(f"       frames/rate     = {c.sample_frames} / {c.sample_rate}"
                 f"  => {c.sample_seconds}s" if c.sample_seconds else
                 f"       frames/rate     = {c.sample_frames} / {c.sample_rate}")
        L.append(f"       TIMEBASE        : {c.timebase_verdict}")
    if r.notes:
        L.append("notes:")
        for n in r.notes:
            L.append(f"   ! {n}")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Inspect a Live .als template")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--dump-xml", metavar="OUT", help="also write the decompressed XML")
    a = ap.parse_args(argv)

    if a.dump_xml:
        raw = Path(a.path).read_bytes()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        Path(a.dump_xml).write_bytes(raw)

    r = inspect(a.path)
    print(json.dumps(r.to_dict(), indent=2) if a.json else format_report(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
