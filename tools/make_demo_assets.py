# -*- coding: utf-8 -*-
"""演示素材生成器（M5）：离屏渲染 GUI 页签 → ``docs/demo/`` 截图 + GIF。

用法（仓库根；需 ``gui`` extra）：

    py -3.8 tools/make_demo_assets.py            # 生成全部截图 + GIF
    py -3.8 tools/make_demo_assets.py --check    # 只校验素材存在

**为什么离屏渲染**：无显示环境（CI / 远程）也能产出素材——``QT_QPA_PLATFORM=offscreen``
下构造真实控件、驱动真实引擎、``grab()`` 真实像素。素材因此**必然反映当前代码**，
不会出现"截图是旧版界面"的漂移。

**确定性说明**：截图字节受字体渲染影响（不同机器可能不同），故素材**不做**位级守门；
``--check`` 只断言"文件存在且非空"。GIF 由 Pillow 组装（可选依赖，缺则跳过 GIF）。

**数据来源**：素材用**仓库随附数据**（``data/samples`` 与规则库）演示，全部为合成内容。
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 必须在导入 PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DEMO_DIR = REPO_ROOT / "docs" / "demo"

#: 素材清单：``文件名 → 说明``（README 引用这些文件名）
SHOTS = {
    "tab-single-check.png": "单件核验页签（合规样例）",
    "tab-single-violation.png": "单件核验页签（检出违规）",
    "tab-batch-scan.png": "批量扫描页签（逐件结果）",
    "tab-diff.png": "两轮对账页签（新增违规/已修复/持续违规）",
    "tab-benchmark.png": "基准指标页签（三类基准 + 达标线）",
    "tab-rules.png": "规则库与依据页签（依据清单 + 规则条目）",
    "demo.gif": "演示动图（页签切换）",
}


def _require_gui():
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except ImportError as exc:  # pragma: no cover - 环境相关
        sys.stderr.write(
            "缺少 GUI 依赖（{0}）。请先安装：pip install -e \".[gui]\"\n".format(exc))
        return False
    return True


def _grab(widget, path, width=1180, height=760):
    """把控件渲染为 PNG（离屏；先 resize 保证尺寸稳定）。"""
    widget.resize(width, height)
    widget.show()
    # 让布局完成一次（离屏下 processEvents 足够）
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    pixmap = widget.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = pixmap.save(str(path), "PNG")
    if not ok:
        raise RuntimeError("截图保存失败：{0}".format(path))
    return path


def generate(data_dir=None, demo_dir=None):
    """生成全部截图（返回写出路径列表）。"""
    from PySide6.QtWidgets import QApplication

    from labelcheck.gui.main_window import MainWindow

    data_dir = Path(data_dir) if data_dir else REPO_ROOT / "data"
    demo_dir = Path(demo_dir) if demo_dir else DEMO_DIR

    app = QApplication.instance() or QApplication([])
    window = MainWindow(data_dir=data_dir)
    by_title = {tab.TITLE: tab for tab in window.tab_objects}
    written = []

    # 单件核验（合规）
    single = by_title["单件核验"]
    single.path_edit.setText(str(data_dir / "samples" / "card-text-basic.json"))
    single.check_path(str(data_dir / "samples" / "card-text-basic.json"))
    window.tabs.setCurrentWidget(single.widget)
    written.append(_grab(window.window, demo_dir / "tab-single-check.png"))

    # 单件核验（违规）
    stripped = data_dir / "samples" / "card-image-metadata-stripped.json"
    if stripped.is_file():
        single.check_path(str(stripped))
        written.append(_grab(window.window, demo_dir / "tab-single-violation.png"))

    # 批量扫描（逐件结果）
    batch = by_title["批量扫描"]
    samples = data_dir / "samples"
    batch.target_edit.setText(str(samples))
    first = batch.scan(str(samples))
    window.tabs.setCurrentWidget(batch.widget)
    written.append(_grab(window.window, demo_dir / "tab-batch-scan.png"))

    # 两轮对账（独立页签：两份结果 JSON）
    diff_tab = by_title["两轮对账"]
    if first is not None:
        import json
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="labelcheck-demo-"))
        round1 = tmp / "round1.json"
        round1.write_text(
            json.dumps(first.result.to_dict(), ensure_ascii=False), encoding="utf-8")
        diff_tab.previous_edit.setText(str(round1))
        diff_tab.current_edit.setText(str(round1))
        diff_tab.diff(str(round1), str(round1))
    window.tabs.setCurrentWidget(diff_tab.widget)
    written.append(_grab(window.window, demo_dir / "tab-diff.png"))

    # 基准指标
    bench = by_title["基准指标"]
    bench.run(None)
    window.tabs.setCurrentWidget(bench.widget)
    written.append(_grab(window.window, demo_dir / "tab-benchmark.png"))

    # 规则库与依据
    rules = by_title["规则库与依据"]
    rules.refresh()
    window.tabs.setCurrentWidget(rules.widget)
    written.append(_grab(window.window, demo_dir / "tab-rules.png"))

    return written


def make_gif(demo_dir=None):
    """把已生成的截图组装成演示 GIF（需 Pillow；缺则跳过并返回 None）。"""
    demo_dir = Path(demo_dir) if demo_dir else DEMO_DIR
    try:
        from PIL import Image
    except ImportError:
        sys.stderr.write("未安装 Pillow，跳过 GIF 生成（截图已产出）\n")
        return None

    frames = []
    for name in ("tab-single-check.png", "tab-single-violation.png",
                 "tab-batch-scan.png", "tab-diff.png", "tab-benchmark.png", "tab-rules.png"):
        path = demo_dir / name
        if not path.is_file():
            continue
        image = Image.open(str(path)).convert("RGB")
        image.thumbnail((900, 620))
        frames.append(image)
    if not frames:
        return None

    out = demo_dir / "demo.gif"
    # 固定时长与循环次数 → GIF 本身可复现（像素仍取决于字体渲染）
    frames[0].save(
        str(out), save_all=True, append_images=frames[1:], duration=1600, loop=0)
    return out


def check(demo_dir=None):
    """校验素材存在且非空；返回缺失清单。"""
    demo_dir = Path(demo_dir) if demo_dir else DEMO_DIR
    missing = []
    for name in SHOTS:
        path = demo_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
    return missing


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 README 演示素材（截图 + GIF）")
    parser.add_argument("--check", action="store_true", help="只校验素材存在，不生成")
    parser.add_argument("--no-gif", action="store_true", help="不生成 GIF（只出截图）")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认仓库 data/）")
    parser.add_argument("--out", default=None, help="输出目录（默认 docs/demo/）")
    args = parser.parse_args(argv)

    if args.check:
        missing = check(args.out)
        if missing:
            sys.stderr.write("缺少演示素材：{0}\n".format("、".join(missing)))
            return 1
        sys.stdout.write("演示素材齐全（{0} 个）。\n".format(len(SHOTS)))
        return 0

    if not _require_gui():
        return 3

    written = generate(data_dir=args.data_dir, demo_dir=args.out)
    for path in written:
        sys.stdout.write("已写出：{0}\n".format(path))
    if not args.no_gif:
        gif = make_gif(args.out)
        if gif is not None:
            sys.stdout.write("已写出：{0}\n".format(gif))
    return 0


if __name__ == "__main__":
    sys.exit(main())
