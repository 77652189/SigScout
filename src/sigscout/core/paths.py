from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @classmethod
    def discover(cls, anchor: Path | None = None) -> "ProjectPaths":
        start = (anchor or Path.cwd()).resolve()
        if start.is_file():
            start = start.parent
        for candidate in [start, *start.parents]:
            if (candidate / "pyproject.toml").exists() and (candidate / "src" / "sigscout").exists():
                return cls(candidate)
        return cls(start)

    @property
    def local_runs_dir(self) -> Path:
        return self.root / "local_runs"

    @property
    def opn_saved_screening_dir(self) -> Path:
        return self.root / "examples" / "opn" / "saved_screening"

    @property
    def opn_screening_output_dir(self) -> Path:
        return self.local_runs_dir / "opn_signal_peptides"

    @property
    def uspnet_repo(self) -> Path | None:
        configured = os.environ.get("USPNET_REPO")
        if configured:
            return Path(configured)
        candidate = self.root.parent / "USPNet"
        return candidate if candidate.exists() else None

