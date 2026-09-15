"""Command line entry point: `python -m abletonhelper.cli ...`"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import registry
from .analysis.base import AnalysisInput
from .als import inspect as als_inspect


def cmd_inspect(args) -> int:
    return als_inspect.main([args.path] + (["--json"] if args.json else [])
                            + (["--dump-xml", args.dump_xml] if args.dump_xml else []))


def cmd_analyze(args) -> int:
    path = Path(args.path)
    if path.is_dir():
        from .library import scan_song_folder
        stems = {k: path / v for k, v in scan_song_folder(path).items()}
        inp = AnalysisInput(mix=stems.get("mix"), stems=stems)
    else:
        inp = AnalysisInput(mix=path)

    result = registry.analyze(inp, backend=args.backend)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    print(f"source  : {result.source}")
    print(f"backend : {result.backend} ({result.backend_version})")
    print(f"duration: {result.duration:.2f}s")
    print(f"tempo   : {result.tempo:.2f} BPM   key: {result.key}   "
          f"meter: {result.time_signature}/4")
    print(f"beats   : {len(result.beats)}   downbeats: {len(result.downbeats)}")
    print(f"\nsections ({len(result.sections)}):")
    for s in result.sections:
        bars = (s.duration * result.tempo / 60.0 / result.time_signature) if result.tempo else 0
        print(f"   {s.label:12s} {s.start:7.2f} -> {s.end:7.2f}  "
              f"({s.duration:6.2f}s ~ {bars:4.1f} bars)  conf={s.confidence:.2f}")
    if result.chords:
        print(f"\nchords ({len(result.chords)} spans, first 16):")
        for c in result.chords[:16]:
            print(f"   {c.chord:8s} {c.start:7.2f} -> {c.end:7.2f}  conf={c.confidence:.2f}")
    if result.meta:
        print(f"\nmeta: {json.dumps(result.meta, indent=2)}")
    if args.out:
        result.write_json(args.out)
        print(f"\nwrote {args.out}")
    return 0


def cmd_chords(args) -> int:
    from .analysis.midi_chords import chords_from_midi, list_tracks

    if args.tracks:
        for t in list_tracks(args.path):
            print(f"[{t['index']}] {t['name']!r}  notes={t['notes']}")
        return 0

    from .analysis.midi_chords import explain
    print(explain(args.path, args.track, args.all_tracks))
    spans = chords_from_midi(args.path, track_filter=args.track,
                             all_tracks=args.all_tracks,
                             prefer_flats=args.flats)
    if not spans:
        print("No chords found. Try --tracks to see what is in the file, "
              "then --track NAME to pick one.")
        return 1
    for c in spans:
        print(f"   {c.chord:10s} {c.start:7.2f} -> {c.end:7.2f}")
    return 0


def cmd_backends(args) -> int:
    st = registry.status()
    for name, info in st.items():
        mark = "OK " if info["available"] else "-- "
        print(f"{mark} {name:10s} {info['version']}")
        if not info["available"]:
            print(f"     {info['reason']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="abletonhelper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inspect", help="report the real structure of a .als")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dump-xml")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("analyze", help="analyse an audio file or a stem folder")
    p.add_argument("path")
    p.add_argument("--backend", default="auto", choices=["auto", "librosa", "allin1"])
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", help="write AnalysisResult JSON here")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("chords", help="read chords from a MIDI file")
    p.add_argument("path")
    p.add_argument("--track", default=None,
                   help="only read tracks whose name contains this "
                        "(default: pick automatically)")
    p.add_argument("--all-tracks", action="store_true",
                   help="read every track, even non-chord ones")
    p.add_argument("--tracks", action="store_true", help="list tracks and exit")
    p.add_argument("--flats", action="store_true", help="spell with flats")
    p.set_defaults(func=cmd_chords)

    p = sub.add_parser("backends", help="what analysis backends are usable")
    p.set_defaults(func=cmd_backends)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
