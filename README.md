# Python static analysers – test environment

Docker-based test environment used in the bachelor's thesis
**"Python – Staattinen analyysi"** (Tomi Helin, LUT University, 2026).
It builds a container with eleven static analysers for Python and three test
datasets, and runs every analyser on every dataset file with default settings.

- Thesis: <THESIS URL / URN, added after publication>
- Archived release: [![DOI](https://zenodo.org/badge/1454301282.svg)](https://doi.org/10.5281/zenodo.24143337)

The evaluation of the findings (classification into true positives, false
positives and false negatives) was done manually and is described in the thesis
(chapter 6.4.2 and appendices 2–4). The rules used in the classification are
in `evaluation/`.

## Contents

| File | Purpose |
|---|---|
| `Dockerfile` | Container image: Python, analysers, test datasets (identical to appendix 1 of the thesis) |
| `static_analyzers.txt` | Analysers and their pinned versions |
| `tools/batch_run_analyzers.py` | Batch script that runs the analysers on the datasets |
| `.dockerignore` | Files excluded from the image build context |
| `evaluation/` | Matching rules and ground-truth details used in the evaluation (see `evaluation/README.md`) |
| `verification_run_20261111/` | Complete output of a verification run made with this repository (see below) |

## What the image contains

**Base image:** `python:3.12.14-slim-trixie` (Debian 13, Python 3.12.14).
Each analyser is installed with pipx into its own virtual environment.

| Category | Analyser | Version |
|---|---|---|
| Education | PythonTA | 2.13.1 |
| Linting | Pylint | 4.0.9 |
| | Flake8 | 7.4.1 |
| | Pyflakes | 4.0.0 |
| | Pycodestyle | 2.15.0 |
| | Prospector | 1.19.1 |
| | Ruff | 0.16.9 |
| Type checking | Mypy | 2.3.1 |
| | Pyright | 1.1.414 (Node.js 24.19.0 via `nodejs-wheel-binaries`) |
| Security | Bandit | 1.9.4 |
| | Semgrep CE | 1.178.0 |

The libraries imported by the datasets (`flask`, `flask-caching`,
`flask-restful`, `requests`) are installed into every analyser environment and
into the system Python, so that missing third-party modules are not reported as
import errors.

**Datasets** (cloned at build time and pinned to commits):

| Dataset | Repository | Commit | Files analysed |
|---|---|---|---|
| CODEVIOLATION¹ | https://github.com/CodingWithLLMs/CODEVAIOLATION | `f2eca3e` | 75: `Python Code Snippets/*.py` |
| QuixBugs | https://github.com/jkoppel/QuixBugs | `4257f44` | 40: `python_programs/*.py` (buggy versions) |
| QuixBugs, correct versions² | same | same | 40: `correct_python_programs/*.py` |
| YesWeHack | https://github.com/yeswehack/vulnerable-code-snippets | `90c910e` | 14: `**/vsnippet/*.py` |

¹ The repository name is spelled `CODEVAIOLATION`; the thesis refers to the
dataset as CODEVIOLATION. The dataset was compiled by Salih and Sarhan (2025),
whose article links to https://github.com/CodingWithLLMs/Online-CodeBase.

² The correct QuixBugs versions are analysed only as a control (thesis
chapter 7.2); they are not used in the reported metrics.

The ground truth used in the thesis comes from the datasets themselves: for
CODEVIOLATION the file `Ground Truth of Python Code Snippets with (PEP 8 and
Coding Best Practice Violations).docx` in the dataset repository, for QuixBugs
the difference between `python_programs/` and `correct_python_programs/`, and
for YesWeHack the vulnerability category given by the directory name.

In QuixBugs, `node.py`, `__init__.py` and `*_test.py` are excluded. In
YesWeHack, page templates in `vsnippet/ignore/` and exploit/solution scripts
outside `vsnippet/` are excluded; the 14 files include the helper module
`customLog.py`.

## Requirements

- Docker (tested with Docker Desktop 4.65.0 on Windows 11 Pro N, build 26200, x86-64).
- Network access during the build (Debian packages, PyPI, GitHub).
- Network access during the run for Semgrep: `--config auto` downloads the rules
  from the Semgrep Registry and sends usage metrics to Semgrep.

## Usage

Build the image:

```sh
docker build -t test-static-analyzers .
```

Start the container so that the results are written to `logs/` on the host.

PowerShell (as in the thesis):

```powershell
docker run -it --rm -v "${PWD}\logs:/workspace/logs" test-static-analyzers
```

Linux / macOS:

```sh
docker run -it --rm -v "$(pwd)/logs:/workspace/logs" test-static-analyzers
```

Inside the container, run the batch script from `/workspace`:

```sh
python3 tools/batch_run_analyzers.py
```

Quick smoke test (one file from each of the four dataset groups, one tool):

```sh
python3 tools/batch_run_analyzers.py --limit 1 --tools ruff
```

Non-interactive run (Linux / macOS):

```sh
docker run --rm -v "$(pwd)/logs:/workspace/logs" test-static-analyzers \
    python3 tools/batch_run_analyzers.py
```

### Script options

| Option | Default | Description |
|---|---|---|
| `--datasets` | `CODEVAIOLATION QuixBugs_Buggy QuixBugs_Correct yeswehack` | Datasets to analyse (exact, case-sensitive names) |
| `--tools` | all | Run only the listed tools (`pylint flake8 pyflakes pycodestyle prospector ruff mypy pyright bandit semgrep python_ta`) |
| `--limit N` | – | Analyse at most N files per dataset |
| `--timeout` | `600` | Timeout per tool run in seconds |
| `--semgrep-config` | `auto` | Semgrep rule configuration |
| `--datasets-root` | `/opt/datasets` | Location of the datasets |
| `--logs-root` | `./logs` | Output directory |
| `--run-name` | `run_<UTC timestamp>` | Name of the run directory (must not exist yet) |

Unknown names in `--datasets` and `--tools` are ignored without a warning, so a
misspelt name can produce an empty run that still ends with exit code 0. Run the
script from `/workspace`, because the default `--logs-root` is the relative path
`./logs`.

## How the analysers are run

Each analyser is run separately for each file, in a new empty temporary working
directory, so that no configuration or cache file can affect the result. The
datasets themselves contain no analyser configuration files. All analysers use
their default settings; the only command-line additions are:

| Tool | Command |
|---|---|
| Pylint | `pylint --output-format=json2 <file>` |
| Flake8 | `flake8 <file>` |
| Pyflakes | `pyflakes <file>` |
| Pycodestyle | `pycodestyle <file>` |
| Prospector | `prospector --output-format json <file>` |
| Ruff | `ruff check --isolated --no-cache --output-format json <file>` |
| Mypy | `mypy -O json <file>` |
| Pyright | `pyright --outputjson <file>` |
| Bandit | `bandit -f json -q <file>` |
| Semgrep | `semgrep scan --config auto --json --quiet <file>` |
| PythonTA | `python_ta --output-format pyta-json --exit-zero <file>` |

The output-format options do not change the findings. Bandit `-q` and Semgrep
`--quiet` only suppress progress output, Ruff `--no-cache` disables the cache
file and PythonTA `--exit-zero` makes its exit code always 0; none of them
changes the findings. `--isolated` prevents Ruff from reading any configuration
file. Semgrep has no local default rule set, so `--config auto` is used.
The environment variable `PYTHONDONTWRITEBYTECODE=1` is set for all runs.

## Output

```
logs/<run-name>/
    manifest.csv                       analysed files and their SHA-256 hashes
    versions/                          Python and tool versions, pip freeze of every tool environment,
                                       versions_at_runtime.json (output of each tool's --version)
    <dataset>/<case>/<tool>.json|txt   tool output (the findings)
    <dataset>/<case>/<tool>.stderr.txt
    <dataset>/<case>/<tool>.meta.json  command, tool version, start time, return code,
                                       duration, timeout and start error
    run_summary.json                   duration, files per dataset, tools, Semgrep config, problems
```

Mypy writes JSON Lines (one object per line), and its output file is empty when
there are no findings.

### Checking a run for errors

`run_summary.json` lists only runs that timed out, could not be started or
wrote a Python traceback to stderr. Return codes and error fields in the tool
outputs are not checked by the script, so check them separately:

- Return codes in the `*.meta.json` files. A non-zero code usually means that
  findings were reported (for example Flake8, Pycodestyle, Mypy, Ruff and
  Pyright return 1, and Pylint returns a bit mask). Errors are indicated by
  Mypy, Ruff and Pyright returning 2 or more, Semgrep returning 2 or more, and
  Pylint setting bit 1 (fatal) or 32 (usage error).
- PythonTA always returns 0 (`--exit-zero`). A crash of Pylint or PythonTA is
  reported as a fatal message (for example F0001 or `astroid-error`) in the
  tool output.
- Semgrep and Bandit report errors, such as files that could not be parsed, in
  the `errors` field of their JSON output, and Prospector reports failures of
  its sub-tools as messages in its own output. A Semgrep run without network
  access fails with exit code 2 but is not listed in `run_summary.json`.

In the run used in the thesis, no analysis ended with an error exit code or a
timeout.

## Limits of reproducibility

- The thesis results come from the run made on 26 October 2026.
- Semgrep `--config auto` downloads the current rules at run time, so the rule
  set can differ from the one used in the thesis.
- Only the analysers themselves are pinned. Their dependencies (for example the
  Pylint, Mypy and Pycodestyle versions inside PythonTA and Prospector) are
  resolved at build time; the resolved versions are written to
  `/opt/versions/tool_freeze.txt` in the image and copied to `versions/` in
  every run.
- The base image tag can be rebuilt by its maintainers with updated Debian
  packages.

## Verification run (11 November 2026)

The directory `verification_run_20261111/` contains the complete, unmodified
output of a run made on 11 November 2026 with the image built from this
repository (`python3 tools/batch_run_analyzers.py --run-name
verification_20261111`, duration 1015 s).

The run was compared with the run of 26 October 2026 used in the thesis:

- The analysers reported exactly the same findings in both runs (6,565
  findings; same dataset, file, tool, line, rule identifier and message),
  including Semgrep with `--config auto`. The TP, FP and FN values in the
  thesis are therefore unchanged.
- The same 169 files were analysed, and their SHA-256 hashes in `manifest.csv`
  match the pinned dataset commits.
- The tool versions in `versions/` match `static_analyzers.txt`.
- No run timed out, wrote a traceback or ended with an error exit code; the
  `errors` fields of the Semgrep and Bandit outputs are empty, Pylint reported
  no fatal messages and all stderr files are empty.

The output files contain short excerpts of the analysed code (for example
Bandit `code`, PythonTA `snippet` and Ruff `fix.edits[].content`). Semgrep
shows `requires login` instead of the code line, because the run was made
without a Semgrep account; this does not affect the analysis.

## Changes since the run used in the thesis

Only comments were changed in `tools/batch_run_analyzers.py` after the run:

- The module docstring was corrected: it now lists all command-line additions
  (`-q`, `--quiet`, `--no-cache`, `--exit-zero`), states that Semgrep is run
  with `--config auto`, and describes the effect of the empty working directory
  more precisely.
- A leftover editing comment before the Semgrep configuration check was
  removed.

Analyser command lines, environment variables, file selection, working
directories and output files are unchanged.

## Licence

The files in this repository are released under the MIT licence (see
`LICENSE`). The datasets are not included in this repository; they are cloned
from their original repositories at build time and are subject to their own
terms. The analyser outputs in `verification_run_20261111/` contain short
excerpts of the dataset files. QuixBugs is MIT-licensed; the CODEVAIOLATION and YesWeHack repositories
do not include a licence file.

## Citation

If you use this environment, please cite the archived release (see
`CITATION.cff`) and the thesis.
