# SigScout

[中文说明](README.md)

SigScout is a signal peptide workbench for secretion construct design. It helps discover, interpret, screen, cluster, and export candidate signal peptides. The default demo project focuses on secretory expression design for human osteopontin (OPN) in Pichia/Komagataella.

SigScout is not meant to replace wet-lab validation. Its job is to turn early signal peptide candidates into an auditable and reproducible experimental draft: preserve source evidence, expose transparent rule checks, collapse highly similar sequences into representatives, and export CSV/FASTA files for downstream design.

## Features

- Query UniProt for proteins annotated with `signal peptide` features.
- Apply transparent rule checks for the N-region charge, H-region hydrophobic core, and C-region cleavage-site preference.
- Optionally call USPNet-fast for machine-learning review; missing USPNet installations do not block rule-based screening.
- Cluster highly similar signal peptides while preserving complete candidate and duplicate evidence.
- Export CSV, FASTA, and JSON summary files for wet-lab discussion or downstream codon-optimization workflows.
- Load locally saved screening results when available; experiment context and saved example outputs are ignored by Git by default.

## Scope

SigScout does not run pcSec model comparisons, does not depend on MATLAB, does not perform codon optimization, and does not integrate SignalP 6.0. Tools such as PichiaCLM can consume SigScout representative exports later for DNA/CDS-level design, but SigScout itself stays at the protein-level signal peptide screening layer.

SigScout outputs draft experimental candidates, not final synthesis-ready sequences. Real secretion performance must be validated with the actual host strain, vector, cultivation condition, and wet-lab assay.

## Installation

Python 3.10 or newer is recommended.

```powershell
cd C:\Users\63097\Documents\CursorProject\SigScout
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[test]"
```

## Run

The recommended local port is `8506`:

```powershell
python -m streamlit run src/sigscout/ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8506
```

CLI commands are also available:

```powershell
python -m sigscout.cli serve --port 8506
python -m sigscout.cli discover --taxon-id 4922 --max-records 300
python -m sigscout.cli screen --preset opn
```

## Inputs And Outputs

Primary inputs:

- The mature amino-acid sequence of a target protein, such as OPN without its native signal peptide.
- Candidate signal peptide sources, such as UniProt, literature, manual imports, or internal experiment records.

Standard outputs:

- `uniprot_candidates.csv`
- `uniprot_duplicate_candidates.csv`
- `signal_peptide_method_comparison.csv`
- `signal_peptide_representatives.csv`
- `method_recommended_candidates.fasta`
- `method_representative_candidates.fasta`
- `signal_peptide_method_comparison_summary.json`

Real local run outputs are written to `local_runs/`, which is ignored by Git. Experiment handoff context in `HANDOFF.md`, saved example screening outputs in `examples/opn/saved_screening/`, Python caches, pytest caches, coverage reports, build artifacts, local Streamlit configuration, and knowledge-graph analysis caches are also ignored.

## Project Layout

```text
src/sigscout/core/          Domain models, path discovery, input interfaces
src/sigscout/adapters/      UniProt, USPNet, and process adapters
src/sigscout/services/      Candidate library, rule screening, clustering, exports, and input implementations
src/sigscout/presets/opn.py Default OPN preset
src/sigscout/ui/            Streamlit workbench
tests/                      Unit tests
```

## Development Checks

```powershell
python -m compileall src tests sigscout
python -m pytest -q
python -m sigscout.cli --help
```

Streamlit health check:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8506/_stcore/health
```

## Compliance Notes

- UniProt is used as a public database source; external materials should preserve accessions, database provenance, and query conditions.
- USPNet-fast is an optional external review tool; use its code and model files according to the official repository license and model-download instructions.
- SignalP 6.0 has licensing and use restrictions. This project does not download it, integrate it, or use it as a default route.
- This tool does not guarantee expression level, secretion efficiency, or final construct performance.

## Acknowledgements

SigScout uses and thanks the following open-source projects and data sources:

- [UniProt](https://www.uniprot.org/) for protein sequences, signal peptide annotations, and accession provenance.
- [USPNet](https://github.com/ml4bio/USPNet) as an optional machine-learning signal peptide review tool.
- [Streamlit](https://streamlit.io/) for the interactive local workbench.
- [pandas](https://pandas.pydata.org/) for CSV and tabular data handling.
- [Pydantic](https://docs.pydantic.dev/) for candidate data modeling.
- [pytest](https://pytest.org/) for project tests.

## License

This repository does not yet declare an open-source license. Add an explicit license and review third-party data/model terms before external reuse, publication, or commercial distribution.
