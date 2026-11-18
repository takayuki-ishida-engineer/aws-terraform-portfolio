#!/usr/bin/env python3
"""Verify the developer_access native test events against the actual mock plans.

Reads `terraform test -json -verbose` events (optionally compacted by the EKS
checker's --compact filter) and independently checks each positive plan's
resource set, IAM trust and policy, network exposure and instance hardening,
and each negative run's variable diagnostic. A source contract rejects SSH keys,
user data, inbound rules and inline security group rules. --self-test applies
semantic mutations, capture failures and source mutations and requires each to
be rejected. Offline; no AWS API is called.
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1]
PREFIX_NAME = "test-dev"
RESOURCES = {"aws_iam_role.this", "aws_iam_role_policy_attachment.ssm", "aws_iam_instance_profile.this",
             "aws_security_group.this", "aws_vpc_security_group_egress_rule.vpc_https", "aws_instance.this"}
DEFAULT_TAGS = {"project": "test", "env": "dev", "managed": "terraform"}
POSITIVE = {
    "default_access_host": {"instance_type": "t3.micro", "tags": {}},
    "custom_type_and_tags": {"instance_type": "t3.small", "tags": {"owner": "platform"}},
}
NEGATIVE = {
    "rejects_invalid_ami": ("ami_id", "ami_id must look like"),
    "rejects_invalid_subnet": ("subnet_id", "subnet_id must look like"),
    "rejects_invalid_vpc": ("vpc_id", "vpc_id must look like"),
    "rejects_non_canonical_cidr": ("vpc_cidr", "canonical IPv4"),
    "rejects_wide_cidr": ("vpc_cidr", "canonical IPv4"),
    "rejects_unsupported_instance_type": ("instance_type", "instance_type must be"),
    "rejects_name_tag": ("tags", "must not set Name, service"),
    "rejects_aws_prefixed_tag": ("tags", "must not set Name, service"),
    "rejects_extra_default_tag": ("default_tags", "default_tags may hold only"),
    "rejects_invalid_name_prefix": ("name_prefix", "name_prefix must be"),
}
TRUST = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"Service": "ec2.amazonaws.com"}}]}
SSM_POLICY = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def only(items, code):
    require(isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict), code)
    return items[0]


def check_plan(run, plan, expected, inputs=None):
    """Check one positive plan; ``inputs`` holds vpc_id, vpc_cidr, subnet_id, ami_id."""
    inputs = inputs or {"vpc_id": "vpc-0123456789abcdef0", "vpc_cidr": "10.40.0.0/16",
                        "subnet_id": "subnet-0123456789abcdef0", "ami_id": "ami-0123456789abcdef0"}
    changes = plan.get("resource_changes") or []
    require({c.get("address") for c in changes} == RESOURCES and len(changes) == len(RESOURCES), "resource_set:" + run)
    after = {}
    for change in changes:
        require(change.get("mode") == "managed" and change["change"].get("actions") == ["create"], "create_only:" + run)
        after[change["address"]] = change["change"].get("after") or {}
    tags = expected["tags"]
    role, attach, profile = after["aws_iam_role.this"], after["aws_iam_role_policy_attachment.ssm"], after["aws_iam_instance_profile.this"]
    require(role.get("name") == PREFIX_NAME + "-role-bastion" and json.loads(role.get("assume_role_policy", "{}")) == TRUST
            and role.get("max_session_duration") == 3600 and role.get("tags") == {**tags, "Name": PREFIX_NAME + "-role-bastion", "service": "role"},
            "role:" + run)
    require(attach.get("policy_arn") == SSM_POLICY and attach.get("role") == role["name"], "managed_policy:" + run)
    require(profile.get("name") == PREFIX_NAME + "-profile-bastion" and profile.get("role") == role["name"]
            and profile.get("tags") == {**tags, "Name": PREFIX_NAME + "-profile-bastion", "service": "profile"}, "instance_profile:" + run)
    group, rule = after["aws_security_group.this"], after["aws_vpc_security_group_egress_rule.vpc_https"]
    require(group.get("name") == PREFIX_NAME + "-sg-bastion" and group.get("vpc_id") == inputs["vpc_id"]
            and group.get("tags") == {**tags, "Name": PREFIX_NAME + "-sg-bastion", "service": "sg"}, "security_group:" + run)
    require(rule.get("security_group_id") == group.get("id") and rule.get("cidr_ipv4") == inputs["vpc_cidr"]
            and rule.get("ip_protocol") == "tcp" and rule.get("from_port") == 443 and rule.get("to_port") == 443
            and not rule.get("cidr_ipv6") and not rule.get("prefix_list_id") and not rule.get("referenced_security_group_id")
            and rule.get("tags") == {**tags, "Name": PREFIX_NAME + "-sg-bastion-out-vpc-https", "service": "sg"}, "egress_rule:" + run)
    instance = after["aws_instance.this"]
    require(instance.get("ami") == inputs["ami_id"] and instance.get("instance_type") == expected["instance_type"]
            and instance.get("subnet_id") == inputs["subnet_id"] and instance.get("vpc_security_group_ids") == [group.get("id")]
            and instance.get("iam_instance_profile") == profile["name"], "instance_binding:" + run)
    require(instance.get("associate_public_ip_address") is False and instance.get("user_data") is None
            and instance.get("monitoring") is False, "instance_private:" + run)
    metadata = only(instance.get("metadata_options"), "metadata_shape:" + run)
    require(metadata.get("http_endpoint") == "enabled" and metadata.get("http_tokens") == "required"
            and metadata.get("http_put_response_hop_limit") == 1 and metadata.get("instance_metadata_tags") == "disabled", "imdsv2:" + run)
    volume = only(instance.get("root_block_device"), "root_volume_shape:" + run)
    require(volume.get("encrypted") is True and volume.get("volume_type") == "gp3" and volume.get("delete_on_termination") is True
            and volume.get("tags") == {**DEFAULT_TAGS, **tags, "Name": PREFIX_NAME + "-ec2-bastion-root", "service": "ec2"}, "root_volume:" + run)
    require(instance.get("tags") == {**tags, "Name": PREFIX_NAME + "-ec2-bastion", "service": "ec2"}, "instance_tags:" + run)


def source_contract(source=None):
    source = source or "\n".join(p.read_text(encoding="utf-8") for p in sorted(MODULE.glob("*.tf")))
    code = re.sub(r"(?m)#.*$", "", source)
    require(not re.search(r"\b(key_name|user_data|user_data_base64)\s*=", code), "no_ssh_key_or_user_data")
    require('resource "aws_vpc_security_group_ingress_rule"' not in code and not re.search(r"\b(ingress|egress)\s*\{", code), "no_inbound_or_inline_rules")
    require(re.search(r"associate_public_ip_address\s*=\s*false", code) and re.search(r'http_tokens\s*=\s*"required"', code), "private_imdsv2_source")
    require(code.count('resource "aws_iam_role_policy_attachment"') == 1 and "AmazonSSMManagedInstanceCore" in code
            and 'resource "aws_iam_role_policy"' not in code, "single_managed_policy")
    require(not re.search(r'(?m)^\s*(provider|data)\s+"', code), "no_child_provider_or_discovery")
    return True


def verify(events, exit_code):
    require(exit_code == 0, "terraform_exit")
    require([e.get("terraform") for e in events if e.get("type") == "version"] == ["1.17.0"], "version")
    expected_runs = set(POSITIVE) | set(NEGATIVE)
    abstracts = [e.get("test_abstract") for e in events if e.get("type") == "test_abstract"]
    require(len(abstracts) == 1 and len(abstracts[0]) == 1 and set(next(iter(abstracts[0].values()))) == expected_runs, "manifest")
    terminals = [(e["test_run"].get("run"), e["test_run"].get("status")) for e in events
                 if e.get("type") == "test_run" and "status" in e.get("test_run", {})]
    require(sorted(terminals) == sorted((run, "pass") for run in expected_runs), "run_terminals")
    require([e.get("test_summary") for e in events if e.get("type") == "test_summary"]
            == [{"status": "pass", "passed": len(expected_runs), "failed": 0, "errored": 0, "skipped": 0}], "summary")
    plans = {}
    for event in events:
        if event.get("type") == "test_plan":
            require(event.get("@testrun") not in plans, "duplicate_plan")
            plans[event.get("@testrun")] = event.get("test_plan") or {}
    for run, expected in POSITIVE.items():
        require(run in plans, "missing_plan:" + run)
        check_plan(run, plans[run], expected)
    for run, (_variable, fragment) in NEGATIVE.items():
        errors = [e["diagnostic"] for e in events if e.get("type") == "diagnostic" and e.get("@testrun") == run
                  and e.get("diagnostic", {}).get("severity") == "error"]
        require(errors and all(d.get("summary") == "Invalid value for variable" for d in errors)
                and any(fragment in d.get("detail", "") for d in errors), "negative:" + run)
    require(not [e for e in events if e.get("type") == "diagnostic" and e.get("diagnostic", {}).get("severity") == "error"
                 and e.get("@testrun") not in NEGATIVE], "unexpected_error_diagnostic")
    source_contract()
    return {"status": "passed", "evidence_type": "actual_mock_plan_verification", "aws_api_calls": 0,
            "native_tests": len(expected_runs), "positive_plans": len(POSITIVE), "negative_cases": len(NEGATIVE)}


def after_of(events, address, run="default_access_host"):
    plan = next(e for e in events if e.get("type") == "test_plan" and e.get("@testrun") == run)["test_plan"]
    return next(r for r in plan["resource_changes"] if r["address"] == address)["change"]["after"]


def semantic_mutations():
    inst, rule, role = "aws_instance.this", "aws_vpc_security_group_egress_rule.vpc_https", "aws_iam_role.this"
    yield "public_ip", lambda e: after_of(e, inst).update(associate_public_ip_address=True)
    yield "user_data", lambda e: after_of(e, inst).update(user_data="#!/bin/sh")
    yield "imdsv1", lambda e: after_of(e, inst)["metadata_options"][0].update(http_tokens="optional")
    yield "imds_hop_2", lambda e: after_of(e, inst)["metadata_options"][0].update(http_put_response_hop_limit=2)
    yield "unencrypted_root", lambda e: after_of(e, inst)["root_block_device"][0].update(encrypted=False)
    yield "other_subnet", lambda e: after_of(e, inst).update(subnet_id="subnet-0fedcba9876543210")
    yield "extra_security_group", lambda e: after_of(e, inst).update(vpc_security_group_ids=["sg-0123456789abcdef0", "sg-0aaaaaaaaaaaaaaaa"])
    yield "egress_world", lambda e: after_of(e, rule).update(cidr_ipv4="0.0.0.0/0")
    yield "egress_ssh", lambda e: after_of(e, rule).update(from_port=22, to_port=22)
    yield "egress_prefix_list", lambda e: after_of(e, rule).update(prefix_list_id="pl-12345678")
    yield "trust_any_service", lambda e: after_of(e, role).update(assume_role_policy=json.dumps(
        {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"AWS": "*"}}]}))
    yield "admin_policy", lambda e: after_of(e, "aws_iam_role_policy_attachment.ssm").update(policy_arn="arn:aws:iam::aws:policy/AdministratorAccess")
    yield "instance_tags", lambda e: after_of(e, inst)["tags"].update(service="other")


def capture_failures():
    def drop(kind):
        return lambda e: e.__setitem__(slice(None), [x for x in e if x.get("type") != kind])

    def extra_resource(e):
        plan = next(x for x in e if x.get("type") == "test_plan" and x.get("@testrun") == "custom_type_and_tags")["test_plan"]
        extra = copy.deepcopy(plan["resource_changes"][0]);extra["address"] = "aws_vpc_security_group_ingress_rule.ssh"
        plan["resource_changes"].append(extra)

    def failed_run(e):
        next(x for x in e if x.get("type") == "test_run" and x["test_run"].get("run") == "rejects_name_tag" and "status" in x["test_run"])["test_run"]["status"] = "fail"

    yield "no_version", drop("version")
    yield "no_summary", drop("test_summary")
    yield "no_plans", drop("test_plan")
    yield "extra_resource", extra_resource
    yield "failed_run", failed_run
    yield "lost_negative", lambda e: e.__setitem__(slice(None), [x for x in e if not (x.get("type") == "diagnostic" and x.get("@testrun") == "rejects_wide_cidr")])


def source_mutations():
    base = "\n".join(p.read_text(encoding="utf-8") for p in sorted(MODULE.glob("*.tf")))
    for name, old, new in [
        ("ssh_key", "monitoring                  = false", 'monitoring                  = false\n  key_name = "operator"'),
        ("public_ip", "associate_public_ip_address = false", "associate_public_ip_address = true"),
        ("imdsv1", 'http_tokens                 = "required"', 'http_tokens                 = "optional"'),
        ("inbound_rule", 'resource "aws_instance" "this" {', 'resource "aws_vpc_security_group_ingress_rule" "ssh" {}\nresource "aws_instance" "this" {'),
        ("extra_policy", 'resource "aws_iam_instance_profile" "this" {', 'resource "aws_iam_role_policy" "extra" {}\nresource "aws_iam_instance_profile" "this" {'),
    ]:
        require(old in base, "source_mutation_witness:" + name)
        yield name, base.replace(old, new, 1)


def self_test(events):
    counts = {"semantic_mutations": 0, "capture_failure_injections": 0, "source_mutations": 0}
    for name, mutate in semantic_mutations():
        mutated = copy.deepcopy(events);mutate(mutated)
        try:
            verify(mutated, 0)
        except (ValueError, KeyError, TypeError, StopIteration):
            counts["semantic_mutations"] += 1;continue
        raise ValueError("mutation_not_detected:" + name)
    for name, mutate in capture_failures():
        mutated = copy.deepcopy(events);mutate(mutated)
        try:
            verify(mutated, 0)
        except (ValueError, KeyError, TypeError, StopIteration):
            counts["capture_failure_injections"] += 1;continue
        raise ValueError("mutation_not_detected:" + name)
    for name, source in source_mutations():
        try:
            source_contract(source)
        except ValueError:
            counts["source_mutations"] += 1;continue
        raise ValueError("mutation_not_detected:" + name)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-events", required=True)
    parser.add_argument("--terraform-exit-code", type=int, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        with open(args.test_events, encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        report = verify(events, args.terraform_exit_code)
        if args.self_test:
            report.update(self_test(events))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print("developer_access verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
