import os
from pathlib import Path

from skyrim_downgrader import manifest

ACF = '''"AppState"
{
	"appid"		"489830"
	"installdir"		"Skyrim Special Edition"
	"StateFlags"		"4"
	"buildid"		"24914197"
	"AutoUpdateBehavior"		"0"
}
'''


def test_set_auto_update_behavior_rewrites_value(tmp_path: Path):
    acf = tmp_path / "appmanifest_489830.acf"
    acf.write_text(ACF, encoding="utf-8")
    assert manifest.read_auto_update_behavior(acf) == 0
    assert manifest.set_auto_update_behavior(acf, 1) is True
    assert manifest.read_auto_update_behavior(acf) == 1
    assert manifest.read_buildid(acf) == "24914197"
    # untouched otherwise
    assert '"installdir"\t\t"Skyrim Special Edition"' in acf.read_text(encoding="utf-8")
    assert manifest.set_auto_update_behavior(acf, 1) is False


def test_read_only_roundtrip_and_edit_through_it(tmp_path: Path):
    acf = tmp_path / "appmanifest_489830.acf"
    acf.write_text(ACF, encoding="utf-8")
    manifest.set_read_only(acf, True)
    assert manifest.is_read_only(acf)
    assert manifest.set_auto_update_behavior(acf, 1) is True
    assert manifest.is_read_only(acf)  # restored after the edit
    manifest.set_read_only(acf, False)
    assert os.access(acf, os.W_OK)
