# Architecture

## Shape

```
frontend/  React + Vite (TypeScript)
              |  /api  (proxied in dev, served by FastAPI in prod)
backend/   FastAPI
           ├── analysis/   pluggable analyzers -> AnalysisResult
           ├── als/        read + write Live sets
           ├── library.py  stem discovery, analysis orchestration
           ├── jobs.py     background work
           └── db.py       SQLAlchemy over SQLite
```

## The one contract that matters

`analysis/base.py::AnalysisResult` is the only thing that crosses from
analysis into set building and into the UI. Backends are swappable
because nothing downstream knows which one ran. Times in it are **always
seconds**; conversion to Ableton units happens once, in
`als/timebase.py`.

## Local now, hosted later

Deliberate choices that make the eventual multi-user version cheap:

| Concern | Now | Later |
|---|---|---|
| DB | SQLite via SQLAlchemy | swap `AH_DATABASE_URL` to Postgres |
| Jobs | thread pool in-process | replace `jobs.submit` with RQ/Celery; the Job row and polling endpoint are unchanged |
| Files | local paths | storage interface behind `library.py` |
| Auth | `single_user = True` | real accounts; every query already goes through a session |

## The thing that does not survive hosting

This is worth knowing now rather than later.

A generated `.als` references audio **by absolute path on the machine
that will open it**. That is fine locally. It cannot work for a hosted
multi-user product: a server has no idea where a stranger's Mac keeps
its files, and cannot write to it.

The fix, which shapes the builder from the start: emit a proper **Ableton
Project folder** as a zip —

```
My Set Project/
├── My Set.als          <- references Samples/ relatively
└── Samples/Imported/
    ├── kick.wav
    └── ...
```

Live resolves relative paths inside a project folder, so the same bundle
opens correctly on any machine. Building this way from day one means the
local and hosted paths stay identical, and it makes local sets portable
too — which matters the first time a set is moved between a laptop and a
studio machine.
