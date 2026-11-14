#!/usr/bin/env python3
"""Check R0 wiring and independently enforce the safety-critical architecture.

The generated manifest catches accidental KiCad edits. The independent contract
below catches a generator change that crosses the bus/programming/power domains.
This check does NOT turn the incomplete study into a validated PCB.
"""
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def read_nets(root):
    nets, loose = {}, set()
    for net in root.findall('./nets/net'):
        name = net.get('name', '').lstrip('/')
        pins = {f"{n.get('ref')}.{n.get('pin')}" for n in net.findall('node') if not n.get('ref', '').startswith('#')}
        if name.startswith('unconnected-'):
            loose |= pins
        elif pins:
            if name in nets:
                raise ValueError(f'ambiguous net {name}')
            nets[name] = pins
    return nets, loose


def critical_contract():
    expected = {
      '+15V_PASS': {'J_I2C_IN.4', 'J_I2C_OUT.4'},
      'SDA_BUS': {'J_I2C_IN.1', 'J_I2C_OUT.1', 'R_IN2.1'},
      'SCL_BUS': {'J_I2C_IN.2', 'J_I2C_OUT.2', 'R_IN1.1'},
      'USB_UP_DM': {'J_USB.2', 'U_HUB.30'},
      'USB_UP_DP': {'J_USB.3', 'U_HUB.31'},
      'USB_FX_DM': {'U_HUB.1', 'U_FX.16'},
      'USB_FX_DP': {'U_HUB.2', 'U_FX.15'},
      'USB_RP_DM': {'U_HUB.3', 'R_DM.1'},
      'USB_RP_DP': {'U_HUB.4', 'R_DP.1'},
      'RP_DM_PAD': {'R_DM.2', 'U_RP.51'},
      'RP_DP_PAD': {'R_DP.2', 'U_RP.52'},
      'HUB_CFG0': {'U_HUB.24', 'R_HCFG0.1'},
      'HUB_CFG1': {'U_HUB.25', 'R_HCFG1.1'},
      'HUB_NONREM0': {'U_HUB.28', 'R_HNR0.1'},
      'HUB_NONREM1': {'U_HUB.22', 'R_HNR1.1'},
      'HUB_PWR1': {'U_HUB.12', 'U_SW1.4', 'R_PW1.1'},
      'HUB_PWR2': {'U_HUB.16', 'U_SW2.4', 'R_PW2.1'},
      'HUB_OC1_N': {'U_HUB.13', 'U_SW1.3', 'R_OC1.1'},
      'HUB_OC2_N': {'U_HUB.17', 'U_SW2.3', 'R_OC2.1'},
      'VBUS_FX': {'U_SW1.1', 'U_FXREG.1', 'U_FXREG.3', 'C_FXIN.1'},
      'VBUS_RP': {'U_SW2.1', 'U_RPREG.1', 'U_RPREG.3', 'C_RPIN.1'},
    }
    for ch in range(1, 9):
        pair = (ch + 1)//2
        ip, op, dp = (1, 6, 1) if ch % 2 else (3, 4, 2)
        expected[f'CH{ch}_PROT'] = {f'R_IN{ch}.2', f'R_PD{ch}.1', f'U_BUF{pair}.{ip}', f'D_IN{pair}.{dp}'}
        expected[f'FX_D{ch-1}'] = {f'U_BUF{pair}.{op}', f'U_FX.{24+ch}'}
    # BA remains disconnected until the external programming interface is qualified.
    # BP is genuinely buffered; its +3.3V reference supplies only the target side.
    expected.update({
      'BP_TCLK_UNUSED': {'J_BP.1'},
      'BP_DSCLK': {'J_BP.6', 'R_BPCLK.2'},
      'BP_DSI': {'J_BP.4', 'R_BPDI.2'},
      'BP_DSCLK_BUF': {'U_BPX.13', 'R_BPCLK.1'},
      'BP_DSI_BUF': {'U_BPX.12', 'R_BPDI.1'},
      'BP_DSO': {'J_BP.3', 'U_BPX.11', 'R_BPDSO.1'},
      'BP_ALLPST': {'J_BP.5', 'U_BPX.10', 'R_BPALL.1'},
      'BP_BKPT_N': {'J_BP.2', 'Q_BP1.3', 'R_BPPU1.1'},
      'BP_RESET_N': {'J_BP.8', 'Q_BP2.3', 'R_BPPU2.1', 'R_RSTS.1'},
      'BP_RESET_SENSE_IN': {'R_RSTS.2', 'R_RSTPD.1', 'U_RST.2'},
      'RP_BP_RESET_SENSE': {'U_RST.4', 'U_RP.19'},
      'BP_VREF': {'J_BP.7', 'U_BPX.14', 'C_BPB.1', 'R_BPPU1.2', 'R_BPPU2.2', 'R_VTOP.1'},
      'BP_GATE1': {'U_BPAND.7', 'Q_BP1.1', 'R_GATE1.1'},
      'BP_GATE2': {'U_BPAND.3', 'Q_BP2.1', 'R_GATE2.1'},
      'RP_BP_OE': {'U_RP.18', 'U_BPX.8', 'U_BPAND.2', 'U_BPAND.6', 'R_BPOE.1'},
      'RP_BP_DSCLK': {'U_RP.12', 'U_BPX.2'},
      'RP_BP_DSI': {'U_RP.13', 'U_BPX.3'},
      'RP_BP_DSO': {'U_RP.14', 'U_BPX.4'},
      'RP_BP_ALLPST': {'U_RP.17', 'U_BPX.5'},
      'RP_BP_BKPT': {'U_RP.15', 'U_BPAND.1', 'R_REQ1.1'},
      'RP_BP_RESET': {'U_RP.16', 'U_BPAND.5', 'R_REQ2.1'},
      'BP_VREF_DIV': {'R_VTOP.2', 'R_VBOT.1', 'U_SENSE.2'},
      'RP_ADC_BP_VREF': {'U_RP.42', 'U_SENSE.4', 'R_VADC.1', 'C_VADC.1'},
    })
    ba={1:'BA_VPP',2:'BA_VDD_SENSE',4:'BA_PGD',5:'BA_PGC'}
    expected.update({name:{f'J_BA.{pin}'} for pin,name in ba.items()})
    return expected


def check_root(root):
    actual, loose = read_nets(root)
    errors = []
    manifest = json.loads((HERE/'expected-netlist.json').read_text())
    wanted, nc = {}, set()
    for ref,pins in manifest.items():
        for pin,net in pins.items():
            if net is None:nc.add(f'{ref}.{pin}')
            else:wanted.setdefault(net,set()).add(f'{ref}.{pin}')
    for name in wanted.keys() | actual.keys():
        if wanted.get(name) != actual.get(name):errors.append(f'manifest mismatch {name}')
    if loose != nc:errors.append('unconnected pin set changed: '+str(sorted(loose ^ nc)))
    for name,pins in critical_contract().items():
        if actual.get(name) != pins:errors.append(f'architecture violation {name}: {sorted(actual.get(name, []))}')
    # Strap values/polarities are independent of the generated full manifest.
    values={c.get('ref'):c.findtext('value') for c in root.findall('./components/comp')}
    for ref,value in {'R_HCFG0':'100k','R_HCFG1':'10k','R_HNR0':'100k','R_HNR1':'10k','R_HBIAS':'12k 1%', 'R_DM':'27','R_DP':'27','R_BAOE':'100k','R_VPPEN':'100k','R_BPOE':'100k','R_VTOP':'10k 1%','R_VBOT':'20k 1%','R_VADC':'20k 1%','R_GATE1':'100k','R_GATE2':'100k','R_REQ1':'100k','R_REQ2':'100k','R_RSTS':'1k','R_RSTPD':'1M'}.items():
        if values.get(ref)!=value:errors.append(f'critical value changed {ref}')
    for ref in ('R_HCFG0','R_HNR0','R_BAOE','R_VPPEN','R_BPOE','R_GATE1','R_GATE2','R_REQ1','R_REQ2','R_RSTPD'):
        if f'{ref}.2' not in actual.get('GND',set()):errors.append(f'pull-down missing {ref}')
    for ref in ('R_HCFG1','R_HNR1'):
        if f'{ref}.2' not in actual.get('+3V3_HUB',set()):errors.append(f'pull-up missing {ref}')
    for pin in (51,):
        if f'U_FX.{pin}' not in actual.get('+3V3_FX',set()):errors.append('FX2 WAKEUP must be inactive HIGH at reset')
    return errors


def check(path):
    return check_root(ET.parse(path).getroot())


if __name__ == '__main__':
    issues=check(sys.argv[1])
    for issue in issues:print('ERROR',issue)
    print('R0 nets conform; BP digital study; BA boundary remains OPEN' if not issues else 'R0 nets DO NOT conform')
    sys.exit(bool(issues))
