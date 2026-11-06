#!/usr/bin/env python3
"""校验部署产物（super.raw.img.zst）和分区布局；可选校验构建输入。"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPER_SIZE = 12 * 1024**3
PART_SIZES = {
    "system_a": 1800 * 1024**2,
    "system_ext_a": 1500 * 1024**2,
    "product_a": 8200 * 1024**2,
    "vendor_a": 384 * 1024**2,
}
INPUT_SHA256 = {
    "input/crdroid-vendor.img": "a4c84743379ebce2695bd021dbaefde8526b68af418c3506641d6e50c6e11b80",
    "input/boot.rc2.img": "f60c65d2fdd03b601ba1819efebdab165b51bbc630995131f350b35fa873e603",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024**2), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_artifact(directory: Path) -> None:
    sums = directory / "SHA256SUMS"
    if not sums.is_file():
        raise SystemExit(f"缺少 {sums}")
    rows = []
    for line in sums.read_text().splitlines():
        words = line.split(maxsplit=1)
        if len(words) == 2:
            rows.append((words[0].lower(), words[1].lstrip("*")))
    if len(rows) != 1:
        raise SystemExit("SHA256SUMS 应只包含一行 super.raw.img.zst")
    expected, name = rows[0]
    image = directory / name
    if not image.is_file():
        raise SystemExit(f"缺少镜像：{image}")
    if image.stat().st_size < 6 * 1024**3:
        raise SystemExit(f"镜像体积异常：{image.stat().st_size} 字节")
    actual = sha256(image)
    if actual != expected:
        raise SystemExit(f"校验失败：期望 {expected}，实际 {actual}")
    print(f"镜像 SHA-256 通过：{name}")

    layout_file = ROOT / "reports" / "super-layout.json"
    if layout_file.is_file():
        layout = json.loads(layout_file.read_text())
        assert layout["super_size"] == SUPER_SIZE, "super 必须是 12 GiB"
        assert layout["metadata_max_size"] == 65536, "metadata 必须是 64 KiB"
        assert layout["metadata_slots"] == 3, "metadata 必须是 3 槽"
        assert layout["header_version"] == "10.2", "liblp 必须是 10.2"
        parts = {p["name"]: p for p in layout["partitions"]}
        assert set(parts) == set(PART_SIZES), f"分区集合不符：{sorted(parts)}"
        for key, size in PART_SIZES.items():
            assert parts[key]["size"] == size, f"{key} 大小不符：{parts[key]['size']}"
        print("分区布局通过：12 GiB / liblp 10.2 / 64 KiB metadata / 3 槽")


def verify_inputs() -> None:
    for rel, expected in INPUT_SHA256.items():
        path = ROOT / rel
        if not path.is_file():
            raise SystemExit(f"缺少输入：{rel}")
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"{rel} SHA-256 不匹配：{actual}")
        print(f"输入 SHA-256 通过：{rel}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=ROOT / "artifact")
    parser.add_argument("--check-inputs", action="store_true")
    args = parser.parse_args()
    if args.check_inputs:
        verify_inputs()
    verify_artifact(args.artifact.resolve())


if __name__ == "__main__":
    main()
