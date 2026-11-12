"""设备模拟器：不用开发板，也能把「上传 → 检测 → 蜕皮提醒」整条链路跑一遍。

两种用法：

1) 纯接口自测（自己建账号/宠物/设备，验证服务端流水线）：
   python server/scripts/device_sim.py --pet-name 测试守宫

2) 只上传一张图（App 里已经绑定好设备与宠物时用，提醒会出现在 App 里）：
   python server/scripts/device_sim.py

默认找一张测试集里的蜕皮照片；也可用 --image 指定任意 jpg。
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_IMAGE = Path("ml/datasets/gecko-state-v2/test/shedding")


def pick_image(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            sys.exit(f"图片不存在: {path}")
        return path
    candidates = sorted(DEFAULT_IMAGE.glob("*.jpg"))
    if not candidates:
        sys.exit(f"默认测试图目录为空: {DEFAULT_IMAGE}，请用 --image 指定一张蜕皮照片")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="模拟 ESP32 设备上传一张照片")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--device-id", default=None, help="设备编号；自测模式默认随机")
    parser.add_argument("--image", default=None, help="要上传的 jpg 路径")
    parser.add_argument("--pet-name", default=None, help="给定时自建账号+宠物+设备（纯接口自测）")
    parser.add_argument("--device-token", default="", help="服务端设了 SHEDGUARD_DEVICE_TOKEN 时填")
    parser.add_argument("--wait", type=float, default=4.0, help="上传后等待后台处理的秒数")
    args = parser.parse_args()

    if args.device_id:
        device_id = args.device_id
    elif args.pet_name:
        # 同一设备同一天同一类型只会提醒一次；自测时每次换设备号才方便重复验证。
        device_id = "sim-" + datetime.now().strftime("%H%M%S")
    else:
        device_id = "gecko-eye-01"

    image = pick_image(args.image)
    base = args.base_url.rstrip("/")
    client = httpx.Client(base_url=base, timeout=30.0, trust_env=False)

    try:
        health = client.get("/healthz")
        print(f"[1/5] /healthz -> {health.status_code}")
        if health.status_code != 200:
            print("服务端没起来，先运行: python -m shedguard_server")
            return 1
    except httpx.HTTPError as exc:
        print(f"连不上 {base}: {exc}")
        return 1

    pet_id: str | None = None
    if args.pet_name:
        reg = client.post("/api/v1/users/anonymous")
        if reg.status_code != 201:
            print(f"[2/5] 建匿名账号失败 {reg.status_code}: {reg.text}")
            return 1
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        pet = client.post("/api/v1/pets", json={"name": args.pet_name}, headers=headers)
        if pet.status_code != 201:
            print(f"[2/5] 建宠物失败 {pet.status_code}: {pet.text}")
            return 1
        pet_id = pet.json()["id"]
        print(f"[2/5] 账号与宠物就绪 pet_id={pet_id}")
        dev = client.post(
            "/api/v1/devices",
            json={
                "expo_push_token": "ExponentPushToken[simulator-local-test]",
                "platform": "android",
                "device_id": device_id,
                "pet_id": pet_id,
            },
            headers=headers,
        )
        print(f"[3/5] 绑定设备 {device_id} -> {dev.status_code}")
    else:
        headers = {}
        print("[2/5] 跳过建账号（假定 App 已绑定设备与宠物）")
        print("[3/5] 跳过绑定设备")

    captured = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    upload_headers = {"X-Device-Id": device_id, "X-Captured-At": captured}
    if args.device_token:
        upload_headers["X-Device-Token"] = args.device_token
    with image.open("rb") as fh:
        res = client.post(
            "/api/v1/images",
            files={"file": (image.name, fh, "image/jpeg")},
            headers=upload_headers,
        )
    print(f"[4/5] 上传 {image.name} -> {res.status_code} {res.text[:120]}")
    if res.status_code not in (200, 201):
        return 1

    import time

    time.sleep(args.wait)
    query = {"device_id": device_id, "limit": "5"}
    if pet_id:
        query["pet_id"] = pet_id
    alerts = client.get("/api/v1/alerts", params=query, headers=headers)
    print(f"[5/5] 查询提醒 -> {alerts.status_code}")
    if alerts.status_code != 200:
        print(alerts.text)
        return 1
    items = alerts.json().get("items", [])
    if not items:
        print("      没有生成提醒。常见原因：")
        print("      - 这张图被判为非蜕皮（换一张蜕皮照片试试）")
        print("      - 同一设备同一天已经提醒过一次（自动去重；换 --device-id 或等明天）")
        print("      - 图片与之前完全相同，被去重而没有重新处理（换图或用 --image 指定）")
        return 2
    for item in items:
        print(
            f"      [OK] {item['kind']}  {item['local_date']}  state={item['state'] or '-'} "
            f"conf={item['confidence']}  push={item['push_status']}"
        )
    print("\n链路通了：上传 → 检测 → 判定 → 建提醒。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
