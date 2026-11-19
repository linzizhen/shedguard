"""下载 cloudflared（Windows amd64）。

为什么不用 PowerShell 的 Invoke-WebRequest：本机 schannel 证书链有问题，
`Invoke-WebRequest` 与 `curl.exe` 都会在 TLS 握手阶段失败，而 Python 的 urllib 正常。

用法：
    .venv\\Scripts\\python.exe scripts\\fetch_cloudflared.py .tmp\\cloudflared.exe
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
CHUNK = 1024 * 256


def download(dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    written = 0
    with urllib.request.urlopen(URL, timeout=60) as response, partial.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        while True:
            chunk = response.read(CHUNK)
            if not chunk:
                break
            handle.write(chunk)
            written += len(chunk)
            if total:
                percent = written * 100 // total
                print(f"\r已下载 {written // 1024} KB / {total // 1024} KB（{percent}%）", end="")
    print()
    if written == 0:
        partial.unlink(missing_ok=True)
        raise RuntimeError("下载到 0 字节，链接可能已失效")
    partial.replace(dest)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：fetch_cloudflared.py <目标路径>", file=sys.stderr)
        return 2
    dest = Path(argv[1])
    print(f"从 {URL} 下载 cloudflared …")
    try:
        size = download(dest)
    except Exception as exc:  # noqa: BLE001 - 网络异常原样告诉用户
        print(f"下载失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "可以手动下载后放到目标路径：\n"
            "  https://github.com/cloudflare/cloudflared/releases/latest/download/"
            "cloudflared-windows-amd64.exe",
            file=sys.stderr,
        )
        return 1
    print(f"完成：{dest}（{size // 1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
