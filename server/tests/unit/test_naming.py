"""路径与哈希生成：全部由服务端决定，不接受客户端输入。"""

from datetime import date, datetime

from shedguard_server.domain.naming import build_filename, build_rel_path, sha256_hex

KNOWN_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"


def test_sha256_of_known_content() -> None:
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_filename_uses_local_time_and_sha_prefix() -> None:
    filename = build_filename(datetime(2026, 11, 2, 14, 30, 5), KNOWN_SHA, "jpg")

    assert filename == "143005_a1b2c3d4.jpg"


def test_filename_pads_single_digit_components() -> None:
    filename = build_filename(datetime(2026, 11, 2, 9, 5, 3), KNOWN_SHA, "png")

    assert filename == "090503_a1b2c3d4.png"


def test_rel_path_layout() -> None:
    rel_path = build_rel_path(date(2026, 11, 2), "eye-01", "143005_a1b2c3d4.jpg")

    assert rel_path == "images/2026-11-02/eye-01/143005_a1b2c3d4.jpg"