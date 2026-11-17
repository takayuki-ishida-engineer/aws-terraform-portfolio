"""Run root test fixtures in a sibling copy without the committed input values.

`terraform test` always loads terraform.tfvars and *.auto.tfvars from the root
directory, even for another -test-directory. Required-input rejection fixtures
must not inherit the committed placeholder values, so they run in a temporary
directory next to the root (same depth, so relative module sources stay valid)
that holds only the root's *.tf files, its lock file and, where present, the
non-secret feature policy `features.auto.tfvars`. The root's initialized working
directory is reused through TF_DATA_DIR. No provider is installed and no AWS API
is called.
"""
import contextlib
import shutil
import tempfile
from pathlib import Path

# Feature flags are policy, not environment input; keep them so the fixtures
# exercise the same effective configuration as the root's native tests.
FEATURE_POLICY = "features.auto.tfvars"


@contextlib.contextmanager
def tfvars_free_copy(root):
    """Yield (copy_directory, extra_environment) for a root without its input values."""
    root = Path(root).resolve()
    if not (root / ".terraform").is_dir():
        raise ValueError("root_not_initialized:" + root.name)
    with tempfile.TemporaryDirectory(prefix="." + root.name + "-no-tfvars-", dir=root.parent) as temporary:
        copy = Path(temporary)
        for source in root.glob("*.tf"):
            shutil.copy2(source, copy / source.name)
        shutil.copy2(root / ".terraform.lock.hcl", copy / ".terraform.lock.hcl")
        if (root / FEATURE_POLICY).is_file():
            shutil.copy2(root / FEATURE_POLICY, copy / FEATURE_POLICY)
        (copy / "tests").mkdir()
        copied = sorted(path.name for path in copy.iterdir() if path.name.endswith((".tfvars", ".tfvars.json")))
        if copied not in ([], [FEATURE_POLICY]):
            raise ValueError("input_values_copied:" + ",".join(copied))
        yield copy, {"TF_DATA_DIR": str(root / ".terraform")}
