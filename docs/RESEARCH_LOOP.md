# pi-rsi：研究循环、三层 Wiki 与 Task Monitor

搜索空间是一棵树，控制流程是一个顺序执行的研究循环。树保存不同方案的代码版本与结果；每个官方结果分析完后，研究 agent 直接用自然语言提出下一次实验，定期的全局复盘再从整棵树重新判断。可以回到任意仍可展开的分支，包括当前分数较低、但适合验证解释的分支。

## 数据模型与控制边界

树文件使用 schema v3，首次保存旧树前保留 `tree.before-schema-v3.json`。研究节点以 `hypothesis_id` 标识一个被选择的研究问题/方案；历史 `retry_of` 节点保留原始文件和 ID，但共用同一个研究身份。搜索、预算和可视化按研究身份归并，已有代码版本与测量来源仍可追溯。

执行记录保存在 `executions/<node-id>.json`，拥有自己的尝试 ID、阶段、错误、用时和进程恢复状态。实现/评测失败重试会在同一研究节点增加执行尝试，继续其原有 Git 工作区；不会创建新的研究问题。每次尝试的日志与旧交接保存在节点的 `attempts/aNNN/`。实现时间和调参记录在同一研究问题内累计，不因重试清零。

正式测量独立记录代码、评分文件、哈希、得分、测量时的原最好结果，以及评估协议身份（评估器文件、评分配置、正式级别与预算、`memory.protocol_id` 数据版本；超时等运行参数不计入）。协议变化后，旧测量保留为 `stale`，不再参与选择、展开或最终确认；基线不可比时停止派发（`protocol_changed`），用 `rsi reeval` 在新协议下重测（保留旧记录），或恢复原评估器后自动恢复原记录。升级前没有协议字段的旧记录在首次运行时按当时的协议接管，升级前发生的变化无法追溯。测量注册后即能参与“最好已测结果”的比较；文档是否完成不会撤销这个事实。分析、审计、发布分别拥有文档状态。顺序研究循环仍要求完成交接后再选择下一次实验；结果被隔离时禁止复用，不以重新训练掩盖完整性问题。旧 `status` 和 `worker` 字段仅保留兼容视图，重启从执行记录恢复。

`search.max_nodes` 限制不同研究问题/方案数；`search.max_attempts` 单独限制执行次数，未指定时为 `max_nodes * (max_retries + 1)`。`search.max_retries` 限制执行恢复，`research.max_stage_retries` 限制文档恢复。等待或修复文档不消耗新的研究节点，但模型调用与实际队列 GPU 用时仍照常记账。控制器持有文件租约，重复启动不能产生重复执行。

研究模式的 `width_root/width` 仅是分支宽度建议，父节点资格统一由有效测量、代码版本和深度上限决定；不会要求填满 root，也不会因已有几个孩子而禁止回到最好方案。每轮由研究 agent 比较增益潜力和信息价值。旧调度模式保留有界宽度行为。

测量和原始来源的内容指纹控制证据更新；AI 分析文字修订、Wiki 编译和索引变化不会伪装成新的科学观测。新的测量、来源内容、人工指令或预算变化会重新触发判断。显式 `reeval` 保存新测量版本和旧记录；恢复流程不能替换已验证的测量。

## 自然语言决策与结构化

研究 agent 只写自然语言。每个节点分析完写两份分工不同的文件：`HANDOFF.md` 是这个节点的永久记录，只向后看（做了什么、测到什么、意味着什么），子节点 worker、审计和 Wiki 都读它；`NEXT.md` 只向前看（下一次实验、备选想法、是否需要复盘或停止），只被下一次决策读一次。全局复盘写 `cycles/<cycle>/DECISION.md`。它不写 JSON。维护模型（默认 GPT-6 Luna）把文字抄成结构化字段（`extraction.json`），框架校验后写出 `decision.json` / `analysis.json` 供执行、审计和后续模型读取。原文是唯一可信来源，worker 收到的是决策原文，不是摘要。

字段分两类：

- 决定执行什么的字段严格校验：继续还是停止必须附原文句子（代码核对确实出现在原文中）；父节点必须是原文里写出的、可展开的节点 ID，并遵守人工 focus；时间和调参预算超过上限时截到上限，缺省时取上限。
- 审计和知识字段只记警告（`decision.json` 的 `warnings`）：拼错的证据 ID 按相似度纠正到已知 ID，无法对应的丢弃；不合格的参考来源丢弃；未被选中的备选方案有问题时移到 `excluded_candidates`；只有一个方案、缺少预测或证伪条件只是警告。

抽取失败时先把拒绝原因告诉抽取模型重试一次。来自 `NEXT.md` 的提议仍无法执行，就转入全局复盘；全局复盘仍无法执行，就在同一会话里向研究 agent 追问一次（原文备份为 `DECISION.before_clarify.md`），再抽取。只有这些都失败，才停止于 `research_failed`。

全局复盘的触发条件：没有可用提议（第一次决策、最近结果失败或没有写 `NEXT.md`）；距上次复盘已有 `research.review_every` 个实验（默认 5；1 表示每次都复盘，0 表示只按其他条件）；连续 `search.patience` 个实验没有新最好结果；人工指令（`HUMAN.md`）变化；提议建议停止（停止必须经全局复盘）；`rsi continue` 之后。

框架修复后可用 `rsi research repair <experiment>` 重新校验已保存的计划：证据快照必须未变，已派发的计划不能重用，原计划和排除记录保留。随后用 `rsi run <experiment>` 在原预算内恢复运行。

结果分析的结构化同样由维护模型完成：`analysis.json` 只是 HANDOFF 的结构化视图，不含下一步；必须附一句 Result 段落的原文，至少要有一条测量观察；每个列表超过 12 条时由代码截断，不再请大模型做格式修复。

正式评分完成后，分析、审计和发布分别记录完成阶段。每个失败阶段最多按 `research.max_stage_retries` 在同一节点内重试，不会重新调用实现 worker、评测器或分配新节点。成功的分析和审计可以复用。重试耗尽时节点显示 `incomplete / notes pending`：评分已完成，交接尚未完成；有效测量仍参与最好已测结果的比较，不会被当成模型方法失败。控制器停止于 `postprocess_failed`，不会执行最终确认。

再次运行 `rsi run` 会在原节点恢复未完成的阶段，保留原始评分。恢复前后都校验代码提交、工作区、评分文件，以及评测器提供的模型和预测文件哈希；有变化时拒绝复用，也不会创建替代实验。已完成的决策捕获自己引用的原始来源、或 Wiki 重新编译时，不会因此重复思考；新增原始证据、测量、可展开父节点、人工指令或预算变化仍需要重新判断。

```text
任务 / 当前结果 / Wiki / 原始来源
                ↓
首次 / 定期 / 停滞 / 新人工指令：全局复盘 → DECISION.md（自然语言）
否则：采用上一个结果的 NEXT.md
                ↓ Luna 抽取 → 框架校验 → decision.json
选择一个方案 → 实现 + 在预算内调参 → 初步 HANDOFF.md
                ↓
提交正式实验 → Task Monitor 等待（没有模型调用）
                ↓ 成功完成且结果通过校验
唤醒研究 agent → 分析官方结果 → 正式 HANDOFF.md + 下一步 NEXT.md（均为自然语言）
                ↓ Luna 抽取 analysis.json
GPT-6 Luna 整理 Wiki、索引、结论修订与可视化说明
                ↓
回到决策：继续、换分支、做验证；停止只能由全局复盘决定
```

## 角色与权限

- 研究 agent：默认沿用实现 worker 的模型和推理设置。分析结果时提出下一次实验；全局复盘时是独立的工具会话，可以读代码、交接和来源，查参考做法。两者都用自然语言说明选择、理由、预测、反例和备选方案。
- 实现 worker：开放式修改代码，一个节点对应一个方案；允许在这个方案内进行开发集调参。节点保留代码版本、调参记录和交接。
- Task Monitor：普通 CPU 评估和长时间训练均由进程队列运行。等待、轮询、重启恢复、超时和失败处理由代码执行。它不请求模型。
- 维护 agent：默认 `pi / openai-codex/gpt-6-luna / medium`。把研究 agent 的文字抽取成结构化字段，整理有证据引用的知识页、研究议程和结论变化；索引和可视化由框架从已验证的结构化输出生成。
- 固定评估器和审计：框架计算正式分数、核对预算与来源 ID。模型输出是解释和建议，不会替代正式测量，也不能提高资源上限。

全局复盘的工具权限取决于所选 runner。需要外部参考时，保存实际读取的、有标题与 URL 的摘录；不能访问时记录缺口。来源中的说法不自动等于本地实验已证实的结论。

## 三层知识存储

每个任务和评估协议拥有独立的 Wiki。兼容实验可共享知识；不兼容的评估器、协议配置或显式数据版本不会混用。

```text
protocols/<protocol>/
  raw/                            第一层：不可变原始来源与实验证据包
    e-<hash>.json                  保存官方测量、代码身份、原始交接与解释的区别
  revisions/<revision>/
    wiki/<claim-id>.md             第二层：AI 生成的知识页
    AGENDA.md                      动机、方法、剩余问题与下一次验证
    CHANGES.md                     旧结论如何被新证据修订
    index/INDEX.md                 第三层：导航索引
    index/index.json               引用、类别、状态、适用范围与替代关系
    state.json                     结构化、版本化的知识状态
  CURRENT.json                    原子发布指针
  INDEX.md                        当前版本入口
```

旧版本和 raw source 保留。索引只用于检索，不能作为另一份独立证据。多次整理同一个节点的结果也不算重复实验。

知识区分 observation、hypothesis、experience；状态包括 untested、supported、mixed、refuted、superseded。新结果有支持也有反证时保留两侧引用。需要推翻旧解释或改变适用范围时，显式退休旧页，给新页一个 ID，记录 `supersedes` 和 `revision_reason`；不能通过删反证把旧结论变得可信。

## 内容归属：每类内容只有一个家

研究模式下，每类内容只有一个归属文件和一个作者；其他地方只引用它（ID 或路径），或是由代码从它生成的只读视图。

| 内容 | 唯一归属 | 作者 | 其他地方 |
|---|---|---|---|
| 官方分数、代码版本 | `nodes/<id>/eval/metrics.*.json`、git commit | 框架 | tree.json 只做索引 |
| 结果判定（提升 / 无变化 / 变差 / 不确定） | `nodes/<id>/eval/comparison.json` | 框架代码 | 审计、HANDOFF、报告都引用它，不再自己设门槛 |
| 门槛、噪声带、预算等前提 | `setup/setup.json`（`SETUP.md` 是生成视图） | 人 / human-proxy | 提示词里原样引用 |
| 这个节点做什么 | 选中它的 `cycles/<c>/DECISION.md` | 研究 agent | `HYPOTHESIS.md` 与 tree 标题是视图 |
| 实现过程 | `IMPLEMENTATION.md`、`PROGRESS.md`、`TUNING.jsonl` | worker | worker 不写 HANDOFF 和 proposals.json |
| 结果意味着什么 | `HANDOFF.md`（`analysis.json` 是其抽取视图） | 分析 agent | — |
| 下一步 | `NEXT.md` → `DECISION.md` | 研究 agent | Wiki 议程不再写 next experiments |
| 跨节点知识 | Wiki 结论页 | Luna | `INSIGHTS.md` / `DEADENDS.md` 是 Wiki 生成视图；审计员不再追加 |
| 数字核对 | `audit.json`（摘要 + claim check） | 审计 | `SUMMARY.md` 是视图 |
| 纠错结论 | `course/kNNN/COURSE.md`（`course.json` 是抽取视图） | 纠错评审 | 之后的决策提示词引用暂停方向 |

旧调度模式（非研究模式）保持原有文件分工。

## Setup 阶段与 human-proxy

研究模式的实验在 `rsi run` 之前必须完成 `rsi setup`（否则停止于 `setup_required`）：

1. 自动检查：基线按 `setup.calibration_runs`（默认 3，含根节点评估）重复评估，标准差换算成两次结果之差的 2σ 噪声带。它只覆盖同代码、同种子、同样本的重跑噪声。
2. 评审 agent（研究模型，只读工具）写 `setup/REVIEW.md`：风险、要问人的问题、推荐答案与理由、是否关键、类别；Luna 抽取成问题列表。框架总会问实用门槛 `practical_delta`。
3. 决定：人在终端回答，或 `rsi setup <exp> --answer id=value` / `--accept-recommended`；等待中的问题写在 `setup/QUESTIONS.md`。

`--yolo`（`setup.proxy = true`）让 human-proxy 代答：它依据人的原话（`rsi.toml` notes、`HUMAN.md`、任务说明、以往回答）回答，结论附原文依据并标注作者，人随时可以改答。权限：门槛、噪声校准方式、复盘频率、上限内的预算分配、换模型族、诊断实验、附饱和检查的停止可以由 proxy 决定；改评估器 / 指标 / 划分、提高预算上限或 GPU、打开封存的 final 留出集、对外提交上传、删除数据只能由人决定。**首次 setup 中所有关键问题和只能由人决定的问题，即使在 yolo 模式下也必须由人确认。** 运行中途出现的只能由人决定的问题进入 `QUESTIONS.md`，实验按当前 setup 继续。

结果判定：差值超过 `max(噪声带, practical_delta)` 才算提升；噪声来源依次取配对 bootstrap、配对逐项、报告的 SEM、setup 的基线重跑；只有启发式门槛时判定为 uncertain。

## 中途纠错

代码统计自上次纠错以来、没有"超过门槛的新最好结果"的连续实验数；达到 `setup.course_k`（默认等于 `search.patience`）时，一个新的评审 agent（不是正在跑的研究 lead）退一步检查数据、模型与算法族、评估设置和搜索方式，写 `course/kNNN/COURSE.md`：诊断、暂停的方向、下一步方向（可以是只为看清问题的诊断实验）、setup 是否要改。之后的决策强制走全局复盘，复盘必须遵循纠错结论或说明依据；暂停方向列在之后每次决策的提示词里；抽取器明确回答提议是否重新进入某个暂停方向（`reenters_paused`；执行暂停所要求的前置诊断不算），若是则提议不执行、改走全局复盘，只有复盘可以凭新证据解除暂停。setup 需要改时作为中途问题交给人或 proxy。纠错失败只记录，不停止实验。

## Proxy 的质量

研究用到的每个分数都只是上一层的 proxy：dev（quick）结果代替官方结果，官方结果代替真实目标（比赛的隐藏榜）。为避免 proxy 悄悄换掉目标（2026-10 CASMI26 newflow：lead 把"每个分段、每个 seed 都不下降"当交付门槛，27 次官方评估中 20 次测的是与父节点逐字节相同的输出）：

- **交付声明**：worker 写 `nodes/<id>/DELIVERY.json`（`component` 为 on/off/none，`active_commit`，`dev_delta`/`dev_sem`）。worker 把新组件关掉（off）时，harness 把 `active_commit` 的代码树恢复成新提交再做官方评估（`research.measure_active`，默认开）：官方评估测试的是想法本身，按官方分数选最好节点才是安全网。记录在 node.worker.delivery 和 `eval/comparison.json`。声明 `none`（诊断节点、或没有可交付的新组件）时不做官方评估（`research.skip_unmeasured`，默认开）：执行日志记 `measurement.state = "skipped"`，节点以 verdict `not_measured`、无分数完成，不参与最好节点、不可作为父节点；lead 仍分析它的开发/诊断结果（提示词写明没有官方结果），审计由 harness 生成。重启时它和已验证的测量一样是持久边界：只恢复文档阶段，不会重跑 worker 或评估。
- **Proxy 台账**：`PROXY.md` / `proxy.json`（tree 的视图）逐节点列 dev Δ、lead 预测的官方 Δ（抽取器从决策文本取 `expected_delta`）、官方 Δ、输出是否与父节点相同；汇总 dev 与官方的符号一致率和预测落空次数。lead 的分析、全局复盘和纠错评审都读到它；连续 3 次预测为正而实际不涨时触发全局复盘。
- **真实目标的观测**：`rsi observe` 写 `observations.jsonl`（例如 Kaggle 公榜分数），出现在同一段上下文里。setup 评审在 `REVIEW.md` 必须写 `## Proxy validity`：官方层与真实目标的差异、偏差方向、怎么监控，以及 dev 层的分段比较有没有统计功效；该段写入 `SETUP.md`。
- **竞赛提示词**（`prompts/competition.md`）：目标是官方总分；分段只做诊断，只有超过该分段自身约 2 个配对 SE 的下降才能否决；默认交付规则是两 seed 合并的 dev 总分增益为正；更严的条件必须引用 setup 决定。
- 调参试验按不同的 trial 编号计数；超出上限记为 `protocol_deviation`（写入 comparison.json），不再让整个节点失败。

## 噪声与有意义的结果

框架把分数选择与知识结论分开。相同、完整、无重复的逐项结果可提供配对差值的经验噪声诊断；不同协议、分割或不兼容变换不做配对。缺少可估计的测量噪声时标为 uncertain，旧的启发式噪声阈值不能建立有意义的发现。

即使变化高于经验噪声，也要分析实际效果大小、重复实验、适用条件和竞争解释。相关的折分和适应性选择不能当作独立确认；涨分不能单独证明机制。需要时选择对照、消融或重复，而不是只追逐分数。

## Task Monitor 与恢复

状态记录保存在 `nodes/<id>/eval/*.monitor.json`：排队、运行、任务结束、结果已校验、模型分析中、结果已消费。记录队列 ID、结果 hash、完成时间、唤醒时间和唤醒次数。

只有成功结束、正式指标有效的任务，才进入研究结果分析。失败、超时、提前终止和缺失结果进入诊断，不作为成功实验发布。相同代码、命令和协议的排队/运行任务在控制器重启后继续等待，已完成任务可复用；完成结果被改动会拒绝复用。

评估的尝试序号（含 `--resume` 重试）保存在 monitor 记录中，任务身份不包含 `--resume` 参数。控制器重启后继续等待正在运行的那次尝试，或在上次尝试失败后接着下一次尝试；不会重新从第 0 次开始，也不会因重启获得额外尝试次数。队列每个目录只有一个 daemon（`jobd.lock`），任务领取与启动是原子的；daemon 重启后接管的存活任务仍受超时、停滞、NaN 和早停检查，信号发送前核对进程身份，避免误杀复用的 PID。早停按不同检查点计数，不按轮询次数。

控制器在正式评估或分析阶段中断后，保留原 worktree，恢复该阶段，不重新做实现。已经完成并保存的、同一次测量的分析不重复调用模型。模型调用在保存完成结果之前崩溃时可能需要重新分析；这个原型不保证远端模型请求恰好执行一次。

全局复盘的提示词只包含有界摘要（`research.context_chars`，默认 40000 字符；结果分析里的摘要最多 16000 字符）：预算、人工指令、最好路径与高分/最新的可展开父节点、最近历史。完整快照保存在 `cycles/<cycle>/snapshot.json`，研究 agent 按需读取；父节点资格、证据引用和计划缓存仍按完整快照校验，因此摘要外的分支依然可选。pi runner 通过 stdin 传递提示词，不受单个命令行参数 128 KiB 的限制。

复盘会话在保存 DECISION.md 后达到时限时，框架照常抽取并校验这份文字。
重启时，最后一个未派发的决策只要证据快照未变，就重新抽取、校验后恢复，不再调用研究 agent；这也覆盖旧版框架因校验过严而拒绝的计划（例如未选备选里一个拼错的证据 ID）。不把空文件或失败的后端回复当作有效决定。
研究控制器失败、运行时损坏或人为中断会延期最终确认，避免把基础设施故障当作研究已经完成。“停止派发的原因”与“待恢复故障”分开判断：即使墙钟、节点数等预算条件先触发，只要仍有未完成交接、THINK 失败、未结束节点、运行时损坏、协议变化或中断，最终确认都会延期，`final.json` 的 `faults` 列出原因。预算在 THINK 开始前耗尽属于正常停止，不记为研究失败。

搜索预算限制接收新任务；已经得到正式评分的节点仍有独立、有限的结果分析时限。
若旧运行已因分析超时/墙钟结束而留下失败节点，可用 `rsi closeout <experiment> --seconds 600`
补齐分析、审计和交接。该命令核对原代码、检查点、预测和评分身份，只调用分析 agent，不训练、
不重新评分、不增加搜索节点。原故障记录保留在节点的 `closeout.original.json` 和日志中。

等待不占线程。正式评估提交到队列后节点进入 `waiting`（执行记录的 `execution.state = "waiting"`），worker 线程立即释放；控制器每轮扫描等待中节点的 monitor 记录（`task_wake` 事件），任务结束就给它一个线程去收结果、分析、审计、发布。同时最多允许 `search.max_waiting` 个结果待定时继续派发新节点（默认 1：一个在等、一个在实现；0 恢复严格串行）。研究 lead 的摘要里有 `PENDING RESULTS` 一段列出待定节点，决策时不得重复它们、也不能指望它们。等待中的节点算未完成工作：预算停止后仍收完待定结果再确认；中断留给下一次 `rsi run`，重启时 `recover` 按执行记录把它接回同一个队列任务（同样的代码、命令和协议），不会重复提交。失败的评估重试是新的实现尝试，不再接回失败的任务。

节点内的 quick 开发迭代仍由实现会话负责；长命令通过 `rsi job submit --node-dir <nodes/id> [--gpus N] [--timeout S] -- <命令>` 交给同一个队列：记录写在 `nodes/<id>/jobs/<job>.json`，worker 写完 PROGRESS.md、commit 后结束会话；节点进入 `waiting`（`worker_job`），job 结束后框架用保存的 session_id 恢复同一个会话（`worker_resume`，时限 `runner.resume_timeout_s`，不低于 `runner.resume_min_s`），worker 读取结果、完成实现并写交付文件，再进入正式评估。每个节点最多 `runner.max_job_rounds` 轮；提示词告诉 worker 超过约 `runner.long_command_s` 的命令必须这样提交。直接在模型 shell 工具中启动并等待一个任意长命令，仍然不会成为受监控的任务。

## 调度优先级与阶段

可展开的父节点按优先级排序（`scheduler.priorities`，旧调度模式与研究模式共用）：利用项是节点分数或子树最优分数在候选中的归一化位置；探索项是 `explore_c / sqrt(1 + 已探索后代数)`；信息项是有未用的、带 research_question / prediction / falsifier 的 ablate 或 debug 提案；新证据项是节点（或其子节点）上次完成之后又完成的节点比例；子节点全部失败的父节点扣分。深度轮权重偏利用，广度轮偏探索：`search.phase_k > 0` 时每 k 个已派发节点交替一次；否则自适应，连续 `search.breadth_after`（默认 max(2, patience // 2)）个结果没有新 best 就进广度，出新 best 回深度。研究模式把排名、轮次和每个节点的 `rank` 写进摘要（`PHASE` 一行），lead 可以偏离，选到前 `search.priority_top_m` 名之外时 `decision.json` 记 warning，`node.worker.research.parent_rank` 保留它的名次；旧模式直接按优先级选父节点，分数相同时退化为广度优先。`rsi status` 打印当前轮次和前五个候选父节点的分解。

## 启用与检查

新实验默认启用研究循环、Wiki 和 Luna 维护。原有实验配置没有这些新字段时保持原调度行为，显式启用：

```bash
rsi research enable <experiment>
rsi research status <experiment>
rsi run <experiment>
rsi monitor <experiment>           # 只读检查，无模型调用
rsi render <experiment>
```

需要分别指定研究和维护模型时：

```bash
rsi research enable <experiment> \
  --research-runner pi --research-model <provider/model> --research-effort high \
  --maintainer-runner pi --maintainer-model openai-codex/gpt-6-luna
```

`rsi init` 对应支持 `--research-*`、`--think-timeout` 和 `--maintainer-*`。`--no-research-loop` 保留原树调度器；`--no-maintainer` 让 Wiki 使用原 utility 配置。离线测试显式选择 script runner，不伪装成真实模型研究。

## 停止与预算

研究循环一次执行一个实现，即使旧的 `search.max_parallel` 大于 1。节点内实现/调参的会话时限不超过所选方案和 worker 上限；记录的调参试验数会检查上限。试验记录依赖 worker 如实报告，不是任意生成代码的强制沙箱。

`max_nodes`、墙钟和 GPU 预算仍限制搜索。研究模式下墙钟累计保存，控制器重启不会清零。官方实验采用独立任务超时；墙钟限制停止接收新工作，已有任务按其超时有界结束。若分析阶段没有剩余预算，记录未完成，不把缺失分析当成科学结论。

分数 patience 在研究模式中作为“需要重新思考”的信号；完成/饱和由全局复盘说明检查标准，硬预算耗尽则记录资源停止。继续一个已经结束的研究使用 `rsi continue` 显式调整节点/墙钟上限并清除停止决策。

可视化保留搜索树和正式分数，增加每个节点的 Decision（选中它的决策原文）、Result analysis，以及 Wiki & revisions、Task monitor 面板。Luna 整理的结论和变化可检查到具体引用；显示的数字来自框架记录。

## 验证范围

`tests/test_setup.py` 验证 setup 门禁、首次 setup 关键问题必须由人确认（yolo 也一样）、proxy 越权答案不记录、中途问题不阻塞、噪声校准、判定门槛、停滞计数、纠错与失败不停机、知识视图。`tests/test_research_loop.py` 验证：选择较低分分支、提议直接执行与转入复盘、复盘触发条件、追问一次、抽取必须引用原文、审计字段只警告、旧计划重启恢复、预算上限、显式完成判断、重启预算、结论替代与历史保留、未完成任务不唤醒、完成结果防篡改，以及真实 CPU 队列与 fixture agent 的完整循环。

这些检查验证运行机制。真实模型的参考搜索质量、科研判断和多天稳定性仍需在实际任务上测量，不能从 fixture 测试推断。
