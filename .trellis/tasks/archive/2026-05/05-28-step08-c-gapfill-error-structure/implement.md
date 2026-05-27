# Implement — C: Gap-Fill Error Structure

## Execution checklist

- [ ] 创建 `ncei/code/20_step08_gapfill_error_structure.py`。
- [ ] 加载 5 个 expanded by-cell，过滤 `expanded_fill==True/False` 两个子集；行数 assert 333,915 / 2,398,774。
- [ ] retained RMSE vs strict-primary summary 对账（误差 < 0.01）。
- [ ] 6 个单维 group_by 聚合（pandas）。NaN 切片改为字面 `"<NA>"`。
- [ ] 计算 contribution_pct（per design.md 公式）。
- [ ] 拼接所有维度，按 contribution_pct 排序取 top-20。
- [ ] 写出 6 + 1 张 TSV + safety checks。
- [ ] 生成报告 markdown。
- [ ] 自验证：py_compile + check-only 干跑。
- [ ] 完整运行 + safety checks PASS。

## Validation commands

```bash
python -m py_compile ncei/code/20_step08_gapfill_error_structure.py

python ncei/code/20_step08_gapfill_error_structure.py --check-only

python ncei/code/20_step08_gapfill_error_structure.py \
  --run-label c_gapfill \
  --confirm-analyze --overwrite
```

## Review gates

| Gate | Condition |
|---|---|
| G-C-1 | gap-fill rows = 333,915 (per model) |
| G-C-2 | retained RMSE = strict RMSE (差 < 0.01) per model |
| G-C-3 | top-20 切片合计 ≥ 80% （否则 warning + 报告解释） |
| G-C-4 | 单维 sum(n_cells_gapfill) = 333,915（每个维度独立） |
| G-C-5 | 报告 markdown 写入并 review |

## Pi-adapter dispatch

适合。无环境不确定性，pandas 内存运算。dispatch 时附 prd.md + design.md。

## Rollback

- 输出目录可整体删除重做，不影响上游或其他子任务。
