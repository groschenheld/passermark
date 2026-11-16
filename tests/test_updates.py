# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
"""Update function (pdfdruck/updates.py): versions, release list, channel, installation kind, checked download,
swapping the AppImage – without network (GitHub answers are simulated)."""

import hashlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pdfdruck import updates as U  # noqa: E402


def _gh(*rels):
    """A GitHub release list as JSON bytes."""
    out = []
    for tag, pre, names in rels:
        out.append(
            {
                "tag_name": tag,
                "prerelease": pre,
                "draft": False,
                "html_url": f"https://github.com/x/releases/{tag}",
                "body": f"Neu in {tag}",
                "assets": [{"name": n, "browser_download_url": f"https://dl/{tag}/{n}"} for n in names],
            }
        )
    return json.dumps(out).encode()


def test_versions():
    assert U.is_newer("v1.19.0", "1.18.38") and U.is_newer("1.18.39", "1.18.38")
    assert not U.is_newer("v1.18.38", "1.18.38") and not U.is_newer("1.9.99", "1.18.0")  # numeric, not text
    assert U.is_newer("1.19.0", "1.19.0-test2") and not U.is_newer("1.19.0-test1", "1.19.0")
    assert U.parse_version("nightly") is None and not U.is_newer("nightly", "1.0.0")


def test_release_list_and_channel():
    data = json.loads(
        _gh(
            ("v1.20.0-test1", True, []),
            ("v1.19.0", False, ["a.AppImage"]),
            ("v1.18.0", False, []),
            ("nightly", False, []),
        )
    )
    data.append({"tag_name": "v9.0.0", "draft": True})
    rels = U.releases_from_json(data)
    assert [r.tag for r in rels] == ["v1.20.0-test1", "v1.19.0", "v1.18.0"]  # drafts and non-versions dropped
    assert U.newest(rels, "stable", "1.18.38").version == "1.19.0"
    assert U.newest(rels, "test", "1.18.38").version == "1.20.0-test1"
    assert U.newest(rels, "stable", "1.19.0") is None  # up to date
    # a tag with a suffix only goes to the test channel, even if not marked as pre-release (typo "v1.51.1-fix")
    typo = U.releases_from_json(json.loads(_gh(("v1.51.1-fix", False, []), ("v1.19.0", False, []))))
    assert U.newest(typo, "stable", "1.18.38").version == "1.19.0"
    assert U.newest(typo, "test", "1.18.38").version == "1.51.1-fix"
    assert U.newest(U.releases_from_json("kaputt"), "stable", "1.0.0") is None
    r = U.check("stable", fetch=lambda url: _gh(("v99.0.0", False, [])))  # always newer than the running version
    assert r.version == "99.0.0" and r.notes == "Neu in v99.0.0"
    try:
        U.check("stable", fetch=lambda url: b"<html>")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_settings_and_due():
    assert U.settings({}) == {"enabled": True, "channel": "stable"}
    assert U.settings({"updates": {"enabled": False, "channel": "test"}}) == {"enabled": False, "channel": "test"}
    assert U.settings({"updates": {"channel": "beta"}})["channel"] == "stable"
    now = 1_000_000.0
    assert U.due(None, now) and U.due(now - U.CHECK_EVERY, now) and not U.due(now - 60, now)
    assert U.due(now + 3600, now)  # clock set back: check again


def test_install_kind_and_asset():
    d = tempfile.mkdtemp()
    app = os.path.join(d, "Passermark.AppImage")
    open(app, "w").close()
    assert U.install_kind({"APPIMAGE": app}, False, "linux", "/x/pdfdruck/updates.py") == "appimage"
    assert U.install_kind({}, True, "win32", "C:/x/updates.py") == "windows"
    assert U.install_kind({}, False, "linux", U.SOURCE_LIB + "/pdfdruck/updates.py") == "source"
    assert U.install_kind({}, False, "linux", "/home/x/gh/pdfdruck/updates.py") == "other"
    rel = U.releases_from_json(
        json.loads(
            _gh(
                (
                    "v1.19.0",
                    False,
                    [
                        "Passermark-1.19.0-x86_64.AppImage",
                        "Passermark-1.19.0-x86_64.AppImage.sha256",
                        "Passermark-1.19.0-Setup.exe",
                        "passermark-src-1.19.0.tar.gz",
                        "passermark-src-1.19.0.tar.gz.sha256",
                    ],
                )
            )
        )
    )[0]
    assert U.asset_name(rel, "appimage") == "Passermark-1.19.0-x86_64.AppImage"
    assert U.asset_name(rel, "source") == "passermark-src-1.19.0.tar.gz" and U.asset_name(rel, "other") is None
    assert U.can_apply(rel, "appimage") and U.can_apply(rel, "source")
    assert not U.can_apply(rel, "windows")  # setup without checksum: never installed
    assert U.why_not(rel, "appimage") == "" and U.why_not(rel, "windows") == "no_checksum"
    assert U.why_not(rel, "other") == "checkout"
    bare = U.releases_from_json(json.loads(_gh(("v1.19.4", False, []))))[0]
    assert U.why_not(bare, "source") == "no_file"  # tag pushed, build not attached (the 1.19.4 case)


def test_checksum_text():
    h = "a" * 64
    assert U.expected_sha256(f"{h}  datei.tar.gz\n", "datei.tar.gz") == h
    assert U.expected_sha256(f"{h} *datei.tar.gz", "datei.tar.gz") == h
    assert U.expected_sha256(h.upper(), "egal") == h
    assert U.expected_sha256(f"{h}  andere.tar.gz", "datei.tar.gz") is None
    assert U.expected_sha256("kein hash", "datei") is None


class _Resp(io.BytesIO):
    headers = {"Content-Length": "0"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def test_download_checked():
    payload = b"neue Version" * 1000
    good = hashlib.sha256(payload).hexdigest()
    name = "Passermark-1.19.0-x86_64.AppImage"
    rel = U.Release("1.19.0", "v1.19.0", "p", assets={name: "https://dl/f", name + ".sha256": "https://dl/f.sha256"})
    old_get = U._get
    try:
        for published, ok in ((f"{good}  {name}", True), ("b" * 64 + f"  {name}", False)):
            U._get = lambda url, published=published: published.encode()
            seen = []
            try:
                path = U.download(
                    rel,
                    "appimage",
                    tempfile.mkdtemp(),
                    lambda d, t: seen.append(d),
                    lambda req, timeout: _Resp(payload),
                )
                assert ok and open(path, "rb").read() == payload and seen[-1] == len(payload)
            except U.UpdateError as e:
                assert not ok and "Prüfsumme" in str(e), e
        try:
            U.download(U.Release("1.19.0", "v1.19.0", "p", assets={name: "u"}), "appimage")
            raise AssertionError("expected UpdateError")
        except U.UpdateError:
            pass
    finally:
        U._get = old_get


def test_replace_appimage_and_commands():
    d = tempfile.mkdtemp()
    target, new = os.path.join(d, "Passermark.AppImage"), os.path.join(d, "neu")
    with open(target, "w") as f:
        f.write("alt")
    with open(new, "w") as f:
        f.write("neu")
    assert U.replace_appimage(new, target) == target and open(target).read() == "neu"
    assert os.access(target, os.X_OK) and not [n for n in os.listdir(d) if n.endswith(".update")]
    cmd = U.windows_setup_command("C:/t/Setup.exe")
    assert "/VERYSILENT" in cmd and "/AUTOUPDATE" in cmd
    rel = U.Release("1.19.0", "v1.19.0", "p")
    assert U.source_update_command(rel, "/tmp/p.tar.gz")[:4] == [
        "pkexec",
        "/usr/libexec/passermark-admin",
        "update",
        "1.19.0",
    ]


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("ok", k)
