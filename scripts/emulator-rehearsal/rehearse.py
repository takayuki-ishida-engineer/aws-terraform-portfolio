"""Step 2 rehearsal of the real network root (vpc module) in the official AWS Emulator.

Owner-authorized local runs only, never CI. Runs only inside a fresh network +
mount namespace, as uid 1000 with no capabilities and no_new_privs (launch.sh).
Private material (generated credentials, CA, State, plans, logs) lives only on
the namespace-private tmpfs WORK and is removed before exit. stdout carries only
non-secret gate rows. The disposable root is a copy of the committed network root
and vpc module from the tested SHA; the operational root and its State are never
touched. See README.md for the controls and docs/step2-emulator-rehearsals.md for
recorded evidence.
"""
import configparser, errno, hashlib, json, os, re, shutil, signal, socket, ssl, subprocess, sys, time
import urllib.error, urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))
# In the repository the shared gates live in ../emulator-verification; launch.sh copies them next to this file.
sys.path.insert(1, str(HARNESS.parent / 'emulator-verification'))
from gates import Blocked, require, network_gate, unreachable_gate, tls_gate, identity_gate  # noqa: E402
from runtime_contracts import (ENDPOINT, strict_json, startup_record, generated_file, cli_error_code,  # noqa: E402
                               signed_sts_request, signed_sts_identity, sts_rejection, unsigned_sts_rejected)

TOOLS = Path('/opt/step2-tools')
WORK = Path('/opt/step2-work')
EVIDENCE = Path('/opt/step2-evidence')
HOME = WORK / 'home'
ROOT = WORK / 'root' / 'infra/services/dev/ca-central-1/network'
PROJECT = 'step2'
SERVICES = ['ec2', 'ec2messages', 'ecr.api', 'ecr.dkr', 'logs', 'ssm', 'ssmmessages', 'sts']
M = 'module.network.'
EXPECTED = {
    M + 'aws_vpc.this': 'aws_vpc',
    M + 'aws_subnet.private["private1"]': 'aws_subnet', M + 'aws_subnet.private["private2"]': 'aws_subnet',
    M + 'aws_subnet.public["public1"]': 'aws_subnet', M + 'aws_subnet.public["public2"]': 'aws_subnet',
    M + 'aws_internet_gateway.this[0]': 'aws_internet_gateway',
    M + 'aws_route_table.public[0]': 'aws_route_table',
    M + 'aws_route_table.private_by_az["ca-central-1a"]': 'aws_route_table',
    M + 'aws_route_table.private_by_az["ca-central-1b"]': 'aws_route_table',
    M + 'aws_route_table_association.private["private1"]': 'aws_route_table_association',
    M + 'aws_route_table_association.private["private2"]': 'aws_route_table_association',
    M + 'aws_route_table_association.public["public1"]': 'aws_route_table_association',
    M + 'aws_route_table_association.public["public2"]': 'aws_route_table_association',
    M + 'aws_eip.nat["ca-central-1a"]': 'aws_eip',
    M + 'aws_nat_gateway.this["ca-central-1a"]': 'aws_nat_gateway',
    M + 'aws_route.private_nat["ca-central-1a"]': 'aws_route',
    M + 'aws_security_group.endpoints[0]': 'aws_security_group',
    M + 'aws_vpc_security_group_ingress_rule.endpoints_https[0]': 'aws_vpc_security_group_ingress_rule',
    **{M + f'aws_vpc_endpoint.interface["{s}"]': 'aws_vpc_endpoint' for s in SERVICES},
}
ENDPOINT_TYPES = {'aws_security_group', 'aws_vpc_security_group_ingress_rule', 'aws_vpc_endpoint'}
UNTAGGED = {'aws_route_table_association', 'aws_route'}
OPERATIONS = ['plan', 'create', 'api_create', 'read', 'update_plan', 'update', 'api_update', 'no_op',
              'destroy_plan', 'destroy', 'state_empty', 'api_absence', 'baseline_preserved']
REDACT = []


def emit(gate, status, **extra):
    print(json.dumps({'gate': gate, 'status': status, **extra}), flush=True)


def safe(text):
    for value in REDACT:
        text = text.replace(value, '[redacted]')
    return text


def error_excerpt(text):
    keep = [l.strip() for l in text.splitlines()
            if re.search(r'Error|error|StatusCode|api error|Unsupported|not implemented', l)]
    return [safe(l)[:300] for l in keep[:12]]


def expected_for(scenario):
    """Exact reviewed resource inventory of the network root for a scenario."""
    if scenario == 'no-interface-endpoints':
        return {a: k for a, k in EXPECTED.items() if k not in ENDPOINT_TYPES}
    require(scenario == 'full', 'scenario')
    return dict(EXPECTED)


def normal(value):
    """Order-insensitive canonical form for comparing API records."""
    if isinstance(value, dict):
        return {k: normal(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return sorted((normal(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


class Failure(Exception):
    def __init__(self, label, api=None, unsupported=False, detail=None):
        super().__init__(label)
        self.label, self.api, self.unsupported, self.detail = label, api, unsupported, detail or []


class Rehearsal:
    def __init__(self):
        self.prepared = json.loads((TOOLS / 'prepared.json').read_text())
        self.meta = json.loads((TOOLS / 'run.json').read_text())
        self.run_id = self.meta['run_id']
        self.scenario = self.meta['scenario']
        require(self.scenario in ('full', 'no-interface-endpoints'), 'scenario')
        self.expected = expected_for(self.scenario)
        self.probe = None
        self.env = {'PATH': str(TOOLS / 'bin') + ':/usr/bin:/bin', 'HOME': str(HOME), 'LANG': 'C.UTF-8',
                    'CHECKPOINT_DISABLE': '1', 'TF_IN_AUTOMATION': 'true', 'TF_INPUT': 'false',
                    'AWS_CONFIG_FILE': '/dev/null', 'AWS_EC2_METADATA_DISABLED': 'true',
                    'AWS_REGION': 'ca-central-1', 'AWS_DEFAULT_REGION': 'ca-central-1', 'AWS_PAGER': '',
                    'AWS_MAX_ATTEMPTS': '2', 'AWS_RETRY_MODE': 'standard', 'EMULATOR_TELEMETRY': 'off'}
        self.controls = {str(i): 'NOT_TESTED' for i in range(1, 15)}
        self.ops = dict.fromkeys(OPERATIONS, 'NOT_TESTED')
        self.emulator = None
        self.creation_attempted = False
        self.baseline = None
        self.state_ids = {}
        self.plans = {}
        self.current = 'setup'
        self.notes = []
        self.unsupported = []

    # ---------- helpers ----------
    def ctl(self, number):
        self.controls[number] = 'PASS'
        emit('control-' + number, 'PASS')

    def op(self, name, status='PASS', **extra):
        self.ops[name] = status
        emit(name, status, **extra)

    def run(self, args, ok=(0,), timeout=900, env=None):
        if self.emulator is not None and self.emulator.poll() is not None:
            raise Failure('emulator-process-exit')
        try:
            p = subprocess.run(args, cwd=ROOT if ROOT.exists() else WORK, env=env or self.env,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise Failure('command-timeout:' + Path(args[0]).name) from None
        with (WORK / 'private.log').open('a') as log:
            log.write('$ ' + ' '.join(args[:4]) + '\n' + p.stdout[-20000:] + p.stderr[-20000:] + '\n')
        if p.returncode not in ok:
            text = p.stdout + p.stderr
            api = re.search(r'operation error [A-Za-z0-9 ]+: ([A-Za-z0-9]+)', text)
            api = api.group(1) if api else None
            unsupported = bool(re.search(r'StatusCode: ?501|HTTP ?501|\(501\)', text))
            raise Failure('command-failed:' + Path(args[0]).name, api, unsupported, error_excerpt(text))
        return p

    def tf(self, *args, ok=(0,)):
        return self.run([str(TOOLS / 'bin/terraform'), *args], ok=ok)

    def aws(self, service, operation, *args, ok=(0,)):
        p = self.run([str(TOOLS / 'bin/aws'), '--no-cli-pager', '--endpoint-url', ENDPOINT, '--ca-bundle',
                      self.env['AWS_CA_BUNDLE'], '--region', 'ca-central-1', '--cli-connect-timeout', '3',
                      '--cli-read-timeout', '20', service, operation, *args, '--output', 'json'], ok=ok, timeout=120)
        return p if ok != (0,) else (strict_json(p.stdout) if p.stdout.strip() else {})

    def http(self, request, context, timeout=5):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                raise Failure('unexpected-redirect')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                             urllib.request.HTTPSHandler(context=context), NoRedirect())
        return opener.open(request, timeout=timeout)

    # ---------- isolation ----------
    def isolation(self):
        self.current = 'isolation'
        require(os.getuid() == 1000 and os.geteuid() == 1000, 'unprivileged-user')
        status = Path('/proc/self/status').read_text()
        for key, value in [('CapEff', '0000000000000000'), ('CapPrm', '0000000000000000'),
                           ('CapBnd', '0000000000000000'), ('NoNewPrivs', '1')]:
            require(re.search(r'^' + key + r':\s*' + value + r'$', status, re.M), 'process-privileges')
        require(not any(k.startswith(('AWS_', 'TF_')) or 'PROXY' in k.upper() or k in ('GITHUB_TOKEN', 'GH_TOKEN')
                        for k in os.environ), 'no-host-credentials-or-proxy')
        require(not Path('/var/run/docker.sock').exists(), 'no-docker-socket')
        require(os.path.ismount(WORK) and not any(WORK.iterdir()), 'fresh-private-tmpfs')
        HOME.mkdir(mode=0o700)
        links = strict_json(self.run(['/usr/sbin/ip', '-j', 'link']).stdout)
        routes = (strict_json(self.run(['/usr/sbin/ip', '-j', '-4', 'route', 'show', 'table', 'all']).stdout)
                  + strict_json(self.run(['/usr/sbin/ip', '-j', '-6', 'route', 'show', 'table', 'all']).stdout))
        network_gate(self.prepared['host_netns'], os.readlink('/proc/self/ns/net'), links, routes)
        self.ctl('6')
        results = {}
        for service, ips in self.prepared['probes'].items():
            results[service] = []
            for address in ips:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(2)
                    try:
                        results[service].append(sock.connect_ex((address, 443)))
                    except (TimeoutError, socket.timeout):
                        results[service].append(errno.ETIMEDOUT)
        unreachable_gate(results)
        emit('external-probe-errno', 'PASS', results={k: [errno.errorcode[c] for c in v] for k, v in results.items()})
        self.ctl('7')
        lock = self.prepared['versions']
        require(re.search(r'\b' + re.escape(lock['emulator']['version']) + r'\b',
                          self.run([str(TOOLS / 'bin/aws-emulator'), '-v']).stdout), 'emulator-version')
        require(lock['awscli']['version'] in self.run([str(TOOLS / 'bin/aws'), '--version']).stdout, 'awscli-version')
        require(strict_json(self.tf('version', '-json').stdout)['terraform_version'] == lock['terraform']['version'],
                'terraform-version')
        self.ctl('1')

    def startup(self):
        self.current = 'startup'
        log, err = WORK / 'emulator.log', WORK / 'emulator.err'
        with log.open('w') as out, err.open('w') as stderr:
            self.emulator = subprocess.Popen([str(TOOLS / 'bin/aws-emulator'), '--bind', '127.0.0.1', '--port', '9297',
                                              '--auth', 'on', '--telemetry', 'off', '--idle-timeout', '1800'],
                                             env=self.env, stdout=out, stderr=stderr)
        deadline, record = time.monotonic() + 90, None
        while time.monotonic() < deadline and record is None:
            require(self.emulator.poll() is None, 'startup-process-exit')
            rows = [r for r in log.read_bytes().split(b'\n')[:-1] if r.strip()]
            found = [x for x in (startup_record(strict_json(r), HOME) for r in rows) if x is not None]
            require(len(found) <= 1, 'startup-log-invalid')
            record = found[0] if found else None
            time.sleep(0.5)
        require(record is not None, 'startup-timeout')
        expected = HOME / '.aws/emulator/9297'
        ca = generated_file(Path(record['ca_file']), expected / 'ca.pem', os.getuid())
        for key, name in [('config_file', 'config'), ('java_truststore_file', 'truststore.p12')]:
            generated_file(Path(record[key]), expected / name, os.getuid())
        credentials = generated_file(expected / 'emulator_credentials', expected / 'emulator_credentials', os.getuid())
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(credentials)
        require(not parser.defaults() and parser.sections() == ['default']
                and all(parser['default'].get(k) for k in ['aws_access_key_id', 'aws_secret_access_key']),
                'generated-credentials')
        self.credentials = dict(parser['default'])
        REDACT.extend([self.credentials['aws_access_key_id'], self.credentials['aws_secret_access_key']])
        self.env.update(AWS_SHARED_CREDENTIALS_FILE=str(credentials), AWS_CA_BUNDLE=str(ca), AWS_PROFILE='default')
        context = ssl.create_default_context(cafile=str(ca))
        tls_gate(context.verify_mode, context.check_hostname)
        healthy = False
        while time.monotonic() < deadline and not healthy:
            require(self.emulator.poll() is None, 'startup-process-exit')
            try:
                with self.http(ENDPOINT + '/__admin/health', context) as response:
                    healthy = response.status == 200 and response.read(64) == b'ok'
            except urllib.error.URLError as error:
                require(not isinstance(error.reason, ssl.SSLCertVerificationError), 'tls-validation')
                time.sleep(0.5)
        require(healthy, 'health-not-ready')
        rejected = False
        try:
            with self.http(ENDPOINT + '/__admin/health', ssl.create_default_context()):
                pass
        except urllib.error.URLError as error:
            rejected = isinstance(error.reason, ssl.SSLCertVerificationError)
        require(rejected, 'system-trust-must-reject-private-ca')
        self.ctl('2'), self.ctl('4'), self.ctl('5')

    def authenticate(self):
        self.current = 'authentication'
        identity_gate(self.aws('sts', 'get-caller-identity'))
        self.ctl('8')
        base = [str(TOOLS / 'bin/aws'), '--no-cli-pager', '--endpoint-url', ENDPOINT, '--ca-bundle',
                self.env['AWS_CA_BUNDLE'], '--region', 'ca-central-1', 'sts', 'get-caller-identity', '--output', 'json']
        context = ssl.create_default_context(cafile=self.env['AWS_CA_BUNDLE'])
        tls_gate(context.verify_mode, context.check_hostname)
        for field, code in [('aws_secret_access_key', 'SignatureDoesNotMatch'),
                            ('aws_access_key_id', 'InvalidClientTokenId')]:
            changed = dict(self.credentials)
            changed[field] = ('X' if changed[field][0] != 'X' else 'Y') + changed[field][1:]
            env = {k: v for k, v in self.env.items() if k not in ('AWS_PROFILE', 'AWS_SHARED_CREDENTIALS_FILE')}
            env.update(AWS_ACCESS_KEY_ID=changed['aws_access_key_id'],
                       AWS_SECRET_ACCESS_KEY=changed['aws_secret_access_key'], AWS_SHARED_CREDENTIALS_FILE='/dev/null')
            result = self.run(base, ok=(0, 254, 255), env=env)
            observed = cli_error_code(result, 'GetCallerIdentity')
            if result.returncode == 254 and observed == code:
                emit('auth-reject-' + field.split('_')[1], 'PASS', code=code)
                continue
            # Structured wire proof: the same signer must first succeed with the real keys.
            original = signed_sts_request(self.credentials['aws_access_key_id'], self.credentials['aws_secret_access_key'])
            with self.http(original, context) as response:
                identity_gate(signed_sts_identity(response.status, response.read(8193)) or {})
            try:
                with self.http(signed_sts_request(changed['aws_access_key_id'], changed['aws_secret_access_key']), context):
                    raise Failure('auth-request-accepted')
            except urllib.error.HTTPError as error:
                require(sts_rejection(error.code, error.read(8193), code), 'auth-rejection-unproven')
            emit('auth-reject-' + field.split('_')[1], 'PASS', code=code, method='wire')
        request = urllib.request.Request(ENDPOINT, data=b'Action=GetCallerIdentity&Version=2011-06-15',
                                         headers={'Host': 'sts.ca-central-1.amazonaws.com',
                                                  'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with self.http(request, context):
                raise Failure('unsigned-request-accepted')
        except urllib.error.HTTPError as error:
            require(unsigned_sts_rejected(error.code, error.read(8193)), 'unsigned-sts-rejection')
        self.ctl('3')

    # ---------- disposable root ----------
    def prepare_root(self):
        self.current = 'provider-init'
        source = TOOLS / 'source'
        shutil.copytree(source / 'infra', WORK / 'root' / 'infra')
        shutil.rmtree(ROOT / 'tests')
        names = sorted(p.name for p in ROOT.iterdir())
        require(names == ['.terraform.lock.hcl', 'README.md', 'backend.s3.tfbackend.example', 'backend.tf',
                          'backend_override.tf.example', 'local.auto.tfvars.example', 'main.tf', 'outputs.tf',
                          'providers.tf', 'terraform.tfvars', 'variables.tf', 'versions.tf'], 'root-source-inventory')
        (ROOT / 'zz_emulator_override.tf').write_text(
            '# Disposable rehearsal adapter: emulator endpoints and the synthetic account guard.\n'
            'provider "aws" {\n'
            '  region              = "ca-central-1"\n'
            '  allowed_account_ids = ["000000000000"]\n'
            f'  custom_ca_bundle    = "{self.env["AWS_CA_BUNDLE"]}"\n'
            '  max_retries         = 2\n'
            '  endpoints {\n'
            f'    ec2 = "{ENDPOINT}"\n'
            f'    sts = "{ENDPOINT}"\n'
            '  }\n'
            '}\n')
        self.variables('create')
        cli = WORK / 'terraform.rc'
        cli.write_text('provider_installation { filesystem_mirror { path = "%s" include = ["registry.terraform.io/hashicorp/aws"] } }\n'
                       % (TOOLS / 'mirror'))
        self.env['TF_CLI_CONFIG_FILE'] = str(cli)
        lock = (ROOT / '.terraform.lock.hcl').read_bytes()
        self.tf('init', '-input=false', '-lockfile=readonly', '-no-color')
        self.tf('validate', '-no-color')
        require((ROOT / '.terraform.lock.hcl').read_bytes() == lock, 'provider-lock-unchanged')
        self.ctl('9')
        require(not (ROOT / 'terraform.tfstate').exists(), 'initial-state-empty')
        self.ctl('10')

    def variables(self, phase):
        (ROOT / 'zz_emulator.auto.tfvars.json').write_text(json.dumps(
            {'project': PROJECT, 'aws_account_id': '000000000000',
             'tags': {'VerificationRun': self.run_id, 'Phase': phase},
             **({'interface_endpoints': None} if self.scenario == 'no-interface-endpoints' else {})}))

    # ---------- inventory ----------
    def inventory(self):
        ec2 = lambda op, key: self.aws('ec2', op)[key]
        return {
            'aws_vpc': {v['VpcId']: v for v in ec2('describe-vpcs', 'Vpcs')},
            'aws_subnet': {v['SubnetId']: v for v in ec2('describe-subnets', 'Subnets')},
            'aws_internet_gateway': {v['InternetGatewayId']: v for v in ec2('describe-internet-gateways', 'InternetGateways')},
            'aws_route_table': {v['RouteTableId']: v for v in ec2('describe-route-tables', 'RouteTables')},
            'aws_eip': {v['AllocationId']: v for v in ec2('describe-addresses', 'Addresses')},
            'aws_nat_gateway': {v['NatGatewayId']: v for v in ec2('describe-nat-gateways', 'NatGateways')},
            'aws_security_group': {v['GroupId']: v for v in ec2('describe-security-groups', 'SecurityGroups')},
            'aws_vpc_security_group_ingress_rule': {v['SecurityGroupRuleId']: v for v in
                                                    ec2('describe-security-group-rules', 'SecurityGroupRules')},
            'aws_vpc_endpoint': {v['VpcEndpointId']: v for v in ec2('describe-vpc-endpoints', 'VpcEndpoints')},
        }

    @staticmethod
    def live(kind, row):
        state = row.get('State')
        return not (kind in ('aws_nat_gateway', 'aws_vpc_endpoint') and str(state).lower() in ('deleted', 'deleting'))

    def baseline_preserved(self, current):
        for kind, rows in self.baseline.items():
            for rid, row in rows.items():
                require(rid in current[kind], 'baseline-resource-removed:' + kind)
                require(normal(current[kind][rid]) == normal(row), 'baseline-resource-changed:' + kind)

    # ---------- plans ----------
    def plan(self, action, phase):
        path = WORK / (action + '.tfplan')
        args = ['plan', '-input=false', '-no-color', '-out=' + str(path)]
        if action == 'delete':
            args.append('-destroy')
        self.tf(*args)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        plan = strict_json(self.tf('show', '-json', str(path)).stdout)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'plan-changed-during-review')
        self.inspect(plan, action, phase)
        self.plans[str(path)] = digest
        return path

    def inspect(self, plan, action, phase):
        require(plan.get('terraform_version') == '1.17.0', 'plan-version')
        require(not plan.get('errored') and not plan.get('deferred_changes'), 'plan-errored-or-deferred')
        require(not plan.get('resource_drift'), 'plan-drift')
        provider = plan['configuration']['provider_config']['aws']['expressions']
        endpoints = provider['endpoints'][0]
        require(provider['allowed_account_ids']['constant_value'] == ['000000000000']
                and endpoints['ec2']['constant_value'] == ENDPOINT and endpoints['sts']['constant_value'] == ENDPOINT
                and set(endpoints) == {'ec2', 'sts'}, 'provider-endpoint-guard')
        changes = {c['address']: c for c in plan.get('resource_changes', [])}
        require(set(changes) == set(self.expected), 'plan-resource-inventory')
        for address, change in changes.items():
            require(change['mode'] == 'managed' and change['type'] == self.expected[address]
                    and change['provider_name'] == 'registry.terraform.io/hashicorp/aws'
                    and change.get('module_address') == 'module.network', 'plan-resource-identity')
            actions, kind = change['change']['actions'], self.expected[address]
            if action == 'create':
                require(actions == ['create'], 'plan-actions-create')
            elif action == 'delete':
                require(actions == ['delete'], 'plan-actions-delete')
                rid = change['change']['before'].get('id')
                require(rid and rid == self.state_ids.get(address), 'destroy-target-identity')
            elif action == 'update':
                require(actions == (['no-op'] if kind in UNTAGGED else ['update']), 'plan-actions-update')
            else:
                require(actions == ['no-op'], 'plan-actions-no-op')
            if action in ('create', 'update') and kind not in UNTAGGED:
                after = change['change']['after'].get('tags_all')
                require(isinstance(after, dict) and after.get('VerificationRun') == self.run_id
                        and after.get('Phase') == phase and after.get('project') == PROJECT and after.get('env') == 'dev'
                        and after.get('managed') == 'terraform' and after.get('Name') and after.get('service'),
                        'plan-tags')
            if action == 'update' and kind not in UNTAGGED:
                before = {k: v for k, v in change['change']['before'].items() if k not in ('tags', 'tags_all')}
                after = {k: v for k, v in change['change']['after'].items() if k not in ('tags', 'tags_all')}
                require(before == after, 'update-changes-only-tags')
        self.ctl('11')

    @staticmethod
    def drift_summary(refreshed):
        drift = []
        for d in refreshed.get('resource_drift', []):
            before, after = d['change'].get('before') or {}, d['change'].get('after') or {}
            keys = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            drift.append({'address': d['address'], 'actions': d['change']['actions'],
                          'changed': {k: [str(before.get(k))[:120], str(after.get(k))[:120]] for k in keys}})
        return drift

    def check_refresh(self, refreshed, drift, nat):
        """Allow only reviewed computed-attribute convergence that real AWS shows as well.

        The NAT gateway associates the EIP after the EIP was created, and the separate
        aws_route fills the private table's computed route list. The values must match
        the NAT gateway the API reports; any other drift or output change fails.
        """
        outputs = [k for k, v in refreshed.get('output_changes', {}).items() if v['actions'] != ['no-op']]
        require(not outputs, 'refresh-output-changes')
        allowed = {M + 'aws_eip.nat["ca-central-1a"]': {'association_id', 'network_interface', 'private_dns', 'private_ip'},
                   M + 'aws_route_table.private_by_az["ca-central-1a"]': {'route'}}
        nat_id = self.state_ids[M + 'aws_nat_gateway.this["ca-central-1a"]']
        require(nat.get('NatGatewayId') == nat_id, 'refresh-nat-identity')
        address = [a for a in nat.get('NatGatewayAddresses', [])
                   if a.get('AllocationId') == self.state_ids[M + 'aws_eip.nat["ca-central-1a"]']]
        require(len(address) == 1, 'nat-eip-association')
        for d in refreshed.get('resource_drift', []):
            changed = set(next(x['changed'] for x in drift if x['address'] == d['address']))
            require(d['address'] in allowed and d['change']['actions'] == ['update'] and changed <= allowed[d['address']],
                    'refresh-drift-unexpected')
            after = d['change']['after']
            if 'aws_eip' in d['address']:
                require(after.get('network_interface') == address[0]['NetworkInterfaceId']
                        and after.get('private_ip') == address[0]['PrivateIp'], 'refresh-eip-values')
            else:
                require([(r['cidr_block'], r['nat_gateway_id']) for r in after.get('route', [])] == [('0.0.0.0/0', nat_id)],
                        'refresh-route-values')

    def apply(self, path):
        require(hashlib.sha256(path.read_bytes()).hexdigest() == self.plans.get(str(path)), 'reviewed-plan-hash')
        self.tf('apply', '-input=false', '-no-color', str(path))

    def state(self):
        if not (ROOT / 'terraform.tfstate').exists():
            return {}
        value = strict_json(self.tf('state', 'pull').stdout)
        require(value.get('version') == 4 and value.get('terraform_version') == '1.17.0', 'state-header')
        ids = {}
        for resource in value.get('resources', []):
            if resource['mode'] != 'managed':
                continue
            for instance in resource['instances']:
                key = instance.get('index_key')
                suffix = '' if key is None else ('[%d]' % key if isinstance(key, int) else '["%s"]' % key)
                ids[resource['module'] + '.' + resource['type'] + '.' + resource['name'] + suffix] = instance['attributes']
        return ids

    # ---------- API identity checks ----------
    def api_check(self, phase):
        current = self.inventory()
        self.baseline_preserved(current)
        attrs = self.state()
        require(set(attrs) == set(self.expected), 'state-inventory')
        self.state_ids = {a: v['id'] for a, v in attrs.items()}
        vpc_id = attrs[M + 'aws_vpc.this']['id']
        for address, kind in self.expected.items():
            a = attrs[address]
            if kind == 'aws_route_table_association':
                tables = [t for t in current['aws_route_table'].values()
                          if any(x.get('RouteTableAssociationId') == a['id'] for x in t.get('Associations', []))]
                require(len(tables) == 1 and tables[0]['RouteTableId'] == a['route_table_id']
                        and any(x.get('SubnetId') == a['subnet_id'] for x in tables[0]['Associations']), 'api-association')
                continue
            if kind == 'aws_route':
                table = current['aws_route_table'][a['route_table_id']]
                require(any(r.get('DestinationCidrBlock') == '0.0.0.0/0' and r.get('NatGatewayId') == a['nat_gateway_id']
                            for r in table.get('Routes', [])), 'api-route')
                continue
            row = current[kind].get(a['id'])
            require(row is not None and self.live(kind, row), 'api-missing:' + kind)
            require(a['id'] not in self.baseline[kind], 'owned-id-preexisting:' + kind)
            tags = {t['Key']: t['Value'] for t in row.get('Tags', [])}
            require(tags.get('VerificationRun') == self.run_id and tags.get('Phase') == phase
                    and tags.get('project') == PROJECT and tags.get('Name') == a['tags_all'].get('Name'), 'api-tags:' + kind)
            if kind not in ('aws_vpc', 'aws_eip'):
                require(row.get('VpcId', vpc_id) == vpc_id or row.get('VpcId') is None, 'api-vpc:' + kind)
        # Every other new object must be an AWS side effect inside the owned VPC.
        owned = set(self.state_ids.values())
        for kind, rows in current.items():
            for rid, row in rows.items():
                if rid in self.baseline[kind] or rid in owned or not self.live(kind, row):
                    continue
                parent = row.get('VpcId') or current['aws_security_group'].get(row.get('GroupId'), {}).get('VpcId')
                require(parent == vpc_id, 'unexpected-new-resource:' + kind)
        endpoints = sorted(current['aws_vpc_endpoint'][self.state_ids[a]]['ServiceName']
                           for a, k in self.expected.items() if k == 'aws_vpc_endpoint')
        emit('api-identity-' + phase, 'PASS', vpc_id=vpc_id, owned=len(owned), endpoints=endpoints)

    def probe_security_group(self, vpc_id):
        """Direct API evidence: does CreateSecurityGroup add the default egress rule?"""
        tags = 'ResourceType=security-group,Tags=[{Key=VerificationRun,Value=%s},{Key=Phase,Value=probe}]' % self.run_id
        created = self.aws('ec2', 'create-security-group', '--group-name', PROJECT + '-dev-sg-probe',
                           '--description', 'Step 2 egress probe', '--vpc-id', vpc_id, '--tag-specifications', tags)
        group = created['GroupId']
        self.probe = group
        require(group not in self.baseline['aws_security_group'], 'probe-id-preexisting')
        rows = self.aws('ec2', 'describe-security-group-rules', '--filters', 'Name=group-id,Values=' + group)['SecurityGroupRules']
        egress = [r for r in rows if r.get('IsEgress')]
        described = self.aws('ec2', 'describe-security-groups', '--group-ids', group)['SecurityGroups'][0]
        result = {'egress_rules': len(egress), 'ingress_rules': len(rows) - len(egress),
                  'ip_permissions_egress': len(described.get('IpPermissionsEgress', []))}
        # First the exact form the AWS provider sends (protocol -1 with ports 0), then without ports.
        for label, perms in [('provider_form_ports_0', 'IpProtocol=-1,FromPort=0,ToPort=0,IpRanges=[{CidrIp=0.0.0.0/0}]'),
                             ('without_ports', 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]')]:
            p = self.aws('ec2', 'revoke-security-group-egress', '--group-id', group, '--ip-permissions', perms, ok=(0, 254))
            result['revoke_' + label] = 'accepted' if p.returncode == 0 else (cli_error_code(p, 'RevokeSecurityGroupEgress') or 'rejected')
        result['egress_rules_after'] = len([r for r in self.aws('ec2', 'describe-security-group-rules', '--filters',
                                                                 'Name=group-id,Values=' + group)['SecurityGroupRules'] if r.get('IsEgress')])
        result['stored_default_rule'] = {k: egress[0].get(k) for k in ('IpProtocol', 'FromPort', 'ToPort', 'CidrIpv4')} if egress else None
        tags_now = {t['Key']: t['Value'] for t in described.get('Tags', [])}
        require(tags_now.get('VerificationRun') == self.run_id and described.get('VpcId') == vpc_id, 'probe-identity')
        # Direct API probe of one interface endpoint in the owned VPC (not a Terraform result).
        subnet = self.state_ids[M + 'aws_subnet.private["private1"]']
        vtags = 'ResourceType=vpc-endpoint,Tags=[{Key=VerificationRun,Value=%s},{Key=Phase,Value=probe}]' % self.run_id
        p = self.aws('ec2', 'create-vpc-endpoint', '--vpc-id', vpc_id, '--vpc-endpoint-type', 'Interface', '--service-name',
                     'com.amazonaws.ca-central-1.sts', '--subnet-ids', subnet, '--security-group-ids', group,
                     '--private-dns-enabled', '--tag-specifications', vtags, ok=(0, 254, 255))
        if p.returncode == 0:
            endpoint = strict_json(p.stdout)['VpcEndpoint']['VpcEndpointId']
            self.probe_endpoint = endpoint
            row = self.aws('ec2', 'describe-vpc-endpoints', '--vpc-endpoint-ids', endpoint)['VpcEndpoints'][0]
            etags = {t['Key']: t['Value'] for t in row.get('Tags', [])}
            require(etags.get('VerificationRun') == self.run_id and row['VpcId'] == vpc_id, 'probe-endpoint-identity')
            result['interface_endpoint'] = {'create': 'accepted', 'state': row.get('State'), 'private_dns': row.get('PrivateDnsEnabled'),
                                            'subnets': len(row.get('SubnetIds', [])), 'groups': len(row.get('Groups', [])),
                                            'dns_entries': len(row.get('DnsEntries', []))}
            self.aws('ec2', 'delete-vpc-endpoints', '--vpc-endpoint-ids', endpoint)
            left = [e for e in self.aws('ec2', 'describe-vpc-endpoints')['VpcEndpoints']
                    if e['VpcEndpointId'] == endpoint and self.live('aws_vpc_endpoint', e)]
            require(not left, 'probe-endpoint-not-deleted')
            result['interface_endpoint']['delete'] = 'verified'
            self.probe_endpoint = None
        else:
            result['interface_endpoint'] = {'create': cli_error_code(p, 'CreateVpcEndpoint') or ('http-501' if '501' in p.stderr else 'rejected')}
        self.aws('ec2', 'delete-security-group', '--group-id', group)
        remaining = {g['GroupId'] for g in self.aws('ec2', 'describe-security-groups')['SecurityGroups']}
        require(group not in remaining, 'probe-not-deleted')
        self.probe = None
        emit('sg-default-egress-probe', 'PASS', **result)
        self.notes.append({'security_group_probe': result})

    def absence(self):
        current = self.inventory()
        self.baseline_preserved(current)
        for address, rid in self.state_ids.items():
            kind = self.expected[address]
            if kind in UNTAGGED:
                continue
            row = current[kind].get(rid)
            require(row is None or not self.live(kind, row), 'api-still-present:' + kind)
        for kind, rows in current.items():
            extra = [rid for rid, row in rows.items() if rid not in self.baseline[kind] and self.live(kind, row)]
            require(not extra, 'residual-resource:' + kind)

    # ---------- lifecycle ----------
    def lifecycle(self):
        self.current = 'baseline'
        self.baseline = self.inventory()
        require(all(v.get('CidrBlock') != '10.40.0.0/16' for v in self.baseline['aws_vpc'].values()), 'test-cidr-preexisting')
        emit('baseline', 'PASS', counts={k: len(v) for k, v in self.baseline.items()})
        self.current = 'plan'
        path = self.plan('create', 'create'); self.op('plan', resources=len(self.expected))
        self.current = 'create'
        self.creation_attempted = True
        self.apply(path); self.op('create')
        self.current = 'api_create'
        self.api_check('create'); self.op('api_create'); self.ctl('12')
        if self.scenario == 'no-interface-endpoints':
            self.current = 'sg_probe'
            self.probe_security_group(self.state_ids[M + 'aws_vpc.this'])
        self.current = 'read'
        read = WORK / 'refresh.tfplan'
        code = self.tf('plan', '-refresh-only', '-detailed-exitcode', '-input=false', '-no-color', '-out=' + str(read), ok=(0, 2)).returncode
        refreshed = strict_json(self.tf('show', '-json', str(read)).stdout)
        drift = self.drift_summary(refreshed)
        nat_id = self.state_ids[M + 'aws_nat_gateway.this["ca-central-1a"]']
        nat = self.aws('ec2', 'describe-nat-gateways', '--nat-gateway-ids', nat_id)['NatGateways'][0]
        self.check_refresh(refreshed, drift, nat)
        emit('refresh-convergence', 'PASS', exit_code=code, drift=[{'address': x['address'], 'changed': sorted(x['changed'])} for x in drift])
        if code == 2:
            self.tf('apply', '-input=false', '-no-color', str(read))
        again = self.tf('plan', '-refresh-only', '-detailed-exitcode', '-input=false', '-no-color', ok=(0, 2)).returncode
        require(again == 0, 'refresh-not-converged')
        self.op('read')
        self.current = 'update_plan'
        self.variables('updated')
        path = self.plan('update', 'updated'); self.op('update_plan')
        self.current = 'update'
        self.apply(path); self.op('update')
        self.current = 'api_update'
        self.api_check('updated'); self.op('api_update')
        self.current = 'no_op'
        self.plan('no-op', 'updated'); self.op('no_op')
        self.destroy('updated')

    def destroy(self, phase):
        self.current = 'destroy_plan'
        path = self.plan('delete', phase); self.op('destroy_plan')
        self.current = 'destroy'
        self.apply(path); self.op('destroy')
        self.current = 'state_empty'
        require(self.state() == {}, 'state-not-empty'); self.op('state_empty')
        self.current = 'api_absence'
        self.absence(); self.op('api_absence'); self.op('baseline_preserved'); self.ctl('13')

    def recover(self):
        """Clean up only positively identified, test-owned resources after a failure."""
        if getattr(self, 'probe_endpoint', None):
            row = self.aws('ec2', 'describe-vpc-endpoints', '--vpc-endpoint-ids', self.probe_endpoint)['VpcEndpoints'][0]
            require({t['Key']: t['Value'] for t in row.get('Tags', [])}.get('VerificationRun') == self.run_id, 'recovery-probe-endpoint')
            self.aws('ec2', 'delete-vpc-endpoints', '--vpc-endpoint-ids', self.probe_endpoint)
            emit('recovery-probe-endpoint-deleted', 'PASS'); self.probe_endpoint = None
        if self.probe:
            row = self.aws('ec2', 'describe-security-groups', '--group-ids', self.probe)['SecurityGroups'][0]
            tags = {t['Key']: t['Value'] for t in row.get('Tags', [])}
            require(tags.get('VerificationRun') == self.run_id and self.probe not in self.baseline['aws_security_group'],
                    'recovery-probe-identity')
            self.aws('ec2', 'delete-security-group', '--group-id', self.probe)
            emit('recovery-probe-deleted', 'PASS'); self.probe = None
        attrs = self.state()
        if attrs:
            require(set(attrs) <= set(self.expected), 'recovery-state-unexpected')
            self.state_ids = {a: v['id'] for a, v in attrs.items()}
            for address, value in attrs.items():
                kind = self.expected[address]
                if kind not in UNTAGGED:
                    require(value['id'] not in self.baseline[kind], 'recovery-never-delete-preexisting')
                    require(value.get('tags_all', {}).get('VerificationRun') == self.run_id, 'recovery-owner-tag')
            path = WORK / 'recovery.tfplan'
            self.tf('plan', '-destroy', '-input=false', '-no-color', '-out=' + str(path))
            plan = strict_json(self.tf('show', '-json', str(path)).stdout)
            changes = plan.get('resource_changes', [])
            require(changes and all(c['change']['actions'] == ['delete'] and c['address'] in attrs
                                    and c['change']['before']['id'] == attrs[c['address']]['id'] for c in changes),
                    'recovery-plan-scope')
            self.tf('apply', '-input=false', '-no-color', str(path))
            require(self.state() == {}, 'recovery-state-not-empty')
            emit('recovery-destroy', 'PASS', resources=len(changes))
        self.absence()
        emit('recovery-absence', 'PASS')

    def cleanup(self):
        receipts = {}
        if self.emulator is not None:
            if self.emulator.poll() is None:
                self.emulator.send_signal(signal.SIGTERM)
                try:
                    self.emulator.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    self.emulator.kill(); self.emulator.wait(timeout=10)
            receipts['process'] = 'PASS' if self.emulator.poll() is not None else 'FAIL'
        for child in list(WORK.iterdir()):
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        receipts['material'] = 'PASS' if not any(WORK.iterdir()) else 'FAIL'
        return receipts


def main():
    r = Rehearsal()
    failure = None
    try:
        r.isolation(); r.startup(); r.authenticate(); r.prepare_root(); r.lifecycle()
    except Failure as error:
        failure = error
    except Blocked as error:
        failure = Failure(str(error))
    except Exception as error:  # never print private values
        failure = Failure('unclassified:' + type(error).__name__)
    if failure:
        status = 'PARTIAL-SKIP' if failure.unsupported else ('BLOCKED' if not r.creation_attempted and r.current in
                                                            ('isolation', 'startup', 'authentication', 'provider-init') else 'FAIL')
        if r.current in r.ops:
            r.ops[r.current] = status
        if failure.unsupported and failure.api:
            r.unsupported.append(failure.api)
        emit('failure', status, operation=r.current, label=safe(failure.label), api=failure.api, detail=failure.detail)
    resource_cleanup = 'NOT_TESTED'
    if r.creation_attempted:
        if failure:
            try:
                r.recover(); resource_cleanup = 'PASS'
            except Failure as error:
                resource_cleanup = 'FAIL'
                emit('recovery', 'FAIL', label=safe(error.label), api=error.api, detail=error.detail)
            except Exception as error:
                resource_cleanup = 'FAIL'
                emit('recovery', 'FAIL', label=safe(str(error))[:200])
        else:
            resource_cleanup = 'PASS'
    receipts = r.cleanup()
    if resource_cleanup == 'PASS' and receipts.get('material') == 'PASS' and receipts.get('process') == 'PASS':
        r.ctl('14')
    summary = {'run_id': r.run_id, 'tested_sha': r.meta['sha'], 'harness_sha256': r.meta.get('harness_sha256'),
               'execution': r.meta.get('execution', {'kind': 'local'}), 'scenario': 'network root (real vpc module), committed values' + ('' if r.scenario == 'full' else ' without interface_endpoints'),
               'versions': {k: r.prepared['versions'][k].get('version', r.prepared['versions'][k]) if isinstance(r.prepared['versions'][k], dict) else r.prepared['versions'][k]
                            for k in ('emulator', 'terraform', 'awscli', 'provider')},
               'controls': r.controls, 'operations': r.ops, 'resource_cleanup': resource_cleanup,
               'material_cleanup': receipts.get('material', 'NOT_TESTED'), 'process_cleanup': receipts.get('process', 'NOT_TESTED'),
               'unsupported_apis': r.unsupported, 'scenario_id': r.scenario, 'notes': r.notes,
               'failure': None if not failure else {'operation': r.current, 'label': safe(failure.label), 'api': failure.api}}
    (EVIDENCE / ('summary-' + r.run_id + '.json')).write_text(json.dumps(summary, indent=2))
    # The complete non-secret record also goes to stdout, so a CI job log and job summary keep it.
    emit('summary-record', 'PASS', record=summary)
    emit('summary', 'PASS' if not failure and all(v == 'PASS' for v in r.controls.values()) else 'INCOMPLETE',
         operations=r.ops, controls=r.controls)
    return 0 if not failure else 1


if __name__ == '__main__':
    sys.exit(main())
