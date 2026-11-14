#!/usr/bin/env python3
"""Validate the explicitly incomplete R0 ERC report; never waive fabrication ERC.

Read KiCad JSON generated with --severity-all and WITHOUT --exit-code-violations.
Known warnings remain visible in the original report. This allow-list only says
the study has not acquired a new defect or silently hidden an unfinished net.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_LABELS = {'BP_TCLK_UNUSED', 'BA_VPP', 'BA_VDD_SENSE', 'BA_PGD', 'BA_PGC'}
# KiCad 10 defaults, not additional suppressions introduced for this study.
DEFAULT_IGNORED = {'single_global_label', 'four_way_junction', 'simulation_model_issue', 'footprint_filter'}


def check_report(report, fabrication=False):
    issues = []
    if report.get('$schema') != 'https://schemas.kicad.org/erc.v1.json':
        issues.append('unsupported ERC JSON schema')
    if set(report.get('included_severities', [])) != {'error', 'warning', 'exclusion'}:
        issues.append('report must include error, warning and exclusion severities')
    ignored = {c.get('key') for c in report.get('ignored_checks', [])}
    if ignored != DEFAULT_IGNORED:
        issues.append('ignored checks differ from reviewed KiCad defaults')
    seen = Counter()
    violations = [v for sheet in report.get('sheets', []) for v in sheet.get('violations', [])]
    for violation in violations:
        labels = [item.get('description') for item in violation.get('items', [])]
        expected = (
            violation.get('severity') == 'warning'
            and violation.get('type') == 'isolated_pin_label'
            and len(labels) == 1
            and labels[0] in {f"Label '{name}'" for name in EXPECTED_LABELS}
        )
        if expected:
            seen[labels[0]] += 1
        else:
            issues.append(f"unexpected ERC {violation.get('severity')}/{violation.get('type')}: {labels}")
    wanted = Counter({f"Label '{name}'": 1 for name in EXPECTED_LABELS})
    if seen != wanted:
        issues.append('expected exactly the five documented unfinished-net warnings')
    if fabrication:
        # Deliberately not inferred from ERC alone: remove only through a reviewed
        # release gate with a routed PCB, qualified interfaces and physical evidence.
        issues.append('R0 fabrication blocked: five ERC warnings, BA open, hardware unqualified, no routed PCB/DRC')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--fabrication', action='store_true')
    args = parser.parse_args()
    issues = check_report(json.loads(args.report.read_text()), args.fabrication)
    for issue in issues:
        print('ERROR:', issue)
    if not issues:
        print('R0 STUDY ONLY: 0 ERC errors; exactly 5 visible, known warnings; NON-FABRICABLE')
    return bool(issues)


if __name__ == '__main__':
    raise SystemExit(main())
