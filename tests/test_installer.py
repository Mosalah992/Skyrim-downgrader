from pathlib import Path

from skyrim_downgrader import installer


def test_plan_and_copy_small_depot_tree(tmp_path: Path):
    depot = tmp_path / "depot"
    game = tmp_path / "game"
    (depot / "Data").mkdir(parents=True)
    (depot / "SkyrimSE.exe").write_bytes(b"replacement exe")
    (depot / "Data" / "small-file.txt").write_text("new data", encoding="utf-8")
    game.mkdir()
    (game / "SkyrimSE.exe").write_bytes(b"old exe")

    items = installer.plan_copy(depot, game)
    assert {item.dst.relative_to(game) for item in items} == {
        Path("SkyrimSE.exe"),
        Path("Data") / "small-file.txt",
    }

    copied = list(installer.copy_items(items))
    assert copied == items
    assert (game / "SkyrimSE.exe").read_bytes() == b"replacement exe"
    assert (game / "Data" / "small-file.txt").read_text(encoding="utf-8") == "new data"

