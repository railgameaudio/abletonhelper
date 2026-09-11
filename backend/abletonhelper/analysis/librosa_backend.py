"""Baseline analyzer built on librosa. Pure CPU, no model downloads.

What this is good at:  tempo, beat grid, key, rough chord spans.
What this is NOT good at:  naming sections. Librosa can tell you
"this 16-bar span is the same music as that one" but it has no concept
of a chorus. The functional labels produced here are a heuristic over
the repetition structure and are emitted with low confidence on purpose.
Use the allin1 backend when the labels actually matter.
"""

from __future__ import annotations

import numpy as np

from .base import AnalysisInput, AnalysisResult, ChordSpan, Section

NAME = "librosa"


# Krumhansl-Kessler key profiles.
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                      2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                      2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _chord_templates() -> tuple[np.ndarray, list[str]]:
    """24 binary triad templates (12 major, 12 minor), L2-normalised."""
    templates, labels = [], []
    for root in range(12):
        for quality, intervals in (("maj", (0, 4, 7)), ("min", (0, 3, 7))):
            v = np.zeros(12)
            for iv in intervals:
                v[(root + iv) % 12] = 1.0
            templates.append(v / np.linalg.norm(v))
            labels.append(f"{_PITCHES[root]}:{quality}")
    return np.array(templates), labels


class LibrosaAnalyzer:
    name = NAME

    def __init__(self, sr: int = 22050, n_sections: int = 8,
                 min_section_bars: int = 4):
        self.sr = sr
        self.n_sections = n_sections
        self.min_section_bars = min_section_bars
        self._bar_grid = np.array([])
        self._sec_per_bar = 2.0

    @property
    def version(self) -> str:
        try:
            import librosa
            return f"librosa-{librosa.__version__}"
        except Exception:
            return "librosa-missing"

    def available(self) -> tuple[bool, str]:
        try:
            import librosa  # noqa: F401
            return True, ""
        except ImportError as e:
            return False, f"librosa not installed: {e}"

    # -- main ---------------------------------------------------------

    def analyze(self, inp: AnalysisInput) -> AnalysisResult:
        import librosa

        # Prefer a drums stem for the beat grid if one was handed to us:
        # transient-only audio tracks far more reliably than a full mix.
        beat_src = inp.stems.get("drums") or inp.primary()
        harm_src = inp.stems.get("other") or inp.stems.get("bass") or inp.primary()

        y, sr = librosa.load(str(inp.primary()), sr=self.sr, mono=True)
        duration = float(librosa.get_duration(y=y, sr=sr))

        result = AnalysisResult(
            source=str(inp.primary()),
            duration=duration,
            backend=self.name,
            backend_version=self.version,
        )

        # --- tempo + beats -------------------------------------------
        if str(beat_src) != str(inp.primary()):
            yb, _ = librosa.load(str(beat_src), sr=self.sr, mono=True)
        else:
            yb = y
        onset_env = librosa.onset.onset_strength(y=yb, sr=sr)
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, trim=False
        )
        beats = librosa.frames_to_time(beat_frames, sr=sr)
        result.beats = [float(t) for t in beats]
        # Derive BPM from the grid we actually emit. librosa's own tempo
        # scalar can disagree with its beat frames, and every downstream
        # bar calculation keys off the grid -- so the grid wins.
        result.tempo = self._tempo_from_grid(beats, float(np.atleast_1d(tempo)[0]))

        # --- downbeats (phase that maximises onset strength) ---------
        result.downbeats = self._estimate_downbeats(
            beats, onset_env, sr, result.time_signature
        )

        # Bar grid drives section snapping below.
        self._bar_grid = np.array(result.bar_times())
        self._sec_per_bar = (
            (60.0 / result.tempo) * result.time_signature
            if result.tempo > 0 else 2.0
        )

        # --- key ------------------------------------------------------
        if str(harm_src) != str(inp.primary()):
            yh, _ = librosa.load(str(harm_src), sr=self.sr, mono=True)
        else:
            yh = y
        chroma = librosa.feature.chroma_cqt(y=yh, sr=sr, bins_per_octave=36)
        result.key = self._estimate_key(chroma)

        # --- chords ---------------------------------------------------
        result.chords = self._estimate_chords(chroma, sr, beats)

        # --- sections -------------------------------------------------
        result.sections = self._estimate_sections(y, sr, duration)

        result.meta = {
            "beat_source": str(beat_src),
            "harmonic_source": str(harm_src),
            "label_quality": "heuristic - letters mapped to guesses, low confidence",
        }
        return result

    # -- pieces -------------------------------------------------------

    @staticmethod
    def _tempo_from_grid(beats, fallback: float) -> float:
        """BPM from the beat grid by least-squares slope.

        Do NOT use the median inter-beat interval: onset frames are
        quantised to the hop size (~23 ms at sr=22050/hop=512), so gaps
        alternate between neighbouring frame counts and the median snaps
        to one of them -- 0.511 s instead of 0.4998 s, i.e. 117.5 BPM
        instead of 120. Fitting the whole grid averages that jitter out.
        """
        if len(beats) < 2:
            return fallback
        idx = np.arange(len(beats), dtype=float)
        slope = float(np.polyfit(idx, np.asarray(beats, dtype=float), 1)[0])
        return 60.0 / slope if slope > 0 else fallback

    def _estimate_downbeats(self, beats, onset_env, sr, meter: int) -> list[float]:
        import librosa

        if len(beats) < meter:
            return []
        times = librosa.times_like(onset_env, sr=sr)
        strength = np.interp(beats, times, onset_env)
        # Score each of the `meter` possible phases; strongest wins.
        scores = [strength[phase::meter].mean() for phase in range(meter)]
        phase = int(np.argmax(scores))
        return [float(t) for t in beats[phase::meter]]

    def _estimate_key(self, chroma) -> str:
        profile = chroma.mean(axis=1)
        if profile.sum() <= 0:
            return "unknown"
        profile = profile / profile.sum()
        best, best_score = "unknown", -np.inf
        for root in range(12):
            for quality, prof in (("major", _KK_MAJOR), ("minor", _KK_MINOR)):
                rotated = np.roll(prof, root)
                score = float(np.corrcoef(profile, rotated)[0, 1])
                if score > best_score:
                    best_score, best = score, f"{_PITCHES[root]} {quality}"
        return best

    def _estimate_chords(self, chroma, sr, beats) -> list[ChordSpan]:
        import librosa

        templates, labels = _chord_templates()
        # Beat-synchronous chroma: chords change on beats, not frames.
        frames = librosa.time_to_frames(beats, sr=sr)
        frames = np.clip(frames, 0, chroma.shape[1] - 1)
        if len(frames) < 2:
            return []
        sync = librosa.util.sync(chroma, frames, aggregate=np.median)

        norm = np.linalg.norm(sync, axis=0, keepdims=True)
        norm[norm == 0] = 1.0
        sync = sync / norm
        scores = templates @ sync                      # (24, n_beats)
        idx = scores.argmax(axis=0)
        conf = scores.max(axis=0)

        # Smooth single-beat flickers away.
        idx = self._median_filter(idx, k=5)

        spans: list[ChordSpan] = []
        edges = list(beats) + [float(beats[-1] + (beats[-1] - beats[-2]))]
        cur, start_i = idx[0], 0
        for i in range(1, len(idx) + 1):
            if i == len(idx) or idx[i] != cur:
                spans.append(ChordSpan(
                    start=float(edges[start_i]),
                    end=float(edges[min(i, len(edges) - 1)]),
                    chord=labels[int(cur)],
                    confidence=float(np.mean(conf[start_i:i])),
                ))
                if i < len(idx):
                    cur, start_i = idx[i], i
        return spans

    @staticmethod
    def _median_filter(a: np.ndarray, k: int) -> np.ndarray:
        if len(a) < k:
            return a
        pad = k // 2
        padded = np.pad(a, pad, mode="edge")
        out = np.empty_like(a)
        for i in range(len(a)):
            vals, counts = np.unique(padded[i:i + k], return_counts=True)
            out[i] = vals[counts.argmax()]
        return out

    def _estimate_sections(self, y, sr, duration) -> list[Section]:
        """Laplacian structural decomposition (McFee & Ellis, 2014)."""
        import librosa
        import scipy.linalg
        import scipy.ndimage
        from sklearn.cluster import KMeans

        bpo = 12 * 3
        C = librosa.amplitude_to_db(
            np.abs(librosa.cqt(y=y, sr=sr, bins_per_octave=bpo, n_bins=7 * bpo)),
            ref=np.max,
        )
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, trim=False)
        if len(beats) < 8:
            return [Section(0.0, duration, "unknown", 0.0)]
        Csync = librosa.util.sync(C, beats, aggregate=np.median)
        beat_times = librosa.frames_to_time(
            librosa.util.fix_frames(beats, x_min=0), sr=sr
        )

        R = librosa.segment.recurrence_matrix(
            Csync, width=3, mode="affinity", sym=True
        )
        R = scipy.ndimage.median_filter(R, size=(1, 7))

        mfcc = librosa.feature.mfcc(y=y, sr=sr)
        Msync = librosa.util.sync(mfcc, beats)
        path_dist = np.sum(np.diff(Msync, axis=1) ** 2, axis=0)
        sigma = np.median(path_dist) or 1.0
        path_sim = np.exp(-path_dist / sigma)
        Rf = np.diag(path_sim, 1) + np.diag(path_sim, -1)

        deg = (R + Rf).sum(axis=1)
        mu = deg.dot(R) / (deg.dot(R) + deg.dot(Rf) + 1e-9)
        A = mu * R + (1 - mu) * Rf

        d = A.sum(axis=1)
        d[d <= 0] = 1e-9
        dinv = np.diag(d ** -0.5)
        L = dinv @ (np.diag(d) - A) @ dinv
        evals, evecs = scipy.linalg.eigh(L)
        evecs = scipy.ndimage.median_filter(evecs, size=(9, 1))

        k = min(self.n_sections, evecs.shape[1])
        X = evecs[:, :k] / (np.linalg.norm(evecs[:, :k], axis=1, keepdims=True) + 1e-9)
        seg_ids = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)

        bounds = list(librosa.util.fix_frames(
            np.flatnonzero(seg_ids[1:] != seg_ids[:-1]) + 1,
            x_min=0, x_max=len(seg_ids),
        ))
        raw: list[tuple[float, float, int]] = []
        for a, b in zip(bounds[:-1], bounds[1:]):
            start = float(beat_times[min(a, len(beat_times) - 1)])
            end = float(beat_times[min(b, len(beat_times) - 1)])
            if end > start:
                raw.append((start, end, int(seg_ids[a])))
        if not raw:
            return [Section(0.0, duration, "unknown", 0.0)]
        raw[-1] = (raw[-1][0], duration, raw[-1][2])
        raw = self._consolidate(raw, duration)
        return self._label_sections(raw, y, sr)

    def _consolidate(self, raw, duration):
        """Snap to bars, drop sub-musical fragments, merge repeats.

        Raw spectral clustering happily emits half-second "sections".
        Nothing downstream wants that: a section is a structural unit and
        it starts on a bar line. We snap every boundary to the nearest
        downbeat, then absorb anything shorter than `min_section_bars`
        into its neighbour until only real sections remain.
        """
        grid = self._bar_grid
        min_len = self.min_section_bars * self._sec_per_bar

        def snap(t: float) -> float:
            if not len(grid):
                return t
            return float(grid[int(np.argmin(np.abs(grid - t)))])

        # snap boundaries
        spans = []
        for i, (start, end, cid) in enumerate(raw):
            s0 = 0.0 if i == 0 else snap(start)
            e0 = duration if i == len(raw) - 1 else snap(end)
            if e0 > s0:
                spans.append([s0, e0, cid])
        if not spans:
            return [(0.0, duration, 0)]

        # merge adjacent identical clusters
        spans = self._merge_adjacent(spans)

        # absorb fragments, shortest first, until all meet the minimum
        while len(spans) > 1:
            lengths = [sp[1] - sp[0] for sp in spans]
            i = int(np.argmin(lengths))
            if lengths[i] >= min_len:
                break
            if i == 0:
                spans[1][0] = spans[0][0]
                spans.pop(0)
            elif i == len(spans) - 1:
                spans[-2][1] = spans[-1][1]
                spans.pop()
            else:
                # give it to whichever neighbour is longer
                if (spans[i - 1][1] - spans[i - 1][0]) >= (spans[i + 1][1] - spans[i + 1][0]):
                    spans[i - 1][1] = spans[i][1]
                else:
                    spans[i + 1][0] = spans[i][0]
                spans.pop(i)
            spans = self._merge_adjacent(spans)

        return [(sp[0], sp[1], sp[2]) for sp in spans]

    @staticmethod
    def _merge_adjacent(spans):
        out = [list(spans[0])]
        for sp in spans[1:]:
            if sp[2] == out[-1][2]:
                out[-1][1] = sp[1]
            else:
                out.append(list(sp))
        return out

    def _label_sections(self, raw, y, sr) -> list[Section]:
        """Map repetition clusters onto functional names. Heuristic!

        The most-repeated, highest-energy cluster is called chorus; the
        first span is intro and the last is outro. Everything else falls
        back to verse. Confidence stays low because this is a guess.
        """
        import librosa

        energies: dict[int, list[float]] = {}
        counts: dict[int, int] = {}
        for start, end, cid in raw:
            seg = y[int(start * sr):int(end * sr)]
            rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
            energies.setdefault(cid, []).append(rms)
            counts[cid] = counts.get(cid, 0) + 1

        def score(cid: int) -> float:
            return counts[cid] * float(np.mean(energies[cid]))

        chorus_id = max(counts, key=score) if counts else None

        out: list[Section] = []
        for i, (start, end, cid) in enumerate(raw):
            if i == 0:
                label = "intro"
            elif i == len(raw) - 1:
                label = "outro"
            elif cid == chorus_id:
                label = "chorus"
            else:
                label = "verse"
            out.append(Section(start, end, label, confidence=0.25))
        return out
