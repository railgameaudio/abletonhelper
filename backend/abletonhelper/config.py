from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AH_", env_file=".env")

    # Local-first defaults. Every one of these becomes a deployment knob
    # when this stops running on one person's laptop.
    data_dir: Path = Path("data")
    out_dir: Path = Path("out")
    songs_dir: Path = Path("songs")
    template_path: Path = Path("templates/Template.als")

    database_url: str = ""          # derived below when empty
    analysis_backend: str = "auto"  # auto | librosa | allin1
    max_workers: int = 2

    # Single-user local mode. Flip off when real accounts arrive.
    single_user: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def model_post_init(self, _ctx) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{(self.data_dir / 'abletonhelper.db').as_posix()}"

    @property
    def analysis_cache(self) -> Path:
        p = self.data_dir / "analysis"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
