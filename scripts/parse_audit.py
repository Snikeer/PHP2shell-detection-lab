#!/usr/bin/env python3
"""
parse_audit.py - apply Sigma rules to auditd log copies.

Runs on the analysis host only, against copies of audit.log.
Never run this on the lab nodes.

Supports the subset of Sigma used in detection/sigma/:
  - one 'selection' block per rule
  - field equality, and lists of values (any value matches)
  - condition: selection
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

RECORD_RE = re.compile(r"^type=(\S+) msg=audit\((\d+\.\d+):(\d+)\):\s?(.*)$")
FIELD_RE = re.compile(r'(\w+)=("[^"]*"|\S+)')
ARG_RE = re.compile(r"^a\d+$")


def parse_fields(text):
    return {name: value.strip('"') for name, value in FIELD_RE.findall(text)}


def read_events(path):
    """Group raw audit records by event id (timestamp:serial)."""
    events = defaultdict(lambda: {"time": None, "records": {}})
    with open(path, errors="replace") as fh:
        for line in fh:
            m = RECORD_RE.match(line.strip())
            if not m:
                continue
            rtype, timestamp, serial, rest = m.groups()
            ev = events[(timestamp, serial)]
            ev["time"] = float(timestamp)
            ev["records"].setdefault(rtype, parse_fields(rest))
    return events


def selection_matches(selection, record):
    for field, expected in selection.items():
        actual = record.get(field)
        if actual is None:
            return False
        allowed = expected if isinstance(expected, list) else [expected]
        if str(actual) not in {str(v) for v in allowed}:
            return False
    return True


def load_rules(rules_dir):
    rules = []
    for path in sorted(Path(rules_dir).glob("*.yml")):
        rule = yaml.safe_load(path.read_text())
        detection = rule.get("detection", {})
        if detection.get("condition") != "selection":
            print(f"skip {path.name}: only 'condition: selection' is supported", file=sys.stderr)
            continue
        rules.append((path.name, rule))
    return rules


def format_hit(ev):
    sc = ev["records"]["SYSCALL"]
    ts = datetime.fromtimestamp(ev["time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = (f"{ts}  key={sc.get('key')} exe={sc.get('exe')} comm={sc.get('comm')} "
            f"uid={sc.get('uid')} auid={sc.get('auid')}")
    execve = ev["records"].get("EXECVE")
    if execve:
        argv = [execve[k] for k in sorted(execve, key=lambda k: int(k[1:]) if ARG_RE.match(k) else -1)
                if ARG_RE.match(k)]
        text += f' argv="{" ".join(argv)}"'
    return text


def main():
    p = argparse.ArgumentParser(description="Apply Sigma rules to an auditd log copy.")
    p.add_argument("logfile", type=Path)
    p.add_argument("--node", required=True, help="label for the output, e.g. php-lab-node")
    p.add_argument("--rules", type=Path, default=Path("detection/sigma"))
    p.add_argument("--since", help='only events at or after "YYYY-MM-DD HH:MM" (UTC)')
    p.add_argument("--show", type=int, default=5, help="matches to print per rule")
    args = p.parse_args()

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()

    events = read_events(args.logfile)
    rules = load_rules(args.rules)
    ordered = sorted(events.values(), key=lambda e: e["time"])

    print(f"Node: {args.node} | log: {args.logfile} | events parsed: {len(events)}")
    if args.since:
        print(f"Filter: since {args.since} UTC")

    for fname, rule in rules:
        selection = rule["detection"]["selection"]
        hits = []
        for ev in ordered:
            if since and ev["time"] < since:
                continue
            syscall = ev["records"].get("SYSCALL")
            if syscall and selection_matches(selection, syscall):
                hits.append(ev)
        print(f"\n[{rule.get('level', '?')}] {rule.get('title', fname)} ({fname}): {len(hits)} match(es)")
        for ev in hits[: args.show]:
            print("  " + format_hit(ev))


if __name__ == "__main__":
    main()
