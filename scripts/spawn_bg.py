"""在后台启动一个进程，把 PID 打给调用方。

为什么需要这个：本机环境里同时存在 `NO_PROXY`/`no_proxy`、`HTTPS_PROXY`/`https_proxy`
这样只差大小写的变量，PowerShell 的 `Start-Process` 在复制环境字典时会抛
「已添加项。字典中的关键字…」，导致脚本没法起子进程。Python 的 `subprocess`
对这种情况不敏感，所以由它代劳。

用法：
    python scripts/spawn_bg.py --cwd server --out .tmp/x.log --err .tmp/x.err.log \
        --env SHEDGUARD_PORT=8010 -- .venv/Scripts/python.exe -m shedguard_server

输出（stdout 最后一行）：子进程 PID。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--cwd", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--err", required=True)
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv[1:])

    command = [item for item in args.command if item != "--"]
    if not command:
        print("缺少要启动的命令", file=sys.stderr)
        return 2

    env = dict(os.environ)
    for pair in args.env:
        key, sep, value = pair.partition("=")
        if not sep:
            print(f"--env 需要 K=V 形式，收到 {pair}", file=sys.stderr)
            return 2
        env[key] = value

    out_path = Path(args.out)
    err_path = Path(args.err)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    err_path.parent.mkdir(parents=True, exist_ok=True)

    out_handle = out_path.open("wb")
    err_handle = err_path.open("wb")
    process = subprocess.Popen(  # noqa: S603 - 命令由本仓库脚本给出
        command,
        cwd=args.cwd or None,
        env=env,
        stdout=out_handle,
        stderr=err_handle,
        stdin=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    print(process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
