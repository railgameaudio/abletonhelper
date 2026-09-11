# Audio and template files in git

Two file types here are load-bearing and easy to lose:

## `templates/*.als`

The Live template is **input**, not output. The set builder clones node
structure out of it rather than synthesising Live XML, so a missing
template means nothing can be built.

`.als` is gzipped XML — typically well under a megabyte. It belongs in
plain git and is marked `binary` in `.gitattributes` so diffs stay quiet.

**Never add `*.als` to `.gitignore`.** Ableton's own project folders ship
with ignore rules that do exactly that, and the failure is silent: the
push succeeds, the template just is not in it.

Check before pushing:

```bash
git check-ignore -v templates/Template.als   # should print nothing
```

## Audio stems

Routed through Git LFS (see `.gitattributes`). Once per clone:

```bash
git lfs install
```

GitHub rejects any single file over 100 MB without LFS and warns above
50 MB. Full-length multitrack WAVs cross that easily.

If you would rather not put audio in git at all, that is reasonable —
keep `songs/` local and point `AH_SONGS_DIR` somewhere outside the repo.
The app only ever needs paths.
