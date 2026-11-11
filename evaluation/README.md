# Evaluation data

This directory contains the rules and supporting data for the evaluation of
the analyser findings reported in the thesis "Python – Staattinen analyysi"
(chapters 6.4.2 and 6.5). The findings were classified manually by the author
of the thesis into true positives (TP), false positives (FP) and false
negatives (FN) against the ground truth of each dataset. The resulting
evaluation matrices (TP, FP and FN per file and analyser) are in appendices 2–4
of the thesis.

The classification is based on the run of 26 October 2026. The verification run
in `../verification_run_20261111/` produced exactly the same findings, so the
classification can be checked against its output files.

## Files

| File | Content |
|---|---|
| `codeviolation_mapping_rules.csv` | Rules used to match analyser messages to the violation types of the CODEVIOLATION ground truth |
| `quixbugs_bug_lines.csv` | Line(s) of the bug in each buggy QuixBugs program |
| `yeswehack_vulnerabilities.csv` | Vulnerability of each YesWeHack file and the findings classified as TP |

## General rules

- TP: a finding that matches a violation, bug or vulnerability in the ground
  truth. FP: a finding without a match in the ground truth, including findings
  whose type is not in the ground truth (for example a missing module
  docstring). FN: a ground-truth item that the analyser did not report.
- Recall = TP / (TP + FN), precision = TP / (TP + FP) and
  F1 = 2 · precision · recall / (precision + recall) are calculated from the
  totals of each dataset. If precision and recall are both 0, F1 is 0. A metric
  with a zero denominator is undefined.

## CODEVIOLATION

- Ground truth: `Ground Truth of Python Code Snippets with (PEP 8 and Coding Best
  Practice Violations).docx` in the CODEVAIOLATION repository (1,365
  violations). A ground-truth entry with a number, for example
  "whitespace after , 3", counts as that many violations.
- The ground truth has no line numbers, so findings are matched by violation
  type within each file using `codeviolation_mapping_rules.csv`.
- For each file and violation type, TP = min(number of violations in the ground
  truth, number of matching findings). Excess findings of the type and findings
  that do not match any violation type are FP. FN = ground truth − TP.
- Four violation types (comments, early input validation, method inside method,
  class inside method) have no matching check in any analyser and are always FN.

## QuixBugs

- Each buggy program contains one bug. The bug line was determined before the
  analysis by comparing the code lines of `python_programs/` and
  `correct_python_programs/`. In four programs the bug is a missing line; the
  bug lines are then the lines of the buggy version between which code was
  added in the correct version (`missing_line = yes`).
- A finding is a TP only if it is on a bug line and identifies the bug. A style
  finding on a bug line (for example a line that is too long) does not meet
  this condition. No analyser identified any bug, so all findings are FP and
  every program is an FN for every analyser.
- The correct versions were analysed only as a control and are not part of the
  evaluation.

## YesWeHack

- Each file contains one vulnerability, whose type is given by the directory
  name (13 vulnerabilities). The helper module `customLog.py` has no
  vulnerability of its own.
- The ground truth gives no exact location, so the findings were classified
  manually. A finding is a TP if it identifies the vulnerability of the file.
  One vulnerability can produce at most one TP; other findings for the same
  vulnerability and all other security findings (for example the Flask debug
  mode or binding to 0.0.0.0) are FP.
