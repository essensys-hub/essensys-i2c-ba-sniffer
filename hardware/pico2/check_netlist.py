#!/usr/bin/env python3
"""Contrat électrique indépendant du générateur, netlist XML exportée par KiCad.

Contrôle la traversée +15 V isolée des mesures, la sélection bus/IDC et chaque
chaîne entrée -> résistance -> protection/rappel -> tampon -> GPIO. Ne valide
ni un routage, ni une bande passante, ni l'étage ICSP absent de cette étude.
"""
import sys
import xml.etree.ElementTree as ET


def expected_nets():
    nets = {
        "+15V_PASS": {"J1.4", "J2.4"},
        "SDA_BUS": {"J1.1", "J2.1", "JP2.1"},
        "SCL_BUS": {"J1.2", "J2.2", "JP1.1"},
        "+3V3": {"A1.36"} | {f"{ref}{i}.{pin}" for i in range(1, 5) for ref, pin in (("U", 5), ("C", 1))},
        "GND": {"J1.3", "J2.3"} | {f"J3.{i}" for i in range(9, 15)}
               | {f"A1.{i}" for i in (3, 8, 13, 18, 23, 28, 38)}
               | {f"{ref}{i}.{pin}" for i in range(1, 5) for ref, pin in (("U", 2), ("C", 2), ("D", 3))}
               | {f"R{i}.2" for i in range(9, 17)},
    }
    for ch, pico in enumerate((1, 2, 4, 5, 6, 7, 9, 10), 1):
        pair = (ch + 1) // 2
        odd = ch % 2 == 1
        nets[f"CH{ch}_IDC"] = {f"J3.{ch}", f"JP{ch}.3" if ch <= 2 else f"R{ch}.1"}
        if ch <= 2:
            nets[f"CH{ch}_SOURCE"] = {f"JP{ch}.2", f"R{ch}.1"}
        nets[f"CH{ch}_IN"] = {f"R{ch}.2", f"R{ch + 8}.1",
                                f"D{pair}.{1 if odd else 2}", f"U{pair}.{1 if odd else 3}"}
        nets[f"GPIO{ch - 1}"] = {f"U{pair}.{6 if odd else 4}", f"A1.{pico}"}
    return nets


def check(path):
    root = ET.parse(path).getroot()
    actual, loose = {}, set()
    for net in root.findall("./nets/net"):
        name = net.attrib["name"].lstrip("/")
        pins = {f"{p.attrib['ref']}.{p.attrib['pin']}" for p in net.findall("node")
                if not p.attrib["ref"].startswith("#")}
        if name.startswith("unconnected-"):
            loose |= pins
        elif pins:
            if name in actual:
                raise ValueError(f"net ambigu : {name}")
            actual[name] = pins
    expected = expected_nets()
    errors = [f"{net}: attendu {sorted(expected.get(net, []))}, obtenu {sorted(actual.get(net, []))}"
              for net in expected.keys() | actual.keys() if expected.get(net) != actual.get(net)]
    used = set().union(*expected.values())
    unused = {f"A1.{i}" for i in range(1, 41)} - used
    if loose != unused:
        errors.append(f"NC inattendus : {sorted(loose ^ unused)}")
    return errors


if __name__ == "__main__":
    errors = check(sys.argv[1])
    for error in errors:
        print("ÉCART", error)
    print("Netlist capture conforme" if not errors else "Netlist capture NON conforme")
    sys.exit(bool(errors))
