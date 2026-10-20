# Roadmap

更新于 2026-10-20。按实施顺序排：先把主循环从长任务上解放出来（1），再给调度加探索项（3），最后做记忆分层（2）。
Dreaming 暂缓。旧 TODO 里仍然有效的条目收在最后。

## 1. 长周期任务监控与自动唤醒（事件驱动的控制器）

现状：`monitor.py` 已经按评估记录 queued / running / validated / analyzing / consumed，`jobs.py` 的队列 daemon 不用模型，
任务 validated 后 `begin_analysis` 唤醒 lead 一次。缺的是等待方式：`run_node` 的线程同步阻塞在 `monitor.wait`，研究模式
parallel 固定为 1，长任务跑着的时候 harness 什么都不做；worker 自己在 shell 里启动的长命令不受监控。

- [x] 节点新增 `waiting` 状态：提交正式评估后释放 worker 线程与槽位。队列 job id、尝试序号和 monitor 路径继续记在
      执行记录与 monitor.json 里（后者已有）。
- [x] wake queue：主循环每轮扫描 waiting 节点的 monitor 记录。validated 的节点排一个分析任务（研究模式走
      `research.analyze`，旧模式走 `_analysis_session`）；失败、超时、早停的进诊断。唤醒次数与时间仍记在 monitor.json。
- [x] 主循环事件驱动：`Orchestrator._run` 的派发条件从"没有 in-flight"改成"有空槽位且没有待处理事件"。研究模式允许
      "一个节点在等结果 + 一个节点在实现"；分析会话优先于新派发；lead 决策时明确告知有哪个结果待定，只能基于
      初步交接。
- [x] `rsi job submit`（worker 可调用）：把长任务注册进同一个队列与 monitor，然后结束会话。任务完成后用保存的
      `session_id` 调 `resume_agent` 让同一会话收尾（grok 和 pi runner 都已支持）。worker prompt 写明"超过 N 分钟的
      命令必须走 submit"。
- [x] 恢复语义不变：重启后 waiting 节点继续等同一次尝试（monitor 已保证）；分析会话崩溃按 `research.max_stage_retries`
      重试；`rsi monitor <exp>` 列出 waiting 节点与 wake queue。
- [x] 可视化：tree.html 的状态筛选与计数认得 `waiting`（Task monitor 面板沿用 monitor 记录）。
- [x] 测试（`tests/test_waiting.py`：等待期间派发第二个分支、中断后重启接回任务、worker submit 后恢复会话）。原计划：`tests/test_jobs.sh` 增加"长任务期间派发第二个节点"和"worker submit 后恢复会话"；`tests/test_unattended.py`
      增加 waiting 节点跨重启的用例。

验收：一个一小时的 job 运行期间，harness 能完成另一个分支的实现并把它排进队列；job 完成后分析会话在下一轮
主循环内开始；重启不产生重复评估。

## 3. 广度 / 深度交替的调度与回溯

现状：旧调度模式严格 best-first，`research_turn` 每 3 次展开优先挑带 falsifier 的 ablate/debug；研究模式把父节点选择
完全交给 lead，digest 按 focus、best 路径、高分、最近排序。两者都没有显式探索项，低分但没展开过的节点排不上。

- [x] 节点优先级（harness 在 `scheduler.py` 计算）：
  - 利用项：节点分数，或子树最优分数（MCTS 式回传；子节点全失败的父节点降权）；
  - 探索项：子树已探索节点数越少越高（UCB 式 `c * sqrt(log N / n)`），自上次出 proposal 以来新增的 wiki 证据包越多越高；
  - 信息项：有未用的、带 research_question / prediction / falsifier 的 ablate 或 debug proposal 加分（并入现有 `research_turn`）。
- [x] 阶段：`search.phase_k`（每 k 轮在深度 / 广度之间切换，两者权重不同）和 `search.phase_adaptive`（出新 best 进深度，
      停滞到 `course_k` 进广度，与纠错评审同一个信号）。每轮的阶段与权重记进 `events.jsonl`。
- [x] 研究模式落地：digest 的 ELIGIBLE PARENTS 按优先级排序，标注本轮阶段和每个节点的探索项；决策抽取时记录 lead 选的
      父节点是否在前 M 名，不在则 `decision.json` 记 warning（不拒绝）；全局复盘可以显式覆盖阶段。
- [x] 旧调度模式：`pick_parent` 改用同一优先级；所有候选分数相同时退化为广度优先（收掉旧 TODO 的 sparse-reward 条目）。
- [x] 回溯可见：`rsi status` 列出当前轮次和前 5 个候选父节点的分解；节点的 `worker.dispatch` / `worker.research.parent_rank` 记录派发时的优先级与名次（tree.html 展示待做）。
- [ ] 评估：同一任务包、同一预算，best-first 对比优先级调度各至少 3 次（`scripts/compare.py`），看最终分数、新 best 出现的
      节点序号，以及"低分分支被重新展开并产生 best"的次数。

## 2. 记忆与上下文分层

现状：`memory.py` 的三层 wiki（raw / claims + AGENDA / index）、supersedes 链、按协议指纹隔离都已有。弱在检索和组装
都是平的：所有 claim 按词元重叠排进 12000 字符；review prompt 的各块固定截断；worker 只看父节点的 IMPLEMENTATION 和
HANDOFF，更远的祖先只有一行路径。

- [x] L1 方向页（hub page）：`state.json` 新增 `topics`，每个主要方向一页：标题、范围、试过什么（claim ID）、最好结果
      （节点 ID）、为什么停、关联子树的根节点。维护模型在 reflect 时一并更新（schema 扩展，校验 ID 引用），`_render`
      生成 `topics/<id>.md` 和索引。
- [x] 分级上下文预算：`memory.context` 改成 L0 议程固定、L1 全部摘要固定、剩余预算给 L2（按查询与所选方向展开）、
      L3 只给路径。`context_chars` 拆成每层上限；review、analysis、worker 三处 prompt 各自声明用哪几层。
- [x] 路径摘要：节点分析完成后，维护模型把"父路径摘要 + 本节点 HANDOFF"压缩成有上限的 `PATH.md`，子节点 worker 与
      分析会话读它，深层节点不再丢失祖先的教训。
- [x] 检索：词元重叠保留，加"方向优先"两步检索（先选 topic，再在 topic 内排 claim）。embedding 留作可选项。
- [ ] 评估：记忆 A/B/C 比较框架已有（`scripts/memory_campaign.py`）。增加一个指标"lead 的决策引用了多少祖先链之外的
      证据"，以及人工盲评 L1 页是否正确概括了方向。

## 暂缓

- Dreaming：每 m 轮让一个独立的 dreamer 读全部证据，在独立的 dream 树里从任意节点重新起步；共享任务包、冻结评测器
  与 wiki，分数可比。合并分三种：嫁接（超过 best 且超出噪声带，挂到基准节点下）、只进 wiki、作为主树的组合实验。
  依赖 1 的空档调度，等 1 落地后再设计细节。
- 自改进：同一任务包跑 harness 变体（prompt、调度参数）比较；agent 提议 harness 改动作为 meta 实验的节点，评测器是
  固定的 benchmark run。
- 多尺度 proxy 到 full 的排序迁移检查；真实 GPU 上的测试任务（3090 小模型训练）；稀疏奖励任务（ARC-AGI-2）。

## 保留的旧条目

- [ ] 发布到 PyPI。
- [ ] 第二、三个简单任务：`spaceship-titanic`、`playground-series-s6e9`。
- [ ] 每个模型至少 3 次重复运行再谈排名；比较页报告方差。
- [ ] auditor prompt 的措辞与配对噪声估计对齐；按任务设噪声下限。
- [ ] pi runner 用真实 provider 做生产测试；自定义 compaction 重载 PROGRESS.md。
- [ ] 节点接受前的代码质量 reviewer（模块大小、确定性、不改 eval）。
