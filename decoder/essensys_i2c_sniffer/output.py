"""Restitution : texte lisible et NDJSON versionné."""

from __future__ import annotations

import json

from . import SCHEMA


def to_ndjson(rec: dict) -> str:
    return json.dumps({"schema": SCHEMA, **rec}, ensure_ascii=False, sort_keys=True)


def _command_text(c: dict) -> str:
    if c["type"] == "drapeau":
        return f"{c['name']} → {c['action']}"
    text = f"{c['type']} {c['index']} → {c['action']}"
    return text + (" (conflit : priorité firmware appliquée)" if c.get("conflict") else "")


def to_text(rec: dict) -> str:
    t = f"{rec.get('t_ms', 0):12.3f} ms"
    kind = rec["type"]
    if kind == "session":
        start = f", début {rec['start_time']}" if rec.get("start_time") else ""
        return f"session {rec['source']} — {rec['samplerate']} Hz{start} — essensys-i2c-sniff {rec.get('tool', '')} (lecture seule)"
    if kind == "exchange" and rec.get("kind") == "empty":
        line = f"{t}  START sans adresse"
        for a in rec.get("anomalies", []):
            line += f"\n{'':15}⚠ {a}"
        return line
    if kind == "exchange":
        head = f"{t}  {rec.get('addr', '?')} {rec.get('ba_name') or 'non résolue'}"
        frame = rec.get("frame", {}).get("name")
        parts = [head]
        if rec.get("kind") == "address_nack":
            parts.append(f"NACK d'adresse — BA absent (n° {rec.get('nack_count', 1)})")
        else:
            if frame:
                parts.append(frame)
            cmds = [c for c in rec.get("commands", []) if c["type"] != "drapeau" or c["action"] == "actif"]
            if rec.get("frame", {}).get("code") == 5:
                cmds = rec.get("commands", [])
            if cmds:
                parts.append(", ".join(_command_text(c) for c in cmds) + " (commande observée)")
            elif rec.get("fields", {}).get("note"):
                parts.append(rec["fields"]["note"])
            parts.append(rec.get("summary", ""))
        if "repeat" in rec:
            parts.append(f"[répétition {rec['repeat']['rank']}]")
        line = " — ".join(p for p in parts if p)
        for a in rec.get("anomalies", []):
            line += f"\n{'':15}⚠ {a}"
        for tr in rec.get("flag_transitions", []):
            line += f"\n{'':15}↳ {tr['flag']} : {'actif' if tr['from'] else 'inactif'} → {'actif' if tr['to'] else 'inactif'}"
        return line
    if kind == "abandon":
        return f"{t}  {rec['addr']} — ⚠ {rec['summary']} ({rec['attempts']} tentative(s))"
    if kind == "correlation":
        return f"{rec.get('log_time', '')}  action {rec['guid']} → {rec['verdict']}"
    return f"{t}  ⚠ {rec.get('summary') or rec.get('message') or rec.get('raw') or kind}"
