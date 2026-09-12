from pathlib import Path

from skyrim_downgrader import steam

VDF = '''"libraryfolders"
{
	"0"
	{
		"path"		"C:\\Program Files (x86)\\Steam"
	}
	"1"
	{
		"path"		"D:\\SteamLibrary"
	}
}
'''


def test_library_folders_parses_paths(tmp_path: Path):
    (tmp_path / "steamapps").mkdir()
    (tmp_path / "steamapps" / "libraryfolders.vdf").write_text(VDF, encoding="utf-8")
    libs = steam.library_folders(tmp_path)
    assert libs[0] == tmp_path
    assert Path(r"D:\SteamLibrary").resolve() in libs


def test_find_game_dir_from_appmanifest(tmp_path: Path):
    apps = tmp_path / "steamapps"
    apps.mkdir()
    (apps / "appmanifest_489830.acf").write_text('"AppState"\n{\n\t"installdir"\t\t"Skyrim Special Edition"\n}\n')
    assert steam.find_game_dir(tmp_path) == apps / "common" / "Skyrim Special Edition"


def test_find_game_dir_override(tmp_path: Path):
    assert steam.find_game_dir(tmp_path, tmp_path / "x") == (tmp_path / "x").resolve()
