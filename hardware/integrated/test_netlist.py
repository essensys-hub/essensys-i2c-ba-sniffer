#!/usr/bin/env python3
"""Fault-injection regression tests against a KiCad-exported XML netlist."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

import check_netlist as checker

FIXTURE = ET.parse(sys.argv.pop(1)).getroot()


def net(root, name):
    return next(n for n in root.findall('./nets/net') if n.get('name','').lstrip('/') == name)


class ElectricalContract(unittest.TestCase):
    def test_current_study(self):
        self.assertEqual(checker.check_root(FIXTURE), [])

    def test_15v_cannot_reach_bp_reference(self):
        root=deepcopy(FIXTURE)
        net(root,'+15V_PASS').append(ET.Element('node',ref='J_BP',pin='7'))
        self.assertTrue(any('architecture violation +15V_PASS' in e for e in checker.check_root(root)))

    def test_bp_power_cannot_be_pod_power(self):
        root=deepcopy(FIXTURE)
        net(root,'BP_VREF').append(ET.Element('node',ref='U_RPREG',pin='5'))
        self.assertTrue(any('architecture violation BP_VREF' in e for e in checker.check_root(root)))

    def test_ba_vpp_cannot_be_gpio(self):
        root=deepcopy(FIXTURE)
        net(root,'BA_VPP').append(ET.Element('node',ref='U_RP',pin='8'))
        self.assertTrue(any('architecture violation BA_VPP' in e for e in checker.check_root(root)))

    def test_usb_polarity_swap_is_rejected(self):
        root=deepcopy(FIXTURE)
        n=next(n for n in net(root,'USB_FX_DM').findall('node') if n.get('ref')=='U_FX')
        n.set('pin','15')
        self.assertTrue(any('architecture violation USB_FX_DM' in e for e in checker.check_root(root)))

    def test_bp_enable_cannot_bypass_and_gates(self):
        root=deepcopy(FIXTURE)
        n=next(n for n in net(root,'RP_BP_OE').findall('node') if n.get('ref')=='U_BPAND')
        net(root,'RP_BP_OE').remove(n)
        self.assertTrue(any('architecture violation RP_BP_OE' in e for e in checker.check_root(root)))

    def test_adc_divider_value_is_checked(self):
        root=deepcopy(FIXTURE)
        next(c for c in root.findall('./components/comp') if c.get('ref')=='R_VTOP').find('value').text='0'
        self.assertTrue(any('critical value changed R_VTOP' in e for e in checker.check_root(root)))

    def test_reset_sense_cannot_use_request_gpio(self):
        root=deepcopy(FIXTURE)
        n=next(n for n in net(root,'RP_BP_RESET_SENSE').findall('node') if n.get('ref')=='U_RP')
        n.set('pin','16')
        self.assertTrue(any('architecture violation RP_BP_RESET_SENSE' in e for e in checker.check_root(root)))

    def test_capture_path_cannot_be_direct(self):
        root=deepcopy(FIXTURE)
        net(root,'SCL_BUS').append(ET.Element('node',ref='U_FX',pin='25'))
        self.assertTrue(any('architecture violation SCL_BUS' in e for e in checker.check_root(root)))

    def test_self_power_strap_change_is_rejected(self):
        root=deepcopy(FIXTURE)
        n=next(n for n in net(root,'+3V3_HUB').findall('node') if n.get('ref')=='R_HCFG1')
        net(root,'+3V3_HUB').remove(n);net(root,'GND').append(n)
        self.assertTrue(any('pull-up missing R_HCFG1' in e for e in checker.check_root(root)))


if __name__ == '__main__':
    unittest.main()
