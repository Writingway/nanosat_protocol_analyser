import os
import time

import pytest

from protocols.registry import ProtocolRegistry

VALID = """
name: demo
min_length: 2
max_length: 8
fields: [{name: A, offset: 0, size: 1}, {name: B, offset: 1, size: 1}]
"""


def write(path, text):
    path.write_text(text)
    # garantit une date de modification différente même sur un système de fichiers rapide
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 1 + time.time() % 1))


@pytest.fixture
def reg(tmp_path):
    return ProtocolRegistry(tmp_path, poll_interval=0)


def test_loads_valid_file(reg, tmp_path):
    write(tmp_path / "demo.yaml", VALID)
    assert reg.get("demo").spec.fields[1].name == "B"


def test_hot_reload(reg, tmp_path):
    write(tmp_path / "demo.yaml", VALID)
    sha1 = reg.get("demo").sha256
    write(tmp_path / "demo.yaml", VALID.replace("name: B", "name: C"))
    lp = reg.get("demo")
    assert lp.sha256 != sha1
    assert lp.spec.fields[1].name == "C"


def test_invalid_update_keeps_previous_version(reg, tmp_path):
    write(tmp_path / "demo.yaml", VALID)
    sha1 = reg.get("demo").sha256
    write(tmp_path / "demo.yaml", VALID.replace("size: 1}]", "size: 0}]"))
    assert reg.get("demo").sha256 == sha1  # toujours l'ancienne
    st = reg.status()[0]
    assert st["active"] and st["errors"]
    # correction → l'erreur disparaît
    write(tmp_path / "demo.yaml", VALID.replace("name: B", "name: D"))
    assert reg.get("demo").spec.fields[1].name == "D"
    assert reg.status()[0]["errors"] == []


def test_invalid_new_file_reported(reg, tmp_path):
    write(tmp_path / "demo.yaml", "name: [")
    assert reg.get("demo") is None
    assert reg.status()[0]["errors"][0].startswith("syntaxe YAML")


def test_name_must_match_filename(reg, tmp_path):
    write(tmp_path / "autre.yaml", VALID)
    assert reg.get("demo") is None
    assert "autre.yaml" in reg.status()[0]["errors"][0] or "demo" in reg.status()[0]["errors"][0]


def test_deleted_file_removes_protocol(reg, tmp_path):
    write(tmp_path / "demo.yaml", VALID)
    assert reg.get("demo")
    (tmp_path / "demo.yaml").unlink()
    assert reg.get("demo") is None


def test_project_protocols_are_valid():
    from django.conf import settings

    reg = ProtocolRegistry(settings.PROTOCOLS_DIR, poll_interval=0)
    status = reg.status()
    assert {s["name"] for s in status} >= {"nsp", "ewc31", "emea"}
    assert all(s["active"] and not s["errors"] for s in status), status
