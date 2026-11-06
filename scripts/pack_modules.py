#!/usr/bin/env python3
"""把 modules/ 下的每个 KernelSU/Magisk 模块打成可刷入 zip。"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "modules"
OUTPUT = ROOT / "artifact" / "modules"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def build(module: Path) -> Path:
    prop = module / "module.prop"
    if not prop.is_file():
        raise SystemExit(f"模块缺少 module.prop：{module}")
    module_id = next(
        line.split("=", 1)[1].strip()
        for line in prop.read_text(encoding="utf-8").splitlines()
        if line.startswith("id=")
    )
    target = OUTPUT / f"{module_id}.zip"
    files = [prop] + sorted(p for p in module.rglob("*")
                            if p.is_file() and p != prop)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            info = zipfile.ZipInfo(str(path.relative_to(module)).replace("\\", "/"), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())
    print(f"{module.name} -> {target.relative_to(ROOT)}")
    return target


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for module in sorted(p for p in MODULES.iterdir() if p.is_dir()):
        build(module)
    print(f"模块包已生成：{OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
