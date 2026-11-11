#!/usr/bin/env python3
"""Run the selected static analyzers against the three test datasets.

Datasets: CODEVAIOLATION, QuixBugs (buggy and correct versions) and YesWeHack.

All analyzers are run with their default settings. The only additions to the
command lines are:
  * output format (JSON where the tool supports it natively; Mypy writes JSON
    Lines), which does not affect the findings,
  * Bandit -q and Semgrep --quiet, which only suppress progress output,
  * Ruff --no-cache and PythonTA --exit-zero (exit code is always 0), which do
    not affect the findings,
  * Ruff --isolated, which guarantees that no configuration file is read,
  * Semgrep --config auto, because Semgrep has no local default rule set;
    "auto" downloads the rules from the Semgrep Registry at run time, requires
    network access and requires Semgrep metrics to be enabled.

Each tool is run separately for each file, in a fresh empty working directory,
so that no configuration file is read from the working directory and no cache
is reused between runs. (The datasets contain no analyzer configuration files.)

Output structure (one directory per run):
  <logs-root>/<run-name>/
      manifest.csv                      analyzed files and their SHA-256
      versions/                         tool versions and dependency freeze
      <dataset>/<case>/<tool>.json|txt  tool stdout (the findings)
      <dataset>/<case>/<tool>.stderr.txt
      <dataset>/<case>/<tool>.meta.json command, return code, duration, ...
      run_summary.json
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_DATASETS_ROOT = "/opt/datasets"
DEFAULT_LOGS_ROOT = "./logs"
DEFAULT_SEMGREP_CONFIGS = ["auto"]
DEFAULT_TIMEOUT_S = 600

# Files created at image build time (see Dockerfile).
BUILD_INFO_FILES = [
    "/opt/versions/python_version.txt",
    "/opt/versions/tool_versions.txt",
    "/opt/versions/tool_freeze.txt",
    "/opt/semgrep/rulesets.sha256",
    "/opt/semgrep/rule_counts.txt",
    "/opt/semgrep/downloaded_at.txt",
]

# QuixBugs contains test files and a helper class that are not test cases.
QUIXBUGS_EXCLUDE_NAMES = {"node.py", "__init__.py"}
QUIXBUGS_EXCLUDE_SUFFIX = "_test.py"


def get_tools(target, semgrep_configs):
    """Return the analyzers and their command lines (default settings)."""
    t = str(target)
    semgrep_cfg_args = [a for c in semgrep_configs for a in ("--config", str(c))]
    return [
        {"name": "pylint", "ext": "json",
         "command": ["pylint", "--output-format=json2", t]},
        {"name": "flake8", "ext": "txt",
         "command": ["flake8", t]},
        {"name": "pyflakes", "ext": "txt",
         "command": ["pyflakes", t]},
        {"name": "pycodestyle", "ext": "txt",
         "command": ["pycodestyle", t]},
        {"name": "prospector", "ext": "json",
         "command": ["prospector", "--output-format", "json", t]},
        {"name": "ruff", "ext": "json",
         "command": ["ruff", "check", "--isolated", "--no-cache",
                     "--output-format", "json", t]},
        {"name": "mypy", "ext": "json",  # JSON lines: one object per line
         "command": ["mypy", "-O", "json", t]},
        {"name": "pyright", "ext": "json",
         "command": ["pyright", "--outputjson", t]},
        {"name": "bandit", "ext": "json",
         "command": ["bandit", "-f", "json", "-q", t]},
        {"name": "semgrep", "ext": "json",
         "command": ["semgrep", "scan", *semgrep_cfg_args,
                     "--json", "--quiet", t]},
        {"name": "python_ta", "ext": "json",
         "command": ["python_ta", "--output-format", "pyta-json",
                     "--exit-zero", t]},
    ]


VERSION_COMMANDS = {
    "pylint": ["pylint", "--version"],
    "flake8": ["flake8", "--version"],
    "pyflakes": ["pyflakes", "--version"],
    "pycodestyle": ["pycodestyle", "--version"],
    "prospector": ["prospector", "--version"],
    "ruff": ["ruff", "--version"],
    "mypy": ["mypy", "--version"],
    "pyright": ["pyright", "--version"],
    "bandit": ["bandit", "--version"],
    "semgrep": ["semgrep", "--version"],
    "python_ta": ["python_ta", "--version"],
}


def tool_env():
    """Environment for the analyzers: no update checks, no telemetry."""
    env = os.environ.copy()
    env.setdefault("PYRIGHT_PYTHON_IGNORE_WARNINGS", "1")
    env.setdefault("SEMGREP_ENABLE_VERSION_CHECK", "0")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(text):
    """Make a string usable as a directory name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "case"


# --------------------------------------------------------------------------
# Test case discovery
# --------------------------------------------------------------------------

def cases_codeviolation(root):
    src = Path(root) / "CODEVAIOLATION" / "Python Code Snippets"
    return [("CODEVAIOLATION", p.stem, p) for p in sorted(src.glob("*.py"))]


def cases_quixbugs(root, subdir, dataset_name):
    src = Path(root) / "QuixBugs" / subdir
    files = [p for p in sorted(src.glob("*.py"))
             if p.name not in QUIXBUGS_EXCLUDE_NAMES
             and not p.name.endswith(QUIXBUGS_EXCLUDE_SUFFIX)]
    return [(dataset_name, p.stem, p) for p in files]


def cases_yeswehack(root):
    """All Python files directly inside each vsnippet directory.

    Files in vsnippet/ignore/ (page templates) and the exploit/solution
    scripts outside vsnippet directories are not vulnerable snippets and are
    therefore not analyzed. The case name is built from the path so that
    snippets in the same category do not overwrite each other.
    """
    base = Path(root) / "yeswehack"
    cases = []
    for vdir in sorted(p for p in base.glob("**/vsnippet") if p.is_dir()):
        rel_parts = vdir.parent.relative_to(base).parts
        for py in sorted(f for f in vdir.glob("*.py") if f.is_file()):
            case = safe_name("__".join(rel_parts + (py.stem,)))
            cases.append(("yeswehack", case, py))
    return cases


def discover_cases(datasets_root, selected):
    all_cases = []
    if "CODEVAIOLATION" in selected:
        all_cases += cases_codeviolation(datasets_root)
    if "QuixBugs_Buggy" in selected:
        all_cases += cases_quixbugs(datasets_root, "python_programs",
                                    "QuixBugs_Buggy")
    if "QuixBugs_Correct" in selected:
        all_cases += cases_quixbugs(datasets_root, "correct_python_programs",
                                    "QuixBugs_Correct")
    if "yeswehack" in selected:
        all_cases += cases_yeswehack(datasets_root)
    return all_cases


# --------------------------------------------------------------------------
# Running the tools
# --------------------------------------------------------------------------

def run_tool(tool, target, out_dir, timeout_s, env, versions):
    stdout_path = out_dir / f"{tool['name']}.{tool['ext']}"
    stderr_path = out_dir / f"{tool['name']}.stderr.txt"
    meta_path = out_dir / f"{tool['name']}.meta.json"

    meta = {
        "tool": tool["name"],
        "tool_version": versions.get(tool["name"], ""),
        "target": str(target),
        "command": tool["command"],
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "return_code": None,
        "timed_out": False,
        "duration_s": None,
        "error": None,
    }

    start = time.monotonic()
    # A fresh, empty working directory for every run: no configuration file
    # can be picked up from the working directory and no cache is reused.
    with tempfile.TemporaryDirectory(prefix="sa_run_") as workdir:
        meta["cwd"] = workdir
        try:
            with open(stdout_path, "w", encoding="utf-8") as out, \
                 open(stderr_path, "w", encoding="utf-8") as err:
                proc = subprocess.run(tool["command"], stdout=out, stderr=err,
                                      cwd=workdir, env=env, text=True,
                                      timeout=timeout_s, check=False)
            meta["return_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            meta["timed_out"] = True
        except FileNotFoundError as e:
            meta["error"] = f"command not found: {e}"
        except Exception as e:  # keep the batch running
            meta["error"] = repr(e)
    meta["duration_s"] = round(time.monotonic() - start, 3)

    # Flag runs that probably failed (crash instead of findings).
    try:
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        stderr_text = ""
    meta["traceback_in_stderr"] = "Traceback (most recent call last)" in stderr_text

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return meta


def collect_versions(env, versions_dir):
    versions = {}
    for name, cmd in VERSION_COMMANDS.items():
        try:
            with tempfile.TemporaryDirectory() as wd:
                res = subprocess.run(cmd, capture_output=True, text=True,
                                     cwd=wd, env=env, timeout=300, check=False)
            text = (res.stdout or res.stderr).strip()
        except Exception as e:
            text = f"ERROR: {e!r}"
        versions[name] = " | ".join(text.splitlines())
    with open(versions_dir / "versions_at_runtime.json", "w",
              encoding="utf-8") as f:
        json.dump(versions, f, indent=2, ensure_ascii=False)
    for info in BUILD_INFO_FILES:
        if os.path.exists(info):
            shutil.copy2(info, versions_dir / Path(info).name)
    return versions


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets-root", default=DEFAULT_DATASETS_ROOT)
    parser.add_argument("--logs-root", default=DEFAULT_LOGS_ROOT)
    parser.add_argument("--run-name", default=None,
                        help="run directory name (default: run_<UTC timestamp>)")
    parser.add_argument("--semgrep-config", nargs="+", default=DEFAULT_SEMGREP_CONFIGS,
                        help="one or more Semgrep rule files (default: p/python and p/flask)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                        help="timeout per tool run in seconds")
    parser.add_argument("--datasets", nargs="+",
                        default=["CODEVAIOLATION", "QuixBugs_Buggy",
                                 "QuixBugs_Correct", "yeswehack"])
    parser.add_argument("--tools", nargs="+", default=None,
                        help="run only these tools (default: all)")
    parser.add_argument("--limit", type=int, default=None,
                        help="analyze at most N files per dataset (smoke test)")
    args = parser.parse_args()

    run_name = args.run_name or dt.datetime.now(dt.timezone.utc).strftime("run_%Y%m%d_%H%M%SZ")
    run_dir = Path(args.logs_root).resolve() / run_name
    versions_dir = run_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=False)

    for cfg in args.semgrep_config:
        if cfg != "auto" and not cfg.startswith("p/") and not os.path.exists(cfg):
            print(f"[WARNING] Semgrep rule file not found: {cfg}")

    env = tool_env()
    print("Collecting tool versions ...", flush=True)
    versions = collect_versions(env, versions_dir)

    cases = discover_cases(args.datasets_root, set(args.datasets))
    if args.limit is not None:
        limited, per_ds = [], {}
        for c in cases:
            per_ds[c[0]] = per_ds.get(c[0], 0) + 1
            if per_ds[c[0]] <= args.limit:
                limited.append(c)
        cases = limited

    # Manifest of analyzed files (for the thesis and for reproducibility).
    with open(run_dir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "case", "source_path", "sha256"])
        for dataset, case, path in cases:
            w.writerow([dataset, case, str(path), sha256_of(path)])

    counts = {}
    for dataset, _, _ in cases:
        counts[dataset] = counts.get(dataset, 0) + 1
    print("Files to analyze: " + ", ".join(f"{k}={v}" for k, v in counts.items()),
          flush=True)

    problems = []
    run_start = time.monotonic()
    for i, (dataset, case, path) in enumerate(cases, start=1):
        out_dir = run_dir / dataset / case
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{i}/{len(cases)}] {dataset} / {case} ", end="", flush=True)
        for tool in get_tools(path, args.semgrep_config):
            if args.tools and tool["name"] not in args.tools:
                continue
            meta = run_tool(tool, path, out_dir, args.timeout, env, versions)
            if meta["timed_out"] or meta["error"] or meta["traceback_in_stderr"]:
                problems.append({"dataset": dataset, "case": case,
                                 "tool": tool["name"],
                                 "timed_out": meta["timed_out"],
                                 "error": meta["error"],
                                 "traceback": meta["traceback_in_stderr"]})
                print("!", end="", flush=True)
            else:
                print(".", end="", flush=True)
        print(" done", flush=True)

    summary = {
        "run_name": run_name,
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "duration_s": round(time.monotonic() - run_start, 1),
        "files_per_dataset": counts,
        "tools": [t["name"] for t in get_tools("X", args.semgrep_config)
                  if not args.tools or t["name"] in args.tools],
        "semgrep_config": args.semgrep_config,
        "problems": problems,
    }
    with open(run_dir / "run_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Results: {run_dir}")
    if problems:
        print(f"{len(problems)} tool runs need checking (see run_summary.json).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
