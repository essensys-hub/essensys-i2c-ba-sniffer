"""Detect drift between the separately authored PCB and firmware pin contracts."""
import json
from pathlib import Path
import re


def test_integrated_board_and_firmware_use_the_same_gpio_assignment():
    root = Path(__file__).resolve().parents[1]
    hardware = json.loads((root / "hardware/integrated/gpio-contract.json").read_text())
    header = (root / "firmware/programmer/board_contract.h").read_text()
    firmware = {name: int(number) for name, number in
                re.findall(r"^#define (\w+)_PIN (\d+)u$", header, re.M)}
    aliases = {"ADC_BA_VDD": "BA_VDD_SENSE", "ADC_BA_VPP": "BA_VPP_SENSE",
               "ADC_BP_VREF": "BP_VREF_SENSE"}
    expected = {aliases.get(name, name): number for name, number in hardware["gpio"].items()}
    assert firmware == expected
    assert len(set(firmware.values())) == len(firmware)
    assert hardware["hardware_qualified"] is False
    assert set(hardware["active_high_enables"]) == {"BA_OE", "BA_VPP_EN", "BP_OE"}
