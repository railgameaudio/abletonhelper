# abletonhelper

Analyse song stems and build Ableton Live sets from them.

## Setup

```bash
git clone https://github.com/railgameaudio/abletonhelper
cd abletonhelper
git lfs install                 # stems are LFS-tracked

python3 -m venv .venv && source .venv/bin/activate
pip install -e .

cd frontend && npm install && cd ..
```

## Run

```bash
make dev
```

API on http://127.0.0.1:8000, UI on http://127.0.0.1:5173.

## Use

1. Put each song's stems in its own folder under `songs/`.
2. Hit **Scan songs/** in the UI (or `POST /api/songs/scan`).
3. **Analyse** a song — tempo, key, chords and sections.
4. Building sets needs `templates/Template.als`. See `CLAUDE.md`.

Or from the terminal:

```bash
python -m abletonhelper.cli backends
python -m abletonhelper.cli analyze songs/my-song/
python -m abletonhelper.cli inspect templates/Template.als
```

## Section labels

Out of the box, sections come from librosa, which detects *repetition*
rather than *function* — labels like "chorus" are heuristic and marked
low-confidence. For real functional labels install the `allin1` backend.
`docs/analysis.md` covers the tradeoff, including what it costs to run.
