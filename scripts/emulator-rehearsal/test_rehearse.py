#!/usr/bin/env python3
"""Offline negative and mutation tests for the Step 2 rehearsal gates.

Synthetic plan and refresh documents only: no emulator, Terraform, AWS call or
network access. Each mutation must be rejected with its specific gate label.
"""
import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rehearse  # noqa: E402
from gates import Blocked  # noqa: E402

RUN_ID = '20261118000000-1'
M = rehearse.M


def harness(scenario='full'):
    r = rehearse.Rehearsal.__new__(rehearse.Rehearsal)
    r.run_id = RUN_ID
    r.scenario = scenario
    r.expected = rehearse.expected_for(scenario)
    r.controls = {str(i): 'NOT_TESTED' for i in range(1, 15)}
    r.state_ids = {a: 'id-%d' % i for i, a in enumerate(sorted(r.expected))}
    return r


def tags(phase):
    return {'VerificationRun': RUN_ID, 'Phase': phase, 'project': rehearse.PROJECT, 'env': 'dev',
            'managed': 'terraform', 'Name': 'step2-dev-x', 'service': 'x'}


def plan(r, action, phase='create'):
    changes = []
    for address, kind in r.expected.items():
        taggable = kind not in rehearse.UNTAGGED
        body = {'id': r.state_ids[address], 'cidr_block': '10.40.0.0/16'}
        before = dict(body, **({'tags_all': tags('create')} if taggable else {}))
        after = dict(body, **({'tags_all': tags(phase)} if taggable else {}))
        acts = {'create': ['create'], 'delete': ['delete'], 'no-op': ['no-op'],
                'update': ['no-op'] if not taggable else ['update']}[action]
        changes.append({'address': address, 'mode': 'managed', 'type': kind, 'module_address': 'module.network',
                        'provider_name': 'registry.terraform.io/hashicorp/aws',
                        'change': {'actions': acts, 'before': None if action == 'create' else before,
                                   'after': None if action == 'delete' else after}})
    endpoint = {'constant_value': rehearse.ENDPOINT}
    return {'terraform_version': '1.17.0', 'resource_changes': changes,
            'configuration': {'provider_config': {'aws': {'expressions': {
                'allowed_account_ids': {'constant_value': ['000000000000']},
                'endpoints': [{'ec2': dict(endpoint), 'sts': dict(endpoint)}]}}}}}


def change(doc, address):
    return next(c for c in doc['resource_changes'] if c['address'] == address)


EIP = M + 'aws_eip.nat["ca-central-1a"]'
RTB = M + 'aws_route_table.private_by_az["ca-central-1a"]'
NAT = M + 'aws_nat_gateway.this["ca-central-1a"]'
VPC = M + 'aws_vpc.this'


def refresh(r):
    return {'output_changes': {'network': {'actions': ['no-op']}}, 'resource_drift': [
        {'address': EIP, 'change': {'actions': ['update'],
                                    'before': {'network_interface': '', 'private_ip': '', 'association_id': '', 'private_dns': ''},
                                    'after': {'network_interface': 'eni-1', 'private_ip': '10.40.10.4',
                                              'association_id': 'eipassoc-1', 'private_dns': 'ip-10-40-10-4'}}},
        {'address': RTB, 'change': {'actions': ['update'], 'before': {'route': []},
                                    'after': {'route': [{'cidr_block': '0.0.0.0/0', 'nat_gateway_id': r.state_ids[NAT]}]}}}]}


def nat(r):
    return {'NatGatewayId': r.state_ids[NAT], 'NatGatewayAddresses': [
        {'AllocationId': r.state_ids[EIP], 'NetworkInterfaceId': 'eni-1', 'PrivateIp': '10.40.10.4'}]}


class Quiet(unittest.TestCase):
    def run(self, result=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return super().run(result)

    def rejects(self, label, func, *args):
        with self.assertRaises(Blocked) as caught:
            func(*args)
        self.assertEqual(str(caught.exception), label)


class InventoryTests(Quiet):
    def test_scenarios(self):
        self.assertEqual(len(rehearse.expected_for('full')), 26)
        reduced = rehearse.expected_for('no-interface-endpoints')
        self.assertEqual(len(reduced), 16)
        self.assertFalse(set(reduced.values()) & rehearse.ENDPOINT_TYPES)
        self.rejects('scenario', rehearse.expected_for, 'everything')

    def test_normal_ignores_order_only(self):
        self.assertEqual(rehearse.normal({'a': [{'k': 2}, {'k': 1}]}), rehearse.normal({'a': [{'k': 1}, {'k': 2}]}))
        self.assertNotEqual(rehearse.normal({'a': [1]}), rehearse.normal({'a': [2]}))

    def test_redaction(self):
        rehearse.REDACT.append('SECRETVALUE123')
        try:
            self.assertNotIn('SECRETVALUE123', rehearse.safe('error near SECRETVALUE123'))
        finally:
            rehearse.REDACT.remove('SECRETVALUE123')


class PlanTests(Quiet):
    def test_valid_plans_pass(self):
        for scenario in ('full', 'no-interface-endpoints'):
            r = harness(scenario)
            for action, phase in [('create', 'create'), ('update', 'updated'), ('no-op', 'updated'), ('delete', 'updated')]:
                r.inspect(plan(r, action, phase), action, phase)
        self.assertEqual(r.controls['11'], 'PASS')

    def test_rejections(self):
        r = harness()
        cases = []

        def case(label, action, phase, mutate):
            doc = plan(r, action, phase)
            mutate(doc)
            cases.append((label, doc, action, phase))

        case('plan-version', 'create', 'create', lambda d: d.update(terraform_version='1.16.0'))
        case('plan-errored-or-deferred', 'create', 'create', lambda d: d.update(errored=True))
        case('plan-drift', 'update', 'updated', lambda d: d.update(resource_drift=[{'address': VPC}]))
        case('provider-endpoint-guard', 'create', 'create', lambda d: d['configuration']['provider_config']['aws']['expressions']
             ['endpoints'][0]['ec2'].update(constant_value='https://ec2.ca-central-1.amazonaws.com'))
        case('provider-endpoint-guard', 'create', 'create', lambda d: d['configuration']['provider_config']['aws']['expressions']
             ['endpoints'][0].update(s3={'constant_value': rehearse.ENDPOINT}))
        case('provider-endpoint-guard', 'create', 'create', lambda d: d['configuration']['provider_config']['aws']['expressions']
             ['allowed_account_ids'].update(constant_value=['123456789012']))
        case('plan-resource-inventory', 'create', 'create', lambda d: d['resource_changes'].append(
            dict(copy.deepcopy(d['resource_changes'][0]), address=M + 'aws_instance.extra')))
        case('plan-resource-inventory', 'create', 'create', lambda d: d['resource_changes'].pop())
        case('plan-resource-identity', 'create', 'create', lambda d: change(d, VPC).update(type='aws_subnet'))
        case('plan-resource-identity', 'create', 'create', lambda d: change(d, VPC).update(mode='data'))
        case('plan-resource-identity', 'create', 'create', lambda d: change(d, VPC).update(provider_name='registry.example/aws'))
        case('plan-actions-create', 'create', 'create', lambda d: change(d, VPC)['change'].update(actions=['delete', 'create']))
        case('plan-tags', 'create', 'create', lambda d: change(d, VPC)['change']['after']['tags_all'].pop('VerificationRun'))
        case('plan-tags', 'create', 'create', lambda d: change(d, VPC)['change']['after'].pop('tags_all'))
        case('plan-tags', 'update', 'updated', lambda d: change(d, VPC)['change']['after']['tags_all'].update(Phase='create'))
        case('plan-actions-update', 'update', 'updated', lambda d: change(d, VPC)['change'].update(actions=['delete', 'create']))
        case('plan-actions-update', 'update', 'updated', lambda d: change(d, RTB.replace('aws_route_table.private_by_az', 'aws_route.private_nat'))
             ['change'].update(actions=['update']))
        case('update-changes-only-tags', 'update', 'updated', lambda d: change(d, VPC)['change']['after'].update(cidr_block='10.0.0.0/8'))
        case('plan-actions-no-op', 'no-op', 'updated', lambda d: change(d, VPC)['change'].update(actions=['update']))
        case('plan-actions-delete', 'delete', 'updated', lambda d: change(d, VPC)['change'].update(actions=['no-op']))
        case('destroy-target-identity', 'delete', 'updated', lambda d: change(d, VPC)['change']['before'].update(id='vpc-preexisting'))
        for label, doc, action, phase in cases:
            with self.subTest(label=label):
                self.rejects(label, r.inspect, doc, action, phase)
        self.assertGreaterEqual(len(cases), 20)


class RefreshTests(Quiet):
    def test_reviewed_convergence_passes(self):
        r = harness()
        doc = refresh(r)
        r.check_refresh(doc, r.drift_summary(doc), nat(r))
        empty = {'resource_drift': []}
        r.check_refresh(empty, [], nat(r))

    def test_rejections(self):
        r = harness()
        cases = [
            ('refresh-output-changes', lambda d, n: d['output_changes']['network'].update(actions=['update'])),
            ('refresh-nat-identity', lambda d, n: n.update(NatGatewayId='nat-other')),
            ('nat-eip-association', lambda d, n: n.update(NatGatewayAddresses=[])),
            ('refresh-drift-unexpected', lambda d, n: d['resource_drift'].append(
                {'address': VPC, 'change': {'actions': ['update'], 'before': {'cidr_block': 'a'}, 'after': {'cidr_block': 'b'}}})),
            ('refresh-drift-unexpected', lambda d, n: d['resource_drift'][0]['change']['after'].update(allocation_id='eipalloc-x')),
            ('refresh-drift-unexpected', lambda d, n: d['resource_drift'][0]['change'].update(actions=['delete', 'create'])),
            ('refresh-eip-values', lambda d, n: d['resource_drift'][0]['change']['after'].update(network_interface='eni-other')),
            ('refresh-eip-values', lambda d, n: d['resource_drift'][0]['change']['after'].update(private_ip='10.40.10.99')),
            ('refresh-route-values', lambda d, n: d['resource_drift'][1]['change']['after']['route'][0].update(nat_gateway_id='nat-other')),
            ('refresh-route-values', lambda d, n: d['resource_drift'][1]['change']['after']['route'].append(
                {'cidr_block': '10.0.0.0/8', 'nat_gateway_id': r.state_ids[NAT]})),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                doc, nat_row = refresh(r), nat(r)
                mutate(doc, nat_row)
                self.rejects(label, r.check_refresh, doc, r.drift_summary(doc), nat_row)


if __name__ == '__main__':
    unittest.main(verbosity=1)
