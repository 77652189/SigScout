from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sigscout.adapters.uspnet import USPNetAdapter
from sigscout.core.paths import ProjectPaths
from sigscout.presets.opn import DEFAULT_TAXON_ID, opn_library_service
from sigscout.services.screening import SignalPeptideScreeningService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sigscout", description="Signal peptide discovery and screening toolkit.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Query UniProt and persist candidate signal peptides.")
    discover.add_argument("--taxon-id", type=int, default=DEFAULT_TAXON_ID)
    discover.add_argument("--max-records", type=int, default=300)
    discover.add_argument("--reviewed-only", action="store_true")
    discover.add_argument("--output-dir", type=Path)

    screen = subparsers.add_parser("screen", help="Run rule screening and optional USPNet review.")
    screen.add_argument("--preset", choices=["opn"], default="opn")
    screen.add_argument("--taxon-id", type=int, default=DEFAULT_TAXON_ID)
    screen.add_argument("--max-records", type=int, default=300)
    screen.add_argument("--reviewed-only", action="store_true")
    screen.add_argument("--output-dir", type=Path)

    serve = subparsers.add_parser("serve", help="Start the Streamlit workbench.")
    serve.add_argument("--port", type=int, default=8506)
    serve.add_argument("--address", default="0.0.0.0")

    args = parser.parse_args(argv)
    paths = ProjectPaths.discover()

    if args.command == "discover":
        service = _opn_screening_service(paths, args.output_dir)
        result = service.discover_and_persist_uniprot_candidates(
            taxon_id=args.taxon_id,
            max_records=args.max_records,
            reviewed_only=args.reviewed_only,
            exclude_existing=True,
        )
        print(f"UniProt 初始命中：{result.initial_hit_count}")
        print(f"去重候选：{result.deduplicated_count}")
        print(f"重复记录：{result.duplicate_count}")
        print(f"输出目录：{service.output_dir}")
        return 0 if not result.errors else 1

    if args.command == "screen":
        service = _opn_screening_service(paths, args.output_dir)
        result = service.screen_uniprot_candidates(
            taxon_id=args.taxon_id,
            max_records=args.max_records,
            reviewed_only=args.reviewed_only,
        )
        print(result.message)
        print(f"输出目录：{result.output_dir}")
        return 0 if result.success else 1

    if args.command == "serve":
        app = paths.root / "src" / "sigscout" / "ui" / "streamlit_app.py"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(app),
                "--server.address",
                args.address,
                "--server.port",
                str(args.port),
            ],
            cwd=paths.root,
        )
        return int(completed.returncode)

    return 1


def _opn_screening_service(paths: ProjectPaths, output_dir: Path | None) -> SignalPeptideScreeningService:
    return SignalPeptideScreeningService(
        output_dir or paths.opn_screening_output_dir,
        library_service=opn_library_service(),
        uspnet_adapter=USPNetAdapter(repo_dir=paths.uspnet_repo),
    )


if __name__ == "__main__":
    raise SystemExit(main())
