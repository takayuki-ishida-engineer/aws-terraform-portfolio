"""Real temporary GPG keys and fail-closed status-fd mutations; no network."""
import io,json,subprocess,tempfile,time,unittest
from contextlib import contextmanager,redirect_stdout,redirect_stderr
from pathlib import Path
from unittest.mock import patch
from gates import SignatureBlocked,GPG_DIAGNOSTIC_CODES,signature_gate
import prepare

PRIMARY='A'*40;SUBKEY='B'*40;OTHER='C'*40

def valid(signer=PRIMARY,primary=PRIMARY):
  return ('[GNUPG:] VALIDSIG '+signer+' 2026-11-15 1794700800 0 4 0 22 8 00'+(' '+primary if primary else '')+'\n').encode('ascii')

class SignatureStatus(unittest.TestCase):
  def blocked(self,status,code,exit_code=0):
    with self.assertRaises(SignatureBlocked) as caught:signature_gate(status,PRIMARY,exit_code)
    self.assertEqual(caught.exception.code,code)

  def test_primary_and_bound_subkey_status(self):
    self.assertEqual(signature_gate(valid(),PRIMARY,0)['signer'],PRIMARY)
    self.assertEqual(signature_gate(valid(SUBKEY),PRIMARY,0),{'signer':SUBKEY,'primary':PRIMARY})
    self.assertEqual(signature_gate(valid(primary=None),PRIMARY,0)['primary'],PRIMARY)
    self.blocked(valid(SUBKEY,None),'SIGNER_PRIMARY_MISMATCH')
    self.blocked(valid(PRIMARY,OTHER),'SIGNER_PRIMARY_MISMATCH')
    self.blocked(valid(OTHER,OTHER),'SIGNER_PRIMARY_MISMATCH')

  def test_binary_notation_and_untrusted_text_are_not_decoded(self):
    # Regression for the actual AWS status stream's non-UTF-8 NOTATION_DATA.
    status=b'[GNUPG:] NOTATION_NAME fixture@invalid\n[GNUPG:] NOTATION_DATA \xff\xd7secret\n'+valid()
    self.assertEqual(signature_gate(status,PRIMARY,0)['primary'],PRIMARY)
    # Status words in a UID/notation are not actual status records.
    signature_gate(status+b'[GNUPG:] GOODSIG dummy BADSIG EXPKEYSIG\n',PRIMARY,0)
    self.blocked(status+b'[GNUPG:] BADSIG dummy\n','SIGNATURE_INVALID')

  def test_missing_multiple_malformed_and_nonzero(self):
    self.blocked(b'','VALIDSIG_MISSING')
    self.blocked(valid()+valid(),'VALIDSIG_MULTIPLE')
    for status in [b'[GNUPG:] VALIDSIG short\n',valid().replace(PRIMARY.encode(),b'\xff',1),valid()+b'[GNUPG:] VALIDSIG\n']:
      with self.subTest(status_length=len(status)):self.blocked(status,'VALIDSIG_MULTIPLE' if status.count(b'VALIDSIG')==2 else 'VALIDSIG_MALFORMED')
    self.blocked(valid(),'GPG_EXIT_NONZERO',1)
    self.blocked(valid(),'GPG_EXIT_NONZERO',-9)

  def test_expired_revoked_and_invalid_statuses(self):
    for code in ['EXPSIG','EXPKEYSIG','REVKEYSIG','KEYEXPIRED','SIGEXPIRED','KEYREVOKED']:
      with self.subTest(code=code):self.blocked(valid()+('[GNUPG:] '+code+' ignored\n').encode(),'SIGNATURE_EXPIRED_OR_REVOKED')
    for code in ['BADSIG','ERRSIG','NO_PUBKEY','NODATA','BADARMOR','ERROR','FAILURE','UNEXPECTED','TRUNCATED']:
      with self.subTest(code=code):self.blocked(valid()+('[GNUPG:] '+code+' ignored\n').encode(),'SIGNATURE_INVALID')

  def test_diagnostic_log_whitelist_and_secret_suppression(self):
    marker='UNTRUSTED_PRIVATE_EXCEPTION_OR_CREDENTIAL_VALUE'
    def failure(code):
      def main():
        with prepare.stage('emulator-gpg-signature'):raise SignatureBlocked(code)
      return main
    for code in [*GPG_DIAGNOSTIC_CODES,marker+'\n::error::forged']:
      out=io.StringIO();err=io.StringIO()
      with patch.object(prepare,'main',side_effect=failure(code)),redirect_stdout(out),redirect_stderr(err):self.assertEqual(prepare.entrypoint(),1)
      row=json.loads(out.getvalue());self.assertEqual(row['gate'],'emulator-gpg-signature');self.assertEqual(row['status'],'BLOCKED')
      self.assertIn(row['diagnostic'],GPG_DIAGNOSTIC_CODES)
      self.assertNotIn(marker,out.getvalue()+err.getvalue());self.assertEqual(err.getvalue(),'')
    def unavailable():
      with prepare.stage('emulator-gpg-signature'):
        prepare.verify_signature('unused','unused','unused',PRIMARY)
    # Failure before GPG supplies a result stays BLOCKED without a raw exception.
    out=io.StringIO()
    with patch.object(prepare,'main',side_effect=unavailable),patch.object(prepare,'command',return_value='fpr:::::::::'+PRIMARY+':'),patch.object(prepare.subprocess,'run',side_effect=RuntimeError(marker)),redirect_stdout(out):self.assertEqual(prepare.entrypoint(),1)
    self.assertEqual(json.loads(out.getvalue())['diagnostic'],'GPG_RESULT_UNAVAILABLE')
    self.assertNotIn(marker,out.getvalue())

@contextmanager
def key_home():
  with tempfile.TemporaryDirectory(prefix='signature-test-') as directory:
    home=Path(directory)
    try:yield home
    finally:
      subprocess.run(['gpgconf','--homedir',str(home),'--kill','gpg-agent'],capture_output=True)

def gpg(home,*args,ok=True):
  result=subprocess.run(['gpg','--homedir',str(home),'--no-options','--batch','--pinentry-mode','loopback','--passphrase','',*args],capture_output=True)
  if ok and result.returncode!=0:raise RuntimeError('Temporary test GPG command failed')
  return result

def create_key(home,uid,expiry='0',clock=()):
  gpg(home,*clock,'--quick-generate-key',uid,'ed25519','cert,sign',expiry)
  rows=gpg(home,'--with-colons','--fingerprint','--list-keys',uid).stdout
  return next(line.split(b':')[9].decode('ascii') for line in rows.split(b'\n') if line.startswith(b'fpr:'))

class RealGPG(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.context=key_home();cls.home=cls.context.__enter__()
    try:
      cls.primary=create_key(cls.home,'Ephemeral Publisher <publisher@example.invalid>')
      gpg(cls.home,'--quick-add-key',cls.primary,'ed25519','sign','0')
      rows=gpg(cls.home,'--with-colons','--with-subkey-fingerprint','--list-keys',cls.primary).stdout
      cls.subkey=[line.split(b':')[9].decode('ascii') for line in rows.split(b'\n') if line.startswith(b'fpr:')][1]
      cls.other=create_key(cls.home,'Other Ephemeral Publisher <other@example.invalid>')
      cls.package=cls.home/'package';cls.package.write_bytes(b'public test package\n')
      cls.key=cls.home/'public.asc';cls.key.write_bytes(gpg(cls.home,'--armor','--export').stdout)
      cls.primary_sig=cls.home/'primary.sig';cls.subkey_sig=cls.home/'subkey.sig'
      for signer,path in [(cls.primary,cls.primary_sig),(cls.subkey,cls.subkey_sig)]:
        gpg(cls.home,'--local-user',signer+'!','--output',str(path),'--detach-sign',str(cls.package))
    except BaseException:
      cls.context.__exit__(None,None,None);raise

  @classmethod
  def tearDownClass(cls):cls.context.__exit__(None,None,None)

  def verify(self,signature,package=None):
    return gpg(self.home,'--status-fd','1','--verify',str(signature),str(package or self.package),ok=False)

  def test_real_primary_and_subkey_crypto_binding(self):
    for sig,signer in [(self.primary_sig,self.primary),(self.subkey_sig,self.subkey)]:
      with self.subTest(kind=sig.name):
        result=self.verify(sig);self.assertEqual(result.returncode,0)
        self.assertEqual(signature_gate(result.stdout,self.primary,result.returncode),{'signer':signer,'primary':self.primary})
        prepare.verify_signature(self.package,sig,self.key,self.primary)
        with self.assertRaises(SignatureBlocked):signature_gate(result.stdout,self.other,result.returncode)

  def test_real_other_publisher_rejected_even_when_expected_key_present(self):
    signature=self.home/'other.sig'
    gpg(self.home,'--local-user',self.other+'!','--output',str(signature),'--detach-sign',str(self.package))
    result=self.verify(signature);self.assertEqual(result.returncode,0)
    with self.assertRaises(SignatureBlocked) as caught:prepare.verify_signature(self.package,signature,self.key,self.primary)
    self.assertEqual(caught.exception.code,'SIGNER_PRIMARY_MISMATCH')

  def test_real_tampered_package_and_invalid_detached_signature(self):
    tampered=self.home/'tampered';tampered.write_bytes(b'tampered package')
    invalid=self.home/'invalid.sig';invalid.write_bytes(b'invalid detached signature')
    for signature,package in [(self.primary_sig,tampered),(invalid,self.package)]:
      with self.subTest(kind=signature.name):
        result=self.verify(signature,package);self.assertNotEqual(result.returncode,0)
        with self.assertRaises(SignatureBlocked):signature_gate(result.stdout,self.primary,result.returncode)
        with self.assertRaises(SignatureBlocked):prepare.verify_signature(package,signature,self.key,self.primary)

  def test_real_expired_and_revoked_keys_rejected(self):
    for kind in ['expired','revoked']:
      with self.subTest(kind=kind),key_home() as home:
        past=int(time.time())-3*86400
        clock=('--faked-system-time',str(past)) if kind=='expired' else ()
        primary=create_key(home,'Temporary Lifetime Test <lifetime@example.invalid>','1d' if kind=='expired' else '0',clock)
        package=home/'package';package.write_bytes(b'public lifetime fixture');sig=home/'package.sig'
        gpg(home,*clock,'--local-user',primary+'!','--output',str(sig),'--detach-sign',str(package))
        if kind=='revoked':
          data=(home/'openpgp-revocs.d'/ (primary+'.rev')).read_bytes()
          start=data.index(b':-----BEGIN PGP PUBLIC KEY BLOCK-----')
          revocation=home/'revocation.asc';revocation.write_bytes(data[start+1:]);gpg(home,'--import',str(revocation))
        result=gpg(home,'--status-fd','1','--verify',str(sig),str(package),ok=False)
        expected=b'EXPKEYSIG' if kind=='expired' else b'REVKEYSIG'
        self.assertIn(b'[GNUPG:] '+expected,result.stdout)
        with self.assertRaises(SignatureBlocked):signature_gate(result.stdout,primary,result.returncode)
