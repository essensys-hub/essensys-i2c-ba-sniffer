#!/usr/bin/env python3
"""Fault-injection tests using the actual, complete KiCad JSON report."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

import check_erc

FIXTURE = json.loads(Path(sys.argv.pop(1)).read_text())


class StudyERC(unittest.TestCase):
    def test_current_study(self):
        self.assertEqual(check_erc.check_report(FIXTURE), [])

    def test_study_cannot_authorize_fabrication(self):
        self.assertTrue(check_erc.check_report(FIXTURE, fabrication=True))

    def test_extra_error_is_rejected(self):
        report = deepcopy(FIXTURE)
        report['sheets'][0]['violations'].append({'severity': 'error', 'type': 'pin_not_connected', 'items': []})
        self.assertTrue(check_erc.check_report(report))

    def test_unknown_warning_is_rejected(self):
        report = deepcopy(FIXTURE)
        report['sheets'][0]['violations'][0]['items'][0]['description'] = "Label 'UNEXPECTED'"
        self.assertTrue(check_erc.check_report(report))

    def test_excluded_warning_is_rejected(self):
        report = deepcopy(FIXTURE)
        report['sheets'][0]['violations'][0]['severity'] = 'exclusion'
        self.assertTrue(check_erc.check_report(report))

    def test_removed_warning_requires_review(self):
        report = deepcopy(FIXTURE)
        report['sheets'][0]['violations'].pop()
        self.assertTrue(check_erc.check_report(report))

    def test_hidden_severity_is_rejected(self):
        report = deepcopy(FIXTURE)
        report['included_severities'].remove('exclusion')
        self.assertTrue(check_erc.check_report(report))

    def test_added_suppression_is_rejected(self):
        report = deepcopy(FIXTURE)
        report['ignored_checks'].append({'key': 'pin_not_driven'})
        self.assertTrue(check_erc.check_report(report))


if __name__ == '__main__':
    unittest.main()
