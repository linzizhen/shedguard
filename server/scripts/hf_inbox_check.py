"""收件箱自检：一条命令确认 HuggingFace 收件箱配好了、而且真的能写。

P29 的代码早就写完了，缺的只是「收件箱地址 + token」。手工验证要过一遍 App、
灌图、等后台任务、再回网页看文件，中间任何一步出错都很难判断是 token 没权限、
仓库填错、还是网络根本不通。这个脚本把链路拆成 6 步逐条打印，失败就直接说
下一步该改哪里。

用法（在 `server` 目录下执行）：

    ..\\.venv\\Scripts\\python.exe scripts\\hf_inbox_check.py
    ..\\.venv\\Scripts\\python.exe scripts\\hf_inbox_check.py --create
    ..\\.venv\\Scripts\\python.exe scripts\\hf_inbox_check.py --repo 账号/仓库

`--create` 会在仓库不存在时建一个**私有** dataset 仓库。
脚本只写一个 `_probe/...` 探针文件，结束时自动删掉（`--keep` 可保留便于肉眼确认）。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 脚本不经 `pip install -e` 也能跑：把 src 放进导入路径。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from huggingface_hub import CommitOperationAdd, HfApi
from huggingface_hub.utils import HfHubHTTPError

from shedguard_server.config import Settings
from shedguard_server.domain.contribution import (
    UploadItem,
    meta_payload,
    remote_paths,
)
from shedguard_server.infra.contribution_upload import (
    DEFAULT_REPO_TYPE,
    build_contribution_uploader,
)

PROBE_OWNER = "_probe"

HINT_NO_TOKEN = (
    "去 https://huggingface.co/settings/tokens 建一个 fine-grained token"
    "（只勾收件箱这一个仓库、只给 Write），填进 server/.env，"
    "不要贴到聊天或截图里。"
)
HINT_NO_REPO = (
    "加 --create 让脚本建一个私有 dataset，或去 "
    "https://huggingface.co/new-dataset 手工建（Visibility 必须选 Private）。"
)
HINT_NO_PERMS = "token 的 Repository permissions 里要勾上这一个仓库并给 Write。"
HINT_NETWORK = (
    "先确认这台机器能打开 huggingface.co"
    "（大陆网络常年不通，必要时用代理）。"
)
HINT_WRITE = (
    "最常见是 token 只有 Read 没有 Write；"
    "其次是仓库属于别的账号而 token 没跨账号权限。"
)
HINT_CACHE = (
    "若报错里出现「拒绝访问」或 xet logs，是 HuggingFace 的本地缓存目录不可写，"
    "把环境变量 HF_HOME 指到一个可写目录（例如 HF_HOME=D:\\temp\\hf-home）再跑。"
)


def mask(token: str) -> str:
    """只露前缀与长度，避免 token 出现在日志或截图里。"""
    if not token:
        return "（空）"
    return f"{token[:3]}***（长度 {len(token)}）"


def say(step: str, message: str) -> None:
    print(f"[{step}] {message}")


def fail(step: str, message: str, hint: str) -> int:
    print(f"[{step}] 失败：{message}")
    print(f"       → {hint}")
    return 1


def explain_store_failure(api: HfApi, repo_id: str) -> str:
    """上传器会把异常吞掉只留 `failed` 路径；这里重试单文件，把真正的错误抓出来。"""
    path = f"{PROBE_OWNER}/_diag.txt"
    try:
        api.create_commit(
            repo_id,
            [CommitOperationAdd(path_in_repo=path, path_or_fileobj=b"diag\n")],
            commit_message="diagnose contribution inbox",
            repo_type=DEFAULT_REPO_TYPE,
        )
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    print(f"       诊断文件 {path} 反而写成功了，正在删掉")
    try:
        api.delete_file(
            path,
            repo_id,
            commit_message="remove diagnose file",
            repo_type=DEFAULT_REPO_TYPE,
        )
    except Exception as cleanup_exc:
        print(f"       {path} 删不掉，请到网页手工删除：{cleanup_exc}")
    return "重试单个文件反而成功了，说明是瞬时故障，再跑一次脚本即可"


def whoami_name(api: HfApi) -> str:
    info: Any = api.whoami()
    if isinstance(info, dict):
        return str(info.get("name") or info.get("user") or "未知")
    return str(getattr(info, "name", "未知"))


def read_config(args: argparse.Namespace) -> tuple[str, str, bool] | int:
    """返回 (repo_id, token, enabled)；出错时直接返回退出码。"""
    settings = Settings()
    repo_id = (args.repo or settings.contribution_upload_repo or "").strip()
    token = (args.token or settings.contribution_upload_token or "").strip()
    enabled = settings.contribution_upload_enabled

    say("1/6", "读配置")
    print(f"       启用开关 = {enabled}")
    print(f"       收件箱   = {repo_id or '（空）'}")
    print(f"       Token    = {mask(token)}")

    if not token:
        return fail("1/6", "没有 token", HINT_NO_TOKEN)
    if not repo_id or "/" not in repo_id:
        return fail(
            "1/6",
            "收件箱地址不对",
            "要写成「账号名/仓库名」，例如 myname/shedguard-contributions。",
        )
    if not enabled:
        print("       注意：开关是关的。现在只有本脚本会写，服务端不会自动上传。")
    return repo_id, token, enabled


def check_account(api: HfApi) -> str | int:
    say("2/6", "验证 token")
    try:
        return whoami_name(api)
    except HfHubHTTPError as exc:
        status = exc.response.status_code
        if status == 403:
            # fine-grained token 常常只给仓库权限、不给「读账号信息」，这不算错。
            print("       token 有效，但没给「读账号信息」权限（fine-grained 常态），跳过")
            return "（未授权读取）"
        return fail(
            "2/6",
            f"token 被拒（{status}）",
            "重新建一个 token，注意复制完整（hf_ 开头）。",
        )
    except Exception as exc:  # 网络问题要给得出人话
        return fail("2/6", f"连不上 huggingface.co：{exc}", HINT_NETWORK)


def check_repo(api: HfApi, repo_id: str, *, create: bool, account: str = "") -> Any:
    """确保仓库存在；返回 info，出错时返回退出码（int）。"""
    say("3/6", "检查仓库")
    try:
        return api.repo_info(repo_id, repo_type=DEFAULT_REPO_TYPE)
    except HfHubHTTPError as exc:
        status = exc.response.status_code
        if status != 404:
            if status in (401, 403):
                return fail("3/6", f"没有这个仓库的权限（{status}）", HINT_NO_PERMS)
            return fail(
                "3/6",
                f"查仓库出错（{status}）",
                "把完整报错留档，先确认仓库名拼写。",
            )
    # 404：先怀疑账号名写错，这种情况千万别顺手建一个新仓库出来。
    owner, _, name = repo_id.partition("/")
    if account and not account.startswith("（") and owner.lower() != account.lower():
        return fail(
            "3/6",
            f"仓库不存在：{repo_id}",
            f"你账号其实是 {account}，把 .env 里的地址改成 "
            f"{account}/{name} 再跑一次。",
        )
    if not create:
        return fail("3/6", f"仓库不存在：{repo_id}", HINT_NO_REPO)
    try:
        api.create_repo(
            repo_id, repo_type=DEFAULT_REPO_TYPE, private=True, exist_ok=True
        )
    except Exception as create_exc:
        return fail(
            "3/6",
            f"建仓库失败：{create_exc}",
            "确认 token 有创建仓库的权限（fine-grained 需要勾 Repo 的 create）。",
        )
    return api.repo_info(repo_id, repo_type=DEFAULT_REPO_TYPE)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 HuggingFace 收件箱是否可用")
    parser.add_argument("--repo", default=None, help="覆盖收件箱仓库地址")
    parser.add_argument("--token", default=None, help="覆盖 token")
    parser.add_argument("--create", action="store_true", help="仓库不存在时建私有 dataset")
    parser.add_argument("--keep", action="store_true", help="保留探针文件，不自动删除")
    args = parser.parse_args()

    config = read_config(args)
    if isinstance(config, int):
        return config
    repo_id, token, enabled = config

    api = HfApi(token=token)

    account = check_account(api)
    if isinstance(account, int):
        return account
    print(f"       账号 = {account}")

    info = check_repo(api, repo_id, create=args.create, account=account)
    if isinstance(info, int):
        return info
    private = bool(getattr(info, "private", False))
    kind = "私有" if private else "公开"
    print(f"       仓库 = {repo_id}（dataset，{kind}）")
    if not private:
        print("       警告：仓库是公开的。用户分享的守宫照片会被人看到，请立刻改成 Private。")

    # —— 4. 上传探针（走服务端真实上传器）————————————————————
    say("4/6", "上传探针（走服务端真实上传器）")
    uploader = build_contribution_uploader(enabled=True, repo_id=repo_id, token=token)
    if uploader.name == "noop" or not uploader.configured:
        return fail("4/6", "上传器没配置起来", "检查 repo 与 token 是否都填了。")

    stamp = datetime.now().isoformat()
    digest = hashlib.sha256(f"probe-{stamp}".encode()).hexdigest()
    today = date.today()
    paths = remote_paths(
        owner_hash=PROBE_OWNER, local_date=today, digest=digest, include_full=False
    )
    meta = meta_payload(
        digest=digest,
        state="probe",
        confidence=None,
        local_date=today,
        include_full=False,
        width=0,
        height=0,
    )
    items = (
        UploadItem(remote_path=paths.crop, payload=b"shedguard inbox probe\n"),
        UploadItem(remote_path=paths.meta, payload=b"", meta=meta),
    )
    result = uploader.store(items)
    if result.uploaded == 0:
        reason = explain_store_failure(api, repo_id)
        print(f"       真实错误：{reason}")
        return fail(
            "4/6",
            f"写入失败，失败路径 {list(result.failed)}",
            f"{HINT_WRITE} {HINT_CACHE}",
        )
    print(f"       已写入 {result.uploaded} 个文件（{paths.crop}）")

    # —— 5. 读回确认 ——————————————————————————————————————————
    say("5/6", "读回确认")
    try:
        files = set(api.list_repo_files(repo_id, repo_type=DEFAULT_REPO_TYPE))
    except Exception as exc:
        return fail(
            "5/6",
            f"列文件失败：{exc}",
            f"先别删探针，去网页 https://huggingface.co/datasets/{repo_id} 看看。",
        )
    missing = [item.remote_path for item in items if item.remote_path not in files]
    if missing:
        return fail(
            "5/6",
            f"写进去了但列不出来：{missing}",
            "刷新网页确认；若确实没有，把这一步的完整输出留档。",
        )
    print(f"       远端能看到 {len(items)} 个探针文件")

    # —— 6. 删掉探针 ——————————————————————————————————————————
    say("6/6", "清理探针")
    if args.keep:
        print(f"       --keep 已指定，保留 {paths.crop} 供肉眼确认")
    else:
        uploader.delete([item.remote_path for item in items])
        print("       已撤回探针")

    print()
    print("结论：收件箱可用。")
    if not enabled:
        print("剩下只差把 server/.env 里的 SHEDGUARD_CONTRIBUTION_UPLOAD_ENABLED")
        print("改成 true，然后重启服务端。")
    else:
        print("下一步：重启服务端 → App 打开「分享照片」开关 → 喂一张图验证整条链路。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())