"""Static file resolution for the single-origin production build.

The one that matters is the traversal case: the path arrives from the URL, so
an unchecked join would serve the whole container to anyone who asked nicely.
"""

from pathlib import Path

from app.main import resolve_static_file


def test_missing_build_resolves_to_nothing(tmp_path: Path):
    assert resolve_static_file("/", tmp_path) is None


def test_client_route_falls_back_to_index(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html></html>")
    assert resolve_static_file("messages/abc", tmp_path) == tmp_path / "index.html"


def test_real_file_wins_over_index(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html></html>")
    asset = tmp_path / "assets" / "index-abc123.js"
    asset.parent.mkdir()
    asset.write_text("console.log(1)")
    assert resolve_static_file("assets/index-abc123.js", tmp_path) == asset


def test_traversal_is_refused(tmp_path: Path):
    secret = tmp_path / "..secret"
    secret.mkdir()
    (secret / "id_rsa").write_text("nope")
    (tmp_path / "index.html").write_text("<html></html>")
    assert resolve_static_file("../secret/id_rsa", tmp_path) is None
