#!/usr/bin/env python3
"""Fail-closed verification of actual credential-free VPC/DEV network mock plans.

Only provider schemas are discarded by --compact. Plans, diagnostics, identities,
unknown markers and terminal evidence are preserved. No AWS calls are made.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
MODULE = HERE.parent
ROOT = REPO / "infra/services/dev/ca-central-1/network"
PROVIDER = "registry.terraform.io/hashicorp/aws"
ORIGINAL_SHA256 = "ba1eb4e7881f462b8cebe5c97d766b3fbbcc494d6015f46b5561e2174a35bbdd"  # Step 1 PR 2b: naming/tag rules only; F8: the legacy shared table is now aws_route_table.private[0] (address only, same assertions).


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key:" + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("nonfinite_json:" + value)


def parse(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    require(type(value) is bool, "invalid_unknown_marker")
    return value


def known(change, key):
    require(key in change["after"] and not unknown(change["after_unknown"].get(key, False)), "missing_or_unknown:" + key)
    return change["after"][key]


def address(kind, name, key=None):
    return kind + "." + name + ("[" + json.dumps(key) + "]" if key is not None else "")


def verify_endpoint_policy(text, account_id):
    """Check AWS gateway semantics independently of fixture/plan equality.

    Gateway Principal must be '*'. ArnEquals also supports wildcard patterns in
    AWS, so literal same-account role ARN validation is essential. Conditions on
    role ARNs match the role identity, not an STS assumed-role session ARN.
    """
    policy = parse(text)
    require(isinstance(policy, dict) and set(policy) == {"Version", "Statement"}
        and policy["Version"] == "2012-10-17", "endpoint_policy_document")
    statements = policy["Statement"]
    require(isinstance(statements, list) and statements, "endpoint_statement_array")

    def strings(value):
        values = [value] if isinstance(value, str) else value
        require(isinstance(values, list) and values and all(isinstance(v, str) and v for v in values), "endpoint_nonempty_strings")
        return values

    role_pattern = r"arn:aws:iam::" + re.escape(account_id) + r":role/([A-Za-z0-9_+=,.@-]+/)*[A-Za-z0-9_+=,.@-]{1,64}"
    bucket_pattern = r"arn:aws:s3:::[a-z0-9][a-z0-9.-]{1,61}[a-z0-9](/[^*?]*\*?)?"
    bucket_actions = {"s3:ListBucket", "s3:GetBucketLocation"}
    object_actions = {"s3:GetObject", "s3:GetObjectVersion"}
    for statement in statements:
        require(isinstance(statement, dict)
            and {"Effect", "Principal", "Action", "Resource", "Condition"} <= set(statement)
            and set(statement) <= {"Sid", "Effect", "Principal", "Action", "Resource", "Condition"}
            and statement["Effect"] == "Allow" and statement["Principal"] == "*", "endpoint_gateway_principal")
        condition = statement["Condition"]
        require(isinstance(condition, dict) and set(condition) == {"ArnEquals"}
            and isinstance(condition["ArnEquals"], dict)
            and set(condition["ArnEquals"]) == {"aws:PrincipalArn"}, "endpoint_role_condition")
        roles = strings(condition["ArnEquals"]["aws:PrincipalArn"])
        require(all(re.fullmatch(role_pattern, role) for role in roles), "endpoint_literal_same_account_roles")
        actions, resources = strings(statement["Action"]), strings(statement["Resource"])
        require(set(actions) <= bucket_actions | object_actions, "endpoint_read_only_actions")
        require(all(re.fullmatch(bucket_pattern, resource) for resource in resources), "endpoint_scoped_resources")
        require(all(("/" not in resource) if action in bucket_actions else ("/" in resource)
            for action in actions for resource in resources), "endpoint_action_resource_scope")
    return policy


def inventory(inputs):
    per_az = inputs.get("private_routing", {}).get("mode", "legacy_shared") == "per_az"
    # The shared private table exists only in legacy_shared routing (finding F8).
    result = {"aws_vpc.this"} | (set() if per_az else {"aws_route_table.private[0]"})
    for group in ("private", "public"):
        for key in inputs.get(group + "_subnets", {}):
            result |= {address("aws_subnet", group, key), address("aws_route_table_association", group, key)}
    if inputs.get("public_subnets"):
        result |= {"aws_internet_gateway.this[0]", "aws_route_table.public[0]"}
    if per_az:
        result |= {address("aws_route_table", "private_by_az", v["availability_zone"]) for v in inputs["private_subnets"].values()}
        nat = inputs["private_routing"].get("nat") or {}
        for az in nat.get("public_subnet_key_by_nat_az", {}):
            result |= {address("aws_eip", "nat", az), address("aws_nat_gateway", "this", az)}
        result |= {address("aws_route", "private_nat", az) for az in nat.get("nat_az_by_private_az", {})}
        result |= {address("aws_vpc_endpoint", "gateway", service) for service in inputs.get("gateway_endpoints", {})}
        interface = inputs.get("interface_endpoints")
        if interface:
            result |= {"aws_security_group.endpoints[0]", "aws_vpc_security_group_ingress_rule.endpoints_https[0]"}
            result |= {address("aws_vpc_endpoint", "interface", service) for service in interface["services"]}
    return result


def expected_owned_tags(inputs):
    """Exact module-owned Name and service tags per taggable address.

    Names follow docs/deployment-configuration.md section 4 and tags section 5:
    <prefix>[-<az letter>]-<type>[-<purpose>], with service set to the type token.
    """
    prefix = inputs["name_prefix"]
    per_az = inputs.get("private_routing", {}).get("mode", "legacy_shared") == "per_az"
    owned = {"aws_vpc.this": (prefix + "-vpc", "vpc")}
    if not per_az:
        owned["aws_route_table.private[0]"] = (prefix + "-rtb-private", "rtb")
    for group in ("private", "public"):
        for key, subnet in inputs.get(group + "_subnets", {}).items():
            owned[address("aws_subnet", group, key)] = (f"{prefix}-{subnet['availability_zone'][-1]}-subnet-{key}", "subnet")
    if inputs.get("public_subnets"):
        owned["aws_internet_gateway.this[0]"] = (prefix + "-igw", "igw")
        owned["aws_route_table.public[0]"] = (prefix + "-rtb-public", "rtb")
    if per_az:
        for az in {v["availability_zone"] for v in inputs["private_subnets"].values()}:
            first = sorted(k for k, v in inputs["private_subnets"].items() if v["availability_zone"] == az)[0]
            owned[address("aws_route_table", "private_by_az", az)] = (f"{prefix}-{az[-1]}-rtb-{first}", "rtb")
        nat = inputs["private_routing"].get("nat") or {}
        for az in nat.get("public_subnet_key_by_nat_az", {}):
            owned[address("aws_eip", "nat", az)] = (f"{prefix}-{az[-1]}-eip-nat", "eip")
            owned[address("aws_nat_gateway", "this", az)] = (f"{prefix}-{az[-1]}-nat", "nat")
        endpoints = inputs.get("gateway_endpoints", {})
        interface = inputs.get("interface_endpoints") or {"services": []}
        # Every endpoint gets a purpose once more than one endpoint exists.
        total = len(endpoints) + len(interface["services"])
        for key in endpoints:
            owned[address("aws_vpc_endpoint", "gateway", key)] = (f"{prefix}-vpce-{key}" if total > 1 else prefix + "-vpce", "vpce")
        for service in interface["services"]:
            owned[address("aws_vpc_endpoint", "interface", service)] = (f"{prefix}-vpce-{service.replace('.', '-')}", "vpce")
        if interface["services"]:
            owned["aws_security_group.endpoints[0]"] = (prefix + "-sg-vpce", "sg")
            owned["aws_vpc_security_group_ingress_rule.endpoints_https[0]"] = (prefix + "-sg-vpce-in-vpc-https", "sg")
    return {addr: {"Name": name, "service": service} for addr, (name, service) in owned.items()}


def changes_of(plan, prefix="", allow_empty=False):
    require(isinstance(plan, dict) and plan.get("plan_format_version") == "1.2", "plan_format")
    rows = plan.get("resource_changes", [] if allow_empty else None)
    require(isinstance(rows, list), "resource_changes_missing")
    result = {}
    for item in rows:
        require(isinstance(item, dict), "resource_shape")
        full = item.get("address", "")
        require(full.startswith(prefix), "resource_module_boundary")
        relative = full[len(prefix):]
        require(relative not in result, "duplicate_resource")
        pattern = r'(aws_[a-z0-9_]+)\.([a-z0-9_]+)(?:\[("[^"\\]+"|0)\])?'
        match = re.fullmatch(pattern, relative)
        require(match and item.get("type") == match[1] and item.get("name") == match[2], "resource_identity")
        require(item.get("index") == (json.loads(match[3]) if match[3] is not None else None), "resource_index")
        require(item.get("module_address", "") == prefix.rstrip("."), "module_address")
        require(item.get("provider_name") == PROVIDER and item.get("mode") == "managed", "provider_or_mode")
        change = item.get("change", {})
        require(change.get("actions") == ["create"] and "before" in change and change["before"] is None, "unexpected_resource_action")
        require(isinstance(change.get("after"), dict) and isinstance(change.get("after_unknown"), dict), "resource_change_shape")
        unknown(change["after_unknown"])
        result[relative] = change
    return result


def verify_plan(plan, inputs, scope):
    prefix = "module.network." if scope == "root" else ""
    resources = changes_of(plan, prefix)
    require(set(resources) == inventory(inputs), "complete_resource_inventory")
    per_az = inputs.get("private_routing", {}).get("mode", "legacy_shared") == "per_az"
    nat = inputs.get("private_routing", {}).get("nat") or {}
    azs = {v["availability_zone"] for v in inputs["private_subnets"].values()}
    ids = {}
    def read(addr, field):
        return known(resources[addr], field)
    def same(addr, field, expected):
        require(read(addr, field) == expected, "resource_contract:" + addr + ":" + field)
    for addr in resources:
        if addr.startswith(("aws_vpc.", "aws_subnet.", "aws_route_table.", "aws_nat_gateway.", "aws_eip.", "aws_internet_gateway.", "aws_vpc_endpoint.",
                            "aws_security_group.", "aws_vpc_security_group_ingress_rule.")):
            identity = read(addr, "id")
            require(isinstance(identity, str) and identity and identity not in ids.values(), "distinct_resource_ids")
            ids[addr] = identity
    vpc = ids["aws_vpc.this"]
    same("aws_vpc.this", "cidr_block", inputs["vpc_cidr"])
    for field, value in {"enable_dns_support": True, "enable_dns_hostnames": True, "assign_generated_ipv6_cidr_block": False}.items():
        same("aws_vpc.this", field, value)
    if per_az:
        expected = inputs["expected_scope"]
        same("aws_vpc.this", "arn", f"arn:{expected['partition']}:ec2:{expected['region']}:{expected['account_id']}:vpc/{vpc}")
    selected = {az: ids[address("aws_route_table", "private_by_az", az)] if per_az else ids["aws_route_table.private[0]"] for az in azs}
    for group in ("private", "public"):
        for key, subnet in inputs.get(group + "_subnets", {}).items():
            addr = address("aws_subnet", group, key)
            for field in ("cidr_block", "availability_zone"):
                same(addr, field, subnet[field])
            same(addr, "vpc_id", vpc)
            same(addr, "map_public_ip_on_launch", False)
            same(addr, "assign_ipv6_address_on_creation", False)
            assoc = address("aws_route_table_association", group, key)
            same(assoc, "subnet_id", ids[addr])
            same(assoc, "route_table_id", selected[subnet["availability_zone"]] if group == "private" else ids["aws_route_table.public[0]"])
    if not per_az:
        same("aws_route_table.private[0]", "vpc_id", vpc)
        same("aws_route_table.private[0]", "route", [])
    for az in azs if per_az else []:
        addr = address("aws_route_table", "private_by_az", az)
        same(addr, "vpc_id", vpc)
        same(addr, "route", [])
    if inputs.get("public_subnets"):
        same("aws_internet_gateway.this[0]", "vpc_id", vpc)
        same("aws_route_table.public[0]", "vpc_id", vpc)
        routes = read("aws_route_table.public[0]", "route")
        require(isinstance(routes, list) and len(routes) == 1, "public_default_inventory")
        route = routes[0]
        require(route.get("cidr_block") == "0.0.0.0/0" and route.get("gateway_id") == ids["aws_internet_gateway.this[0]"], "public_igw_default")
        require(all(not value for key, value in route.items() if key not in {"cidr_block", "gateway_id"}), "public_competing_route_target")
    for az, key in nat.get("public_subnet_key_by_nat_az", {}).items():
        eip = address("aws_eip", "nat", az); gateway = address("aws_nat_gateway", "this", az)
        same(eip, "domain", "vpc")
        same(gateway, "availability_mode", "zonal")
        same(gateway, "connectivity_type", "public")
        same(gateway, "allocation_id", ids[eip])
        same(gateway, "subnet_id", ids[address("aws_subnet", "public", key)])
        require(inputs["public_subnets"][key]["availability_zone"] == az, "nat_subnet_az")
    for az, target in nat.get("nat_az_by_private_az", {}).items():
        addr = address("aws_route", "private_nat", az)
        same(addr, "route_table_id", selected[az]);same(addr, "destination_cidr_block", "0.0.0.0/0")
        same(addr, "nat_gateway_id", ids[address("aws_nat_gateway", "this", target)])
        for field in ("gateway_id", "transit_gateway_id", "egress_only_gateway_id", "vpc_peering_connection_id", "carrier_gateway_id", "core_network_arn", "local_gateway_id", "odb_network_arn", "vpc_endpoint_id", "destination_ipv6_cidr_block", "destination_prefix_list_id"):
            require(not read(addr, field), "competing_nat_route_target:" + field)
        # Provider-derived EC2 instance/ENI metadata is legitimately unknown at plan.
        # A configured non-null alternate target is still rejected.
        for field in ("network_interface_id", "instance_id"):
            require(resources[addr]["after"].get(field) is None, "configured_alternate_target:" + field)
    for service, endpoint in inputs.get("gateway_endpoints", {}).items():
        addr = address("aws_vpc_endpoint", "gateway", service)
        same(addr, "vpc_id", vpc);same(addr, "vpc_endpoint_type", "Gateway")
        same(addr, "service_name", "com.amazonaws.ca-central-1.s3")
        require(set(read(addr, "route_table_ids")) == {selected[az] for az in endpoint["private_route_table_azs"]}, "endpoint_tables")
        actual_policy = verify_endpoint_policy(read(addr, "policy"), inputs["expected_scope"]["account_id"])
        reviewed_policy = verify_endpoint_policy(endpoint["policy_json"], inputs["expected_scope"]["account_id"])
        require(actual_policy == reviewed_policy, "endpoint_reviewed_policy")
        for field in ("subnet_ids", "security_group_ids"):
            require(not read(addr, field), "gateway_interface_associations")
    interface = inputs.get("interface_endpoints") if per_az else None
    if interface:
        group, rule = "aws_security_group.endpoints[0]", "aws_vpc_security_group_ingress_rule.endpoints_https[0]"
        same(group, "vpc_id", vpc)
        same(group, "name", inputs["name_prefix"] + "-sg-vpce")
        same(rule, "security_group_id", ids[group])
        same(rule, "cidr_ipv4", inputs["vpc_cidr"])
        same(rule, "ip_protocol", "tcp");same(rule, "from_port", 443);same(rule, "to_port", 443)
        for field in ("cidr_ipv6", "prefix_list_id", "referenced_security_group_id"):
            require(not resources[rule]["after"].get(field), "endpoint_rule_single_source:" + field)
        subnets = sorted(ids[address("aws_subnet", "private", key)] for key in interface["subnet_keys"])
        for service in interface["services"]:
            addr = address("aws_vpc_endpoint", "interface", service)
            same(addr, "vpc_id", vpc);same(addr, "vpc_endpoint_type", "Interface")
            same(addr, "service_name", "com.amazonaws.ca-central-1." + service)
            same(addr, "private_dns_enabled", True)
            require(sorted(read(addr, "subnet_ids")) == subnets, "interface_endpoint_subnets")
            require(read(addr, "security_group_ids") == [ids[group]], "interface_endpoint_security_group")
            require(not resources[addr]["after"].get("route_table_ids"), "interface_endpoint_route_tables")
    # Exact module-owned Name/service tags win over caller tags; nothing else is injected.
    # Root-wide project/env/managed tags come from provider default_tags, not resource tags.
    owned = expected_owned_tags(inputs)
    require(set(owned) == set(ids), "tagged_resource_inventory")
    for addr, owned_tags in owned.items():
        actual = read(addr, "tags")
        require(isinstance(actual, dict) and actual == {**inputs.get("tags", {}), **owned_tags}, "resource_name_and_service_tags")
    expected_outputs = {
        "vpc_id": vpc, "vpc_cidr": inputs["vpc_cidr"],
        "private_subnet_ids": {k: ids[address("aws_subnet", "private", k)] for k in inputs["private_subnets"]},
        "public_subnet_ids": {k: ids[address("aws_subnet", "public", k)] for k in inputs.get("public_subnets", {})},
        "private_route_table_id": None if per_az else ids["aws_route_table.private[0]"],
        "public_route_table_id": ids.get("aws_route_table.public[0]"),
        "internet_gateway_id": ids.get("aws_internet_gateway.this[0]"),
        "private_route_table_ids_by_az": selected,
        "private_route_table_ids_by_subnet": {k: selected[v["availability_zone"]] for k, v in inputs["private_subnets"].items()},
        "subnet_azs": {g: {k: v["availability_zone"] for k, v in inputs.get(g + "_subnets", {}).items()} for g in ("private", "public")},
        "nat_gateway_ids_by_az": {az: ids[address("aws_nat_gateway", "this", az)] for az in nat.get("public_subnet_key_by_nat_az", {})},
        "nat_eips_by_az": {az: {"allocation_id": ids[address("aws_eip", "nat", az)], "public_ip": read(address("aws_eip", "nat", az), "public_ip")} for az in nat.get("public_subnet_key_by_nat_az", {})},
        "endpoint_ids": {"gateway": {s: ids[address("aws_vpc_endpoint", "gateway", s)] for s in inputs.get("gateway_endpoints", {})},
                         "interface": {s: ids[address("aws_vpc_endpoint", "interface", s)] for s in (interface or {}).get("services", [])}},
        "routing_mode": "per_az" if per_az else "legacy_shared", "interface_version": 1,
    }
    if scope == "root":
        expected_outputs["scope"] = dict(inputs["expected_scope"], environment="dev")
        expected_outputs = {"network": expected_outputs}
    outputs = plan.get("output_changes")
    require(isinstance(outputs, dict) and set(outputs) == set(expected_outputs), "output_inventory")
    for key, value in expected_outputs.items():
        change = outputs[key]
        require(isinstance(change, dict) and change.get("actions") == (["no-op"] if value is None else ["create"])
            and "before" in change and change["before"] is None
            and "after_unknown" in change and not unknown(change["after_unknown"])
            and change.get("after_sensitive") is False and change.get("after") == value, "output_contract:" + key)
    return len(resources)


def source_contract(sources=None):
    sources = sources or {str(p.relative_to(REPO)): p.read_text() for folder in (MODULE, ROOT) for p in folder.glob("*.tf")}
    def source(path):return re.sub(r"\s+", "", re.sub(r"(?m)#.*$", "", sources[path]))
    child = "infra/modules/vpc/"; root = "infra/services/dev/ca-central-1/network/"
    main=source(child+"main.tf");routing=source(child+"routing.tf");endpoint=source(child+"endpoints.tf")
    for expression in ('allocation_id=aws_eip.nat[each.key].id',
                       'subnet_id=aws_subnet.public[local.nat_subnet_keys[each.key]].id',
                       'route_table_id=aws_route_table.private_by_az[each.key].id',
                       'nat_gateway_id=aws_nat_gateway.this[each.value].id'):
        require(expression in routing, "actual_resource_reference:" + expression)
    require('route_table_id=local.per_az?aws_route_table.private_by_az[var.private_subnets[each.key].availability_zone].id:aws_route_table.private[0].id' in main, "actual_subnet_routing_reference")
    require('value=local.per_az?null:aws_route_table.private[0].id' in source(child+"outputs.tf"), "singular_output_reference")
    require('resource"aws_route_table""private"{count=local.per_az?0:1' in main and 'moved{from=aws_route_table.privateto=aws_route_table.private[0]}' in main, "shared_table_legacy_only")
    require('vpc_id=module.network.vpc_id' in source(root+"outputs.tf"), "root_output_reference")
    require('depends_on=[aws_internet_gateway.this,aws_route_table.public,aws_route_table_association.public]' in routing, "nat_public_readiness")
    require('depends_on=[aws_route.private_nat,aws_vpc_endpoint.gateway]' in main, "association_cutover_readiness")
    require('resource"aws_route_table""private_by_az"{' in routing and not re.search(r'\broute\s*(?:=|\{)', sources[child+"routing.tf"]), "no_inline_az_route_owner")
    require('route=[]' in main and 'gateway_id=aws_internet_gateway.this[0].id' in main, "legacy_route_ownership")
    require('route_table_ids=[forazinsort(tolist(each.value.private_route_table_azs)):aws_route_table.private_by_az[az].idifcontains(local.private_azs,az)]' in endpoint, "endpoint_association_owner")
    interface_block = re.search(r'resource"aws_vpc_endpoint""interface"\{.*?\n\}', re.sub(r"(?m)#.*$", "", sources[child+"endpoints.tf"]).replace(" ", ""), re.S)
    require(interface_block and 'policy' not in interface_block.group(0), "interface_endpoint_default_policy")
    for expression in ('resource"aws_vpc_endpoint""interface"{for_each=local.interface_services',
                       'subnet_ids=[forkeyinsort(tolist(var.interface_endpoints.subnet_keys)):aws_subnet.private[key].id]',
                       'security_group_ids=[aws_security_group.endpoints[0].id]', 'private_dns_enabled=true',
                       'security_group_id=aws_security_group.endpoints[0].idcidr_ipv4=var.vpc_cidrip_protocol="tcp"from_port=443to_port=443',
                       'interface_services=local.per_az&&var.interface_endpoints!=null?var.interface_endpoints.services:toset([])'):
        require(expression in endpoint, "interface_endpoint_reference:" + expression)
    require(not re.search(r'\b(ingress|egress)\s*\{', sources[child+"endpoints.tf"]), "endpoint_group_no_inline_rules")
    forbidden = ('aws_vpc_endpoint_route_table_association','aws_vpc_endpoint_subnet_association','aws_main_route_table_association','override_provider','skip_credentials_validation','skip_requesting_account_id','assume_role')
    require(not any(term in '\n'.join(sources.values()) for term in forbidden), "unapproved_owner_or_provider_bypass")
    require(source(root+"providers.tf").startswith('provider"aws"{region=local.regionallowed_account_ids=[var.aws_account_id]'), "root_account_region_guard")
    require('backend"local"{}' in source(root+"backend.tf"), "root_local_backend")
    require('region="ca-central-1"' in source(root+"main.tf") and 'environment="dev"' in source(root+"main.tf"), "root_scope")
    require('source="../../../../modules/vpc"' in source(root+"main.tf") and 'providers={aws=aws}' in source(root+"main.tf"), "root_child_provider")
    require('required_version="~>1.17.0"' in source(root+"versions.tf") and 'version="~>6.72.0"' in source(root+"versions.tf"), "root_version_contract")
    require(not any(re.search(r'(?m)^\s*(provider|data|terraform)\s+["{]', sources[child+n]) for n in ('main.tf','routing.tf','endpoints.tf','variables.tf','outputs.tf')), "child_provider_data_backend")
    require(hashlib.sha256((HERE/"vpc.tftest.hcl").read_bytes()).hexdigest() == ORIGINAL_SHA256, "original_16_tests_changed")
    lock=(ROOT/".terraform.lock.hcl").read_bytes()
    require(lock == (REPO/"infra/services/dev/ca-central-1/serverless-api/.terraform.lock.hcl").read_bytes(), "root_lock_identity")


def definitions(scope):
    manifest=parse((HERE/"network_cases.json").read_text())
    positives = manifest[scope+"_positive"].copy()
    negatives = manifest[scope+"_negative"].copy()
    if scope == "child":
        originals = manifest["original_positive"]
        positives = {("tests/extension.tftest.hcl",n):v for n,v in positives.items()} | {("tests/vpc.tftest.hcl",n):v for n,v in originals.items()}
        negatives = {("tests/extension.tftest.hcl",n):v for n,v in negatives.items()} | {("tests/vpc.tftest.hcl",n):v for n,v in manifest["original_negative"].items()}
    else:
        positives = {("tests/network.tftest.hcl",n):v for n,v in positives.items()}
        negatives = {("tests/network.tftest.hcl",n):v for n,v in negatives.items()}
        for inputs in positives.values():
            inputs["name_prefix"] = inputs["project"] + "-dev"
            inputs["expected_scope"] = dict(partition="aws",region="ca-central-1",account_id=inputs["aws_account_id"])
            inputs["private_routing"] = {"mode":"per_az", "nat":inputs["nat"]}
    return positives, negatives, manifest


def verify_capture(events, scope, exit_code=0):
    require(exit_code == 0, "terraform_exit_nonzero")
    positives, negatives, manifest = definitions(scope)
    expected = set(positives) | set(negatives)
    terminals={};plans={};diagnostics={};summaries=[];declarations=[];files={};versions=[]
    allowed={"version","test_abstract","test_file","test_run","test_plan","diagnostic","test_summary"}
    for event in events:
        require(isinstance(event,dict) and event.get("type") in allowed and not summaries, "event_shape_or_after_summary")
        kind=event["type"];key=(event.get("@testfile"),event.get("@testrun"))
        if kind=="version":
            require(event.get("terraform")=="1.17.0", "terraform_version")
            versions.append(event["terraform"])
        if kind=="test_abstract":declarations.append(event.get("test_abstract"))
        if kind in {"test_run","test_plan","diagnostic"}:
            require(key in expected, "unexpected_run_identity")
        if kind=="test_run":
            run=event.get("test_run",{});require(run.get("run")==key[1], "run_metadata_identity")
            if "status" in run:
                require(key not in terminals and run["status"]=="pass", "terminal_failure_duplicate_skip")
                terminals[key]=run
        if kind=="test_plan":
            require(key not in plans, "duplicate_plan")
            plans[key]=event.get("test_plan")
        if kind=="diagnostic":
            d=event.get("diagnostic",{})
            require(key in negatives and d.get("severity")=="error" and d.get("summary") in {"Invalid value for variable","Resource precondition failed","Resource postcondition failed"}, "unexpected_diagnostic")
            target=negatives[key]
            if target.startswith("var."):
                require(any(v.get("traversal","").startswith(target) for v in d.get("snippet",{}).get("values",[])), "diagnostic_variable")
            else:
                require(d.get("snippet",{}).get("context")=='resource "aws_vpc" "this"', "diagnostic_resource")
            diagnostics.setdefault(key,[]).append(d)
        if kind=="test_file" and "status" in event.get("test_file",{}):
            name=event["test_file"].get("path",event.get("@testfile"))
            require(name not in files and event["test_file"]["status"]=="pass", "file_terminal")
            files[name]=True
        if kind=="test_summary":summaries.append(event.get("test_summary"))
    require(versions==["1.17.0"], "version_event_coverage")
    require(len(declarations)==1 and isinstance(declarations[0],dict) and {(f,n) for f,names in declarations[0].items() for n in names}==expected
        and sum(map(len,declarations[0].values()))==len(expected), "declared_coverage")
    require(set(terminals)==set(plans)==expected, "incomplete_runs_or_plans")
    require(set(files)=={k[0] for k in expected}, "file_coverage")
    require(set(diagnostics)==set(negatives), "negative_diagnostic_coverage")
    require(summaries==[{"status":"pass","passed":len(expected),"failed":0,"errored":0,"skipped":0}], "summary_contract")
    counts={}
    for key,inputs in positives.items():counts[key[1]]=verify_plan(plans[key],inputs,scope)
    for key in negatives:
        rows=changes_of(plans[key],"module.network." if scope=="root" else "", allow_empty=True)
        allowed_rows=set(manifest["partial_resources"].get(key[1],[]))
        require(set(rows)==allowed_rows, "negative_partial_resource_shape:"+key[1])
        for addr,change in rows.items():
            if addr.startswith("aws_eip."):require(known(change,"domain")=="vpc", "partial_eip_domain")
        # Explicitly reviewed partial inventories are not complete topologies.
        # Missing/extra partial resource evidence is rejected as well.
        outputs=plans[key].get("output_changes",{})
        require(set(outputs)==set(manifest["partial_outputs"][key[1]]), "negative_partial_outputs:"+key[1])
    return {"status":"passed","evidence_type":"actual_mock_plan_verification","aws_api_calls":0,"native_tests":len(expected),
        "positive_plans":len(positives),"negative_cases":len(negatives),"resource_counts":counts}, plans


def rejected(operation, name):
    try:operation()
    except (ValueError,KeyError,TypeError,IndexError,json.JSONDecodeError):return name
    raise ValueError("unsafe_mutation_not_detected:"+name)


def policy_structure_mutations(plan, inputs, scope):
    """Poison BOTH captured policy and reviewed input identically.

    Matching values cannot establish AWS validity. Policy semantics and strict
    JSON parsing must reject each witness on an otherwise real captured plan.
    """
    actual = next(row for row in plan["resource_changes"] if row["type"] == "aws_vpc_endpoint")
    approved = parse(actual["change"]["after"]["policy"])
    role = "arn:aws:iam::" + inputs["expected_scope"]["account_id"] + ":role/test-network-reader"
    foreign = "arn:aws:iam::111111111111:role/test-network-reader"
    variants = []
    for name, principal in [("legacy_principal_object", {"AWS": role}), ("missing_principal", None)]:
        policy = copy.deepcopy(approved)
        if principal is None:
            policy["Statement"][0].pop("Principal")
        else:
            policy["Statement"][0]["Principal"] = principal
        variants.append((name, policy))
    for name, condition in [
        ("empty_condition", {}), ("null_condition", None),
        ("empty_arn_equals", {"ArnEquals": {}}),
        ("empty_role_string", {"ArnEquals": {"aws:PrincipalArn": ""}}),
        ("empty_role_list", {"ArnEquals": {"aws:PrincipalArn": []}}),
        ("null_role", {"ArnEquals": {"aws:PrincipalArn": None}}),
        ("foreign_role", {"ArnEquals": {"aws:PrincipalArn": foreign}}),
        ("mixed_accounts", {"ArnEquals": {"aws:PrincipalArn": [role, foreign]}}),
        ("wildcard_role", {"ArnEquals": {"aws:PrincipalArn": role + "*"}}),
        ("question_role", {"ArnEquals": {"aws:PrincipalArn": role + "?"}}),
        ("arnlike", {"ArnLike": {"aws:PrincipalArn": role}}),
        ("ifexists", {"ArnEqualsIfExists": {"aws:PrincipalArn": role}}),
        ("negated", {"ArnNotEquals": {"aws:PrincipalArn": role}}),
        ("set_operator", {"ForAllValues:ArnEquals": {"aws:PrincipalArn": role}}),
        ("unsupported_key", {"ArnEquals": {"aws:PrincipalAccount": "000000000000"}}),
        ("extra_key", {"ArnEquals": {"aws:PrincipalArn": role, "aws:PrincipalAccount": "000000000000"}}),
        ("extra_operator", {"ArnEquals": {"aws:PrincipalArn": role}, "Bool": {"aws:SecureTransport": "true"}}),
        ("session_arn", {"ArnEquals": {"aws:PrincipalArn": "arn:aws:sts::000000000000:assumed-role/test-network-reader/session"}}),
        ("user_arn", {"ArnEquals": {"aws:PrincipalArn": "arn:aws:iam::000000000000:user/test-reader"}}),
    ]:
        policy = copy.deepcopy(approved)
        policy["Statement"][0]["Condition"] = condition
        variants.append((name, policy))
    for name, field, value in [
        ("administrative_action", "Action", ["s3:*"]),
        ("write_action", "Action", ["s3:PutObject"]),
        ("world_resource", "Resource", ["*"]),
        ("wildcard_bucket", "Resource", ["arn:aws:s3:::*/*"]),
        ("wrong_resource_scope", "Resource", ["arn:aws:s3:::test-network-artifacts"]),
        ("not_action", "NotAction", ["s3:DeleteObject"]),
    ]:
        policy = copy.deepcopy(approved)
        policy["Statement"][0][field] = value
        variants.append((name, policy))
    policy = copy.deepcopy(approved)
    policy["Statement"][0].pop("Condition")
    variants.append(("unconditioned_wildcard", policy))
    policy = copy.deepcopy(approved)
    policy["Statement"].append(copy.deepcopy(policy["Statement"][0]))
    policy["Statement"][1].pop("Condition")
    variants.append(("second_unconditioned_statement", policy))
    variants.extend([
        ("empty_statements", {"Version": "2012-10-17", "Statement": []}),
        ("statement_object", {"Version": "2012-10-17", "Statement": approved["Statement"][0]}),
    ])
    payloads = [(name, json.dumps(policy)) for name, policy in variants]
    payloads.extend([("malformed_policy", "{broken"),
        ("duplicate_policy_key", '{"Version":"2012-10-17","Version":"2012-10-17","Statement":[]}')])
    witnesses = []
    for name, text in payloads:
        poisoned_plan, poisoned_input = copy.deepcopy(plan), copy.deepcopy(inputs)
        row = next(row for row in poisoned_plan["resource_changes"] if row["type"] == "aws_vpc_endpoint")
        row["change"]["after"]["policy"] = text
        poisoned_input["gateway_endpoints"]["s3"]["policy_json"] = text
        require(row["change"]["after"]["policy"] == poisoned_input["gateway_endpoints"]["s3"]["policy_json"], "matched_invalid_policy_witness")
        witnesses.append(rejected(lambda: verify_plan(poisoned_plan, poisoned_input, scope), "matched_invalid_policy:" + name))
    return len(witnesses)


def self_test(events, scope, plans):
    positives,_,_=definitions(scope)
    key=next(k for k in positives if k[1] in {"multi_az_nat","dev_network_s3"})
    plan=plans[key];inputs=positives[key];prefix="module.network." if scope=="root" else ""
    def mutate_resource(addr,field,value):
        p=copy.deepcopy(plan)
        row=next(r for r in p["resource_changes"] if r["address"]==prefix+addr)
        row["change"]["after"][field]=value
        return p
    a='ca-central-1a';b='ca-central-1b'
    # Root cases use the enforced tier keys; child cases keep generic keys.
    pk,uk=('private1','public1') if scope=='root' else ('app-a','public-a')
    mutations=[('public_ip_assignment',address('aws_subnet','private',pk),'map_public_ip_on_launch',True),
        ('private_public_association',address('aws_route_table_association','private',pk),'route_table_id','rtb-public'),
        ('wrong_association_subnet',address('aws_route_table_association','private',pk),'subnet_id','subnet-app-b'),
        ('wrong_nat_target',address('aws_route','private_nat',a),'nat_gateway_id','nat-b'),
        ('nat_target_as_igw',address('aws_route','private_nat',a),'gateway_id','igw-mock'),
        ('wrong_route_table',address('aws_route','private_nat',a),'route_table_id','rtb-b'),
        ('wrong_destination',address('aws_route','private_nat',a),'destination_cidr_block','10.40.0.0/16'),
        ('wrong_nat_public_subnet',address('aws_nat_gateway','this',a),'subnet_id','subnet-public-b'),
        ('wrong_nat_eip',address('aws_nat_gateway','this',a),'allocation_id','eipalloc-b'),
        ('regional_nat',address('aws_nat_gateway','this',a),'availability_mode','regional'),
        ('private_nat',address('aws_nat_gateway','this',a),'connectivity_type','private'),
        ('wrong_vpc',address('aws_subnet','private',pk),'vpc_id','vpc-other'),
        ('wrong_vpc_account','aws_vpc.this','arn','arn:aws:ec2:ca-central-1:111111111111:vpc/vpc-v2-mock'),
        ('az_inline_competing_route',address('aws_route_table','private_by_az',a),'route',[{'cidr_block':'0.0.0.0/0','gateway_id':'igw-mock'}]),
        ('public_wrong_target','aws_route_table.public[0]','route',[{'cidr_block':'0.0.0.0/0','gateway_id':'nat-a'}]),
        ('public_ip_public_subnet',address('aws_subnet','public',uk),'map_public_ip_on_launch',True)]
    semantic=[]
    for name,addr,field,value in mutations:
        semantic.append(rejected(lambda addr=addr,field=field,value=value:verify_plan(mutate_resource(addr,field,value),inputs,scope),name))
    if scope=='child':
        p=copy.deepcopy(plan);p['resource_changes'].append(copy.deepcopy(p['resource_changes'][0]));semantic.append(rejected(lambda:verify_plan(p,inputs,scope),'duplicate_resource'))
    endpoint_key=next(k for k in positives if k[1] in {'s3_selected_table','dev_network_s3'})
    endpoint_plan=plans[endpoint_key];endpoint_inputs=positives[endpoint_key]
    for field,value in [('service_name','com.amazonaws.us-east-1.s3'),('service_name','com.amazonaws.ca-central-1.dynamodb'),('vpc_endpoint_type','Interface'),('route_table_ids',['rtb-public']),('route_table_ids',['rtb-b']),('policy','{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*","Action":"*","Resource":"*"}]}')]:
        p=copy.deepcopy(endpoint_plan);row=next(r for r in p['resource_changes'] if r['type']=='aws_vpc_endpoint');row['change']['after'][field]=value
        semantic.append(rejected(lambda p=p:verify_plan(p,endpoint_inputs,scope),'endpoint_'+field+'_'+str(len(semantic))))
    # Actual existing NAT B is used above in child mode: swapping two valid
    # targets must fail, not merely an invented-ID check.
    for name,edit in [
        ('missing_igw', lambda p: p['resource_changes'].remove(next(r for r in p['resource_changes'] if r['type']=='aws_internet_gateway'))),
        ('unknown_nat_target', lambda p: next(r for r in p['resource_changes'] if r['type']=='aws_route')['change']['after_unknown'].update(nat_gateway_id=True)),
        ('renamed_address', lambda p: p['resource_changes'][0].update(address=prefix+'aws_vpc.renamed', type='aws_vpc', name='renamed')),
        ('extra_resource', lambda p: p['resource_changes'].append(dict(copy.deepcopy(p['resource_changes'][0]), address=prefix+'aws_eip.unapproved', type='aws_eip', name='unapproved'))),
    ]:
        p=copy.deepcopy(plan);edit(p)
        semantic.append(rejected(lambda p=p:verify_plan(p,inputs,scope),name))
    # F8: per_az must not create the unassociated shared table; legacy keeps it route-free.
    p=copy.deepcopy(plan);row=copy.deepcopy(next(r for r in p['resource_changes'] if r['type']=='aws_route_table' and r['name']=='private_by_az'))
    row.update(address=prefix+'aws_route_table.private[0]',name='private',index=0);row['change']['after']['id']='rtb-shared'
    p['resource_changes'].append(row)
    semantic.append(rejected(lambda p=p:verify_plan(p,inputs,scope),'shared_private_table_in_per_az'))
    if scope=='child':
        legacy_key=('tests/extension.tftest.hcl','legacy_private_unchanged')
        p=copy.deepcopy(plans[legacy_key]);row=next(r for r in p['resource_changes'] if r['address']=='aws_route_table.private[0]')
        row['change']['after']['route']=[{'cidr_block':'0.0.0.0/0','gateway_id':'igw-mock'}]
        semantic.append(rejected(lambda p=p:verify_plan(p,positives[legacy_key],scope),'legacy_inline_egress'))
    # F16: interface endpoints stay private, regional, VPC-only and reviewed.
    iface_key=next((k for k in positives if positives[k].get('interface_endpoints')),None)
    require(iface_key is not None,'interface_endpoint_fixture')
    iplan=plans[iface_key];iinputs=positives[iface_key]
    svc=sorted(iinputs['interface_endpoints']['services'])[0]
    ep=prefix+address('aws_vpc_endpoint','interface',svc);rule=prefix+'aws_vpc_security_group_ingress_rule.endpoints_https[0]'
    public_subnet=next(r for r in iplan['resource_changes'] if r['type']=='aws_subnet' and r['name']=='public')['change']['after']['id']
    for name,addr,field,value in [('interface_wrong_region',ep,'service_name','com.amazonaws.us-east-1.'+svc),
            ('interface_private_dns_off',ep,'private_dns_enabled',False),('interface_public_subnet',ep,'subnet_ids',[public_subnet]),
            ('interface_no_security_group',ep,'security_group_ids',[]),('endpoint_rule_world',rule,'cidr_ipv4','0.0.0.0/0'),
            ('endpoint_rule_ssh',rule,'from_port',22),('endpoint_rule_peer_group',rule,'referenced_security_group_id','sg-other')]:
        p=copy.deepcopy(iplan);row=next(r for r in p['resource_changes'] if r['address']==addr);row['change']['after'][field]=value
        semantic.append(rejected(lambda p=p:verify_plan(p,iinputs,scope),name))
    p=copy.deepcopy(iplan);row=copy.deepcopy(next(r for r in p['resource_changes'] if r['address']==ep))
    row.update(address=prefix+address('aws_vpc_endpoint','interface','s3'),index='s3');row['change']['after']['id']='vpce-extra'
    p['resource_changes'].append(row)
    semantic.append(rejected(lambda p=p:verify_plan(p,iinputs,scope),'interface_unreviewed_service'))
    if scope=='child':
        legacy_key=('tests/extension.tftest.hcl','legacy_private_unchanged')
        p=copy.deepcopy(plans[legacy_key])
        p['resource_changes'].append(copy.deepcopy(next(r for r in plan['resource_changes'] if r['type']=='aws_eip')))
        semantic.append(rejected(lambda:verify_plan(p,positives[legacy_key],scope),'automatic_legacy_nat_eip'))
    output_plan=copy.deepcopy(plan)
    target=output_plan['output_changes']['network']['after'] if scope=='root' else None
    if target is not None:target['private_route_table_id']='rtb-legacy'
    else:output_plan['output_changes']['private_route_table_id']['after']='rtb-legacy'
    semantic.append(rejected(lambda:verify_plan(output_plan,inputs,scope),'singular_output_contract'))
    for name,change in [('missing_resource',lambda p:p['resource_changes'].pop()),('wrong_provider',lambda p:p['resource_changes'][0].update(provider_name='registry.terraform.io/unapproved/aws')),('data_resource_mode',lambda p:p['resource_changes'][0].update(mode='data')),('replacement',lambda p:p['resource_changes'][0]['change'].update(actions=['delete','create'])),('unknown_identity',lambda p:p['resource_changes'][0]['change']['after_unknown'].update(id=True)),('missing_output',lambda p:p['output_changes'].pop(next(iter(p['output_changes']))))]:
        p=copy.deepcopy(plan);change(p);semantic.append(rejected(lambda p=p:verify_plan(p,inputs,scope),name))
    faults=[]
    for kind in ['version','test_plan','test_summary','test_abstract','test_run','test_file','diagnostic']:
        p=copy.deepcopy(events);idx=next(i for i,e in enumerate(p) if e['type']==kind and (kind not in {'test_run','test_file'} or 'status' in e[kind]));p.pop(idx)
        faults.append(rejected(lambda p=p:verify_capture(p,scope),'missing_'+kind))
    for kind in ['version','test_plan','test_summary','test_abstract','test_run','test_file']:
        p=copy.deepcopy(events);idx=next(i for i,e in enumerate(p) if e['type']==kind and (kind not in {'test_run','test_file'} or 'status' in e[kind]));p.insert(idx,copy.deepcopy(p[idx]))
        faults.append(rejected(lambda p=p:verify_capture(p,scope),'duplicate_'+kind))
    for status in ['fail','error','skip']:
        p=copy.deepcopy(events);row=next(e for e in p if e['type']=='test_run' and 'status' in e['test_run']);row['test_run']['status']=status
        faults.append(rejected(lambda p=p:verify_capture(p,scope),'terminal_'+status))
    p=copy.deepcopy(events);next(e for e in p if e['type']=='version')['terraform']='1.13.5'
    faults.append(rejected(lambda:verify_capture(p,scope),'wrong_terraform_version'))
    faults.append(rejected(lambda:verify_capture(events,scope,1),'terraform_nonzero'))
    for text in ['{broken','{"type":"test_plan","type":"test_summary"}','{"number":NaN}','{"number":Infinity}']:
        faults.append(rejected(lambda text=text:parse(text),'malformed_'+str(len(faults))))
    sources={str(p.relative_to(REPO)):p.read_text() for folder in (MODULE,ROOT) for p in folder.glob('*.tf')}
    source_mutations=[]
    replacements=[('infra/modules/vpc/routing.tf','aws_internet_gateway.this,',''),
        ('infra/modules/vpc/endpoints.tf','cidr_ipv4         = var.vpc_cidr','cidr_ipv4         = "0.0.0.0/0"'),
        ('infra/modules/vpc/endpoints.tf','private_dns_enabled = true','private_dns_enabled = false'),('infra/modules/vpc/main.tf','depends_on = [aws_route.private_nat, aws_vpc_endpoint.gateway]','depends_on = []'),('infra/services/dev/ca-central-1/network/providers.tf','allowed_account_ids = [var.aws_account_id]','allowed_account_ids = []'),('infra/services/dev/ca-central-1/network/backend.tf','"local"','"s3"')]
    for path, expression, replacement in [
        ('infra/modules/vpc/routing.tf', 'allocation_id', 'allocation_id = "eipalloc-a"'),
        ('infra/modules/vpc/routing.tf', 'nat_gateway_id', 'nat_gateway_id = "nat-a"'),
        ('infra/modules/vpc/main.tf', 'route_table_id', 'route_table_id = "rtb-a"'),
        ('infra/services/dev/ca-central-1/network/outputs.tf', 'vpc_id', 'vpc_id = "vpc-v2-mock"'),
    ]:
        lines = [line.strip() for line in sources[path].splitlines() if line.strip().startswith(expression + ' ')]
        if path.endswith('main.tf'):
            lines = [line for line in lines if 'local.per_az' in line]
        require(len(lines) == 1, 'resource_reference_mutation_witness')
        replacements.append((path, lines[0], replacement))
    for path,old,new in replacements:
        require(old in sources[path],'mutation_source_witness');modified=sources.copy();modified[path]=modified[path].replace(old,new,1)
        source_mutations.append(rejected(lambda modified=modified:source_contract(modified),path))
    return {'semantic_mutations':len(semantic),'capture_failure_injections':len(faults),'source_dependency_mutations':len(source_mutations),
        'policy_structure_mutations':policy_structure_mutations(endpoint_plan, endpoint_inputs, scope)}


def read_events(stream):
    for line in stream:
        require(line.strip(), 'blank_or_incomplete_event')
        event=parse(line);require(isinstance(event,dict),'event_not_object')
        if event.get('type')=='test_plan':event.get('test_plan',{}).pop('provider_schemas',None)
        yield event


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact',action='store_true')
    parser.add_argument('--scope',choices=['child','root'])
    parser.add_argument('--test-events',type=Path)
    parser.add_argument('--terraform-exit-code',type=int,default=0)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    try:
        if args.compact:
            for event in read_events(sys.stdin):print(json.dumps(event,separators=(',',':')))
            return 0
        require(args.scope and args.test_events,'scope_and_events_required')
        source_contract()
        with args.test_events.open() as stream:events=list(read_events(stream))
        report,plans=verify_capture(events,args.scope,args.terraform_exit_code)
        if args.self_test:report.update(self_test(events,args.scope,plans))
        print(json.dumps(report,indent=2))
    except (ValueError,KeyError,TypeError,IndexError,OSError) as e:
        print('Network verification failed: '+str(e),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
