# tools/ 生成器与运维脚本

> 纪律（plan/05 §二/§三）：数据资产由**生成器**产出，**禁手改**产物；生成器必须确定性
> （固定 seed → 任意机器逐字节一致）。

| 脚本 | 作用 | 里程碑 |
|---|---|---|
| `gen_rulesets.py` | 从确定性模板生成 `data/rules/<doc>/<ver>.json` 冻结规则库，回填 `registry.json` 的 sha256 | M1 |
| `gen_mapping.py` | 生成/校验 `data/mapping/national-fields.json` | M1 |
| `gen_samples.py` | 构造合成样本 + 植入真值（`labelcheck.rng` 确定性 RNG） | M1 |
| `make_demo_assets.py` | 生成演示截图/GIF（需 PySide6，惰性导入） | M5 |
| `verify_package.py` | 冻结态包验收（中立目录跑 `--selftest`） | M5 |
| `audit_desensitize.py` | 脱敏四步审计（发布门） | M6 |

M0 尚未实现任何生成器；数据骨架为手工录入的 `pending` 占位条目（见 `data/README.md`）。
