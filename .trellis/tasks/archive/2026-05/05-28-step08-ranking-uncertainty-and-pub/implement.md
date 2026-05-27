# Implement — Step 08 Followup (Parent integration plan)

## Execution order

子任务可以部分并行，但建议按下面 wave 推进：

- **Wave 1**：B → 出 strict-primary 表格 + strict-vs-expanded 表格。是最低风险、最快出结果的 baseline，A/C/D 后续都会引用其点估。
- **Wave 2**：A 与 C 并行。两者都从 by-cell parquet 出发，互不干扰。
- **Wave 3**：D。需要 A/B/C 的聚合表才能画图。
- **Wave 4**：父任务整合 → `publication_ready_step08_summary.md`。

每个 wave 完成后由父任务做一次跨子任务一致性 check（数字交叉点对齐）。

## Parent-level checklist

- [ ] Phase 1.0: 父 + 4 子任务结构存在（已完成 — 见 `task.json children`）。
- [ ] Phase 1.1: 父 prd.md / design.md / implement.md 完成（本文档）；4 子任务各自的 prd.md（+ 复杂子任务的 design.md / implement.md）完成。
- [ ] Phase 1.4: B 子任务先 `task.py start`，进入 Phase 2。
- [ ] Wave 1 完成 → 父任务复核 B 数字与 Step 08 Stage 3/6 报告交叉点一致。
- [ ] Wave 2 完成 → 父任务复核 A 的 CI 是否覆盖 B 的点估；C 切片合计贡献是否解释 80%+ 的 ΔRMSE。
- [ ] Wave 3 完成 → D 的图是否与 A/B/C 表数值一致。
- [ ] Wave 4：写 `publication_ready_step08_summary.md`，整合所有引用，落到 `ncei/derived/model_validation_1min_step08_pub/summary/`。
- [ ] Phase 3.1: 父任务级 quality check（数字交叉点、policy 一致性、约束 R1–R6 复核）。
- [ ] Phase 3.3: 如有新发现的契约/规范，更新 `.trellis/spec/`。
- [ ] Phase 3.4: 单次 commit 包含所有子任务交付物 + 父整合文档；commit message 引用父任务路径。
- [ ] Phase 3.5: 父任务 archive。

## Validation commands

父任务整合层后置的检查：

```bash
# 1. 复核 B 点估与 Step 08 Stage 3 数字一致
python3 ncei/code/22_step08_publication_summary.py --check-only --confirm-cross-check

# 2. 复核 A 的 CI 是否覆盖 B 的 RMSE 点估
python3 ncei/code/22_step08_publication_summary.py --check-ci-coverage

# 3. 复核 C 切片合计是否解释 ≥80% 的 expanded-strict RMSE 抬升
python3 ncei/code/22_step08_publication_summary.py --check-attribution

# 4. 输出最终汇总 markdown
python3 ncei/code/22_step08_publication_summary.py --run-label step08_pub_summary --confirm-final --overwrite
```

实际命令名称可以在父整合脚本设计阶段统一确定。

## Review gates

| Gate | 触发条件 | 通过条件 |
|---|---|---|
| G1 | B 子任务完成 | 与 Step 08 Stage 3 数字对齐；strict-vs-expanded 与 Stage 4/Stage 6 对齐 |
| G2 | A 子任务完成 | bootstrap 收敛（B≥1000）；CI 包含 B 的 RMSE 点估；ranking 概率合理（rank-1 应集中在 GEBCO） |
| G3 | C 子任务完成 | 切片合计 ΔRMSE 贡献占比 ≥ 80%；切片不重不漏 |
| G4 | D 子任务完成 | 图与 A/B/C 表数值一致；缺图原因明确（如 cartopy 不可用 → 改出 TSV） |
| G5 | 父整合完成 | summary md 引用全部 A/B/C/D 主输出；policy 立场不变 |

## Rollback points

- 任一 wave 在 gate 不通过时回滚到该子任务的 Phase 2 重做。
- 父整合层不通过则只回滚 `ncei/derived/model_validation_1min_step08_pub/summary/` 与 `publication_ready_step08_summary.md`。

## Pi-adapter dispatch (optional)

A/B/C/D 子任务均为机械、规格清晰的实现任务（统计方法已在 design.md 锁定），适合通过 Pi-adapter 分发。建议：

- B（最简单、点估聚合）：可由 main agent 直接做，也可 Pi-adapter。
- A（bootstrap）：Pi-adapter 合适，规范完备。
- C（多维切片）：Pi-adapter 合适。
- D（绘图）：建议 main agent 做，因为环境依赖（matplotlib / cartopy）需要交互式判断。

最终是否走 Pi-adapter，由各子任务 `implement.md` 在 Phase 1.1 落地时确定。

## Notes

- 整合脚本 `22_step08_publication_summary.py` 在父任务最终整合阶段写；不在 Wave 1 触发。
- 子任务之间不直接互写：所有依赖通过聚合表落盘后读取。
- 子任务 archive 后再启动下一个子任务 / 父整合，避免长时间多 in_progress。
