#!/usr/bin/env python3
"""Hand root outputs to the roots that consume them (Step 1 item 6).

Workstation only, like run.py. ``network`` reads the applied network root's
``network`` output and writes it as ``network_reference`` into the untracked
``local.auto.tfvars`` of the platform and developer-access roots, replacing an
existing assignment or appending one. The output's scope must name the same
account as each target's ``aws_account_id``. Nothing else in the file changes,
and no AWS API is called beyond what ``terraform output`` needs for the network
root's backend.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight  # noqa: E402

TARGETS = ("platform", "developer-access")


def terraform_output(terraform, root, name, env):
    process = subprocess.run([terraform, "-chdir=" + str(root), "output", "-json", name], env=env,
                             capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise preflight.PreflightError("terraform_output_failed:" + name + " (apply the root first)")
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise preflight.PreflightError("terraform_output_shape:" + name)
    return value


def assignment_span(text, key):
    """(start, end) of a top-level `key = ...` assignment with balanced braces, or None."""
    match = re.search(r"(?m)^" + re.escape(key) + r"\s*=\s*", text)
    if not match:
        return None
    index, depth, quote = match.end(), 0, False
    while index < len(text):
        char = text[index]
        if quote:
            quote = not (char == '"' and text[index - 1] != "\\")
        elif char == '"':
            quote = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return match.start(), index + 1
        elif char == "\n" and depth == 0:
            return match.start(), index
        index += 1
    raise preflight.PreflightError("unbalanced_assignment:" + key)


def write_assignment(path, key, value):
    """Replace or append `key = <value>` in a tfvars file; JSON is a valid HCL expression."""
    rendered = key + " = " + json.dumps(value, indent=2, sort_keys=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    span = assignment_span(text, key)
    if span:
        text = text[:span[0]] + rendered + text[span[1]:]
    else:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + rendered + "\n"
    path.write_text(text, encoding="utf-8")


def handoff_network(terraform="terraform", services=preflight.SERVICES, env=None, out=print):
    environment = dict(os.environ if env is None else env)
    refusal = preflight.automation_refusal(environment)
    if refusal:
        out("Refused (" + refusal + "): hand-off runs only on the operator's workstation.")
        return 1
    network = terraform_output(terraform, Path(services) / "network", "network", environment)
    account = network.get("scope", {}).get("account_id")
    # Check every target before writing any, so a refusal leaves all files unchanged.
    for name in TARGETS:
        root = Path(services) / name
        local = root / preflight.LOCAL_FILE
        findings = preflight.local_file_findings(name, root) if local.is_file() else ["local_tfvars_missing"]
        findings = [f for f in findings if not f.startswith("local_value_missing:")]
        if findings:
            out("Refused for " + name + ": " + ", ".join(findings) + " (copy local.auto.tfvars.example first)")
            return 1
        if preflight.local_value(root, "aws_account_id") != account:
            out("Refused for " + name + ": the network output belongs to another account than aws_account_id")
            return 1
    for name in TARGETS:
        local = Path(services) / name / preflight.LOCAL_FILE
        write_assignment(local, "network_reference", network)
        out("Wrote network_reference to " + str(local))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", choices=["network"])
    parser.add_argument("--terraform", default="terraform")
    args = parser.parse_args(argv)
    try:
        return handoff_network(args.terraform)
    except (preflight.PreflightError, json.JSONDecodeError, OSError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
