import subprocess
import tempfile
import os
import sys

def test_licence_and_secret_guard_clean():
    """Runs licence_and_secret_guard.py on current repo - must pass cleanly."""
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../scripts/licence_and_secret_guard.py"))
    res = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
    assert res.returncode == 0, f"Guard failed unexpectedly: {res.stdout} {res.stderr}"
    assert "Licence & Secret Guard passed" in res.stdout

def test_licence_guard_catches_kml():
    """Simulates a .kml file being checked by the guard."""
    from scripts.licence_and_secret_guard import check_file

    with tempfile.NamedTemporaryFile(suffix=".kml", delete=False) as f:
        f.write(b"<kml xmlns='http://www.opengis.net/kml/2.2'><Document></Document></kml>")
        temp_path = f.name

    try:
        violations = check_file(temp_path)
        assert len(violations) > 0
        assert any("KML" in v for v in violations)
    finally:
        os.remove(temp_path)

def test_licence_guard_catches_private_key():
    """Simulates an unwhitelisted 64-hex private key pattern."""
    from scripts.licence_and_secret_guard import check_file

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        # A mock raw private key string
        f.write(b"PRIVATE_KEY = '4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d'\n")
        temp_path = f.name

    try:
        violations = check_file(temp_path)
        assert len(violations) > 0
        assert any("private key" in v.lower() for v in violations)
    finally:
        os.remove(temp_path)
