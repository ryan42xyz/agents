# SRE Oncall Triage Agent — Architecture

## 0. GCORF Design Framework

GCORF（Goal / Controllability / Observability / Reversibility / Feedback Loop）是这个 agent 的设计框架。每个维度不是独立模块，而是贯穿整个系统的设计约束。

### GCORF → 实现映射

| 维度 | 设计问题 | sre_oncall_triage_agent 实现 | 关键文件 |
|------|---------|------------------|---------|
| **G — Goal** | agent 的目标是什么？怎么定义"成功"？ | Evidence-backed investigation, not speculation. 成功 = 正确 triage + 保守 Slack response + 完整 evidence chain. | `SKILL.md` (Goal / Hard constraints) |
| **C — Controllability** | 怎么限制 agent 的行为空间？ | 三层防线：Claude permissions → hook chain (k8s-gate.sh tier 强制) → agent spec (read-only + scope declaration + query safety rules + debug tree deterministic branching) | `k8s-gate.sh`, `SKILL.md`, debug trees |
| **O — Observability** | 怎么看见 agent 的决策过程？ | INTENT convention (why, not just what) + K8s audit JSONL + MCP audit JSONL + investigation log table (每步 tool/query/result/interpretation) + verify.py (输出质量) + slo.py (趋势) | `audit-pre.sh`, `mcp-audit.sh`, `verify.py`, `slo.py` |
| **R — Reversibility** | 出错了怎么回退？ | Read-only investigation = nothing to reverse. 所有 mutation 走 #MANUAL gate, PROD tier agent 只打印命令不执行, PREPROD 先 --dry-run. Post-investigation case 存储是 opt-in ("要存吗？") | `k8s-gate.sh`, runbook `#MANUAL` markers |
| **F — Feedback Loop** | agent 怎么越用越好？ | Post-investigation case creation → knowledge/cases/. Debug tree proposal for new paths. slo.py 追踪质量趋势. Routing table 本身 derived_from cases (metadata 里声明了). verify.py 每次调查都检查质量退化. | `slo.py`, `knowledge/cases/`, `agent-routing-table.md` |

### GCORF 架构图

```mermaid
flowchart TD
    subgraph G["<b>G — Goal</b><br/>Evidence-backed investigation"]
        G1[SKILL.md Goal section<br/>conservative, evidence-backed]
        G2[Hard constraints<br/>never speculate, never invent scope]
        G3[Verifier checks<br/>conclusion must match evidence]
    end

    subgraph C["<b>C — Controllability</b><br/>限制行为空间"]
        C1[Claude permissions<br/>only kubectl get/describe/logs allowed]
        C2[k8s-gate.sh<br/>PROD read-only, PCI follow PROD<br/>PREPROD dry-run, DEV with INTENT]
        C3[Scope Declaration<br/>declares what will be queried<br/>out_of_scope checked by verifier]
        C4[Query Safety Rules<br/>label filter, step ≥ 30s, window ≤ 24h]
        C5[Debug tree structure<br/>deterministic branching, no free-form]
    end

    subgraph O["<b>O — Observability</b><br/>看见决策过程"]
        O1["INTENT convention<br/># INTENT: one-line WHY<br/>captured in audit log"]
        O2[K8s audit<br/>audit-pre.sh + audit-log.sh<br/>JSONL with command + stdout]
        O3[MCP audit<br/>mcp-audit.sh<br/>tool + params + response]
        O4[Investigation log table<br/>Step / Tool / Query / Result / Branch]
        O5["verify.py — per-investigation QA<br/>slo.py — aggregate trends"]
    end

    subgraph R["<b>R — Reversibility</b><br/>出错可回退"]
        R1[Read-only by default<br/>nothing to reverse]
        R2["#MANUAL gates in runbooks<br/>human executes all mutations"]
        R3[PROD: agent prints command<br/>human decides whether to run]
        R4[PREPROD: --dry-run first<br/>see plan before execution]
    end

    subgraph F["<b>F — Feedback Loop</b><br/>越用越好"]
        F1["Post-investigation<br/>case → knowledge/cases/"]
        F2[New debug tree proposals<br/>for uncovered paths]
        F3["slo.py trends<br/>debug_tree_rate, verdict distribution"]
        F4["Routing table evolution<br/>derived_from: cases/*.trace.md"]
    end

    G -->|defines success criteria for| O
    C -->|constrains actions observed by| O
    O -->|surfaces failures caught by| R
    R -->|safe failures feed into| F
    F -->|improves spec that tightens| C
    F -->|refines definition of| G
```

### GCORF 与 SRE 的同构关系

| GCORF 维度 | SRE 等价物 | sre_oncall_triage_agent 等价物 |
|-----------|-----------|-------------------|
| **Goal** | SLI/SLO — 定义"可靠"的数值含义 | Task success rate + evidence chain completeness |
| **Controllability** | RBAC + blast radius 控制 | Tier enforcement + scope declaration + query safety |
| **Observability** | Metrics + logs + traces (OpenTelemetry) | INTENT audit + MCP audit + investigation log + verify/slo |
| **Reversibility** | Rollback + canary + blue-green | Read-only default + #MANUAL gate + --dry-run + "print command for human" |
| **Feedback Loop** | Postmortem → action items → SLO refinement | Case creation → routing table evolution → debug tree expansion |

关键洞察：**GCORF 的五个维度形成一个闭环**。Feedback Loop 改进 Controllability（新 case 产生新的 routing rule），Controllability 约束 Observability 的范围（scope declaration 告诉你该看什么），Observability 暴露 Reversibility 的需要（verify.py 发现问题），Reversibility 的安全回退产生新的 Feedback（失败 case 也是学习材料）。

---

## 1. Investigation Pipeline

Alert 从输入到输出的完整流程。

```mermaid
flowchart TD
    A[Alert / Slack Message] --> B[Signal Extraction]
    B --> C[Routing Table<br/>6 triage clusters]
    C --> D{Debug tree<br/>matches?}
    D -->|Yes| E[Scope Declaration]
    D -->|No| F[FACETS-based Checklist]
    E --> G[Debug Tree Execution<br/>MCP tool calls per step]
    F --> H[Manual Checklist Generation]
    G --> I[Output File<br/>tmp/sre-triage-*.md]
    H --> I
    I --> J[Verifier<br/>verify.py]
    J -->|PASS| K[Slack Response<br/>ready to send]
    J -->|WARN| L[Review warnings<br/>then send]
    J -->|FAIL| M[Fix output<br/>re-run verifier]
    M --> J
    K --> N{Save case?}
    L --> N
    N -->|Yes| O[knowledge/cases/]
    N -->|No| P[Done]
```

## 2. Safety Layers

三层防线，从外到内。每层解决不同的问题。

```mermaid
flowchart LR
    subgraph L1["Layer 1: Claude Code Permissions<br/>(settings.json)"]
        P1[permissions.allow<br/>只列了 kubectl get/describe/logs]
        P2[permissions.deny<br/>显式封 delete ns/drain/cordon]
        P3[未列入 allow 的命令<br/>弹 permission prompt]
    end

    subgraph L2["Layer 2: Hook Chain<br/>(PreToolUse / PostToolUse)"]
        direction TB
        H1[k8s-gate.sh<br/>环境 tier 强制执行]
        H2[audit-pre.sh<br/>INTENT 记录]
        H3[audit-log.sh<br/>kubectl 执行结果审计]
        H4[mcp-audit.sh<br/>MCP tool call 审计]
    end

    subgraph L3["Layer 3: Agent Spec<br/>(SKILL.md + Debug Trees)"]
        S1[Hard constraints<br/>read-only investigation only]
        S2[Query Safety Rules<br/>label filter / step floor / time ceiling]
        S3[Scope Declaration<br/>out_of_scope 声明]
        S4[on_error handling<br/>失败时的标准化行为]
    end

    L1 --> L2 --> L3
```

## 3. Environment Tier Enforcement

k8s-gate.sh 如何按集群环境分级处理命令。

```mermaid
flowchart TD
    CMD[kubectl/alias command] --> IS_K8S{Is K8s/AWS<br/>command?}
    IS_K8S -->|No| SKIP[Exit 0<br/>skip]
    IS_K8S -->|Yes| HARD{Hard block<br/>checks}
    HARD -->|namespace deletion<br/>cross-ns delete<br/>IAM mutation<br/>EC2 terminate| BLOCK_HARD[Exit 2<br/>BLOCKED]
    HARD -->|pass| TIER{Classify<br/>alias tier}

    TIER -->|PROD / PCI / MGT / DEMO| PROD_CHECK{Mutating<br/>op?}
    PROD_CHECK -->|Yes| BLOCK_PROD[Exit 2<br/>print command<br/>for human to run]
    PROD_CHECK -->|No| READ_WARN[Read-op warnings<br/>then Exit 0]

    TIER -->|PREPROD| PREPROD_CHECK{Mutating<br/>op?}
    PREPROD_CHECK -->|delete| BLOCK_PP[Exit 2]
    PREPROD_CHECK -->|other mutating| DRY{--dry-run?}
    DRY -->|Yes| DRY_OK[Allow<br/>plan only]
    DRY -->|No| DRY_WARN[Warn: run<br/>--dry-run first]
    PREPROD_CHECK -->|read| READ_WARN
    DRY_OK --> READ_WARN
    DRY_WARN --> READ_WARN

    TIER -->|DEV| DEV_CHECK{Mutating<br/>op?}
    DEV_CHECK -->|Yes| INTENT{# INTENT<br/>present?}
    INTENT -->|No| INTENT_WARN[Remind:<br/>add INTENT]
    INTENT -->|Yes| ALLOW[Exit 0]
    INTENT_WARN --> ALLOW
    DEV_CHECK -->|No| READ_WARN

    TIER -->|Unclassified| UNCLASS{Mutating?}
    UNCLASS -->|Yes| BLOCK_HARD
    UNCLASS -->|No| READ_WARN

    READ_WARN --> EXIT_OK[Exit 0]
```

## 4. Debug Tree Execution Model

单个 debug tree step 的执行逻辑，包括 on_error 处理。

```mermaid
flowchart TD
    START[Read Step N<br/>from debug tree] --> CALL[Execute MCP tool call<br/>with query from step]
    CALL --> SUCCESS{Tool call<br/>succeeded?}
    SUCCESS -->|Yes| EVAL[Evaluate result<br/>against branch conditions]
    EVAL --> BRANCH{Which<br/>branch?}
    BRANCH -->|Continue| NEXT[→ Step N+1]
    BRANCH -->|ESCALATE| ESC[Stop: ESCALATE<br/>human intervention]
    BRANCH -->|MANUAL| MAN[Stop: #MANUAL<br/>human gate]
    BRANCH -->|Terminal| DONE[Conclusion<br/>with verdict + evidence]

    SUCCESS -->|No| ONERR{on_error<br/>section?}
    ONERR -->|RETRY_ONCE| RETRY[Wait 5s<br/>retry query]
    RETRY --> RETRY_OK{Retry<br/>succeeded?}
    RETRY_OK -->|Yes| EVAL
    RETRY_OK -->|No| FALLTHROUGH[Fall to next action]

    ONERR -->|MARK_UNKNOWN| UNKNOWN[Record UNKNOWN<br/>add to Uncertainty Note<br/>continue to next step]
    UNKNOWN --> NEXT

    ONERR -->|FALLBACK_QUERY| FALLBACK[Execute<br/>alternative query]
    FALLBACK --> FB_OK{Fallback<br/>succeeded?}
    FB_OK -->|Yes| EVAL
    FB_OK -->|No| UNKNOWN

    ONERR -->|ESCALATE| ESC
    ONERR -->|No on_error| DEFAULT{Terminal<br/>step?}
    DEFAULT -->|Yes| ESC
    DEFAULT -->|No| UNKNOWN

    FALLTHROUGH --> ONERR
```

## 5. Audit & Observability

四个 hook 的触发时机和数据流。

```mermaid
flowchart LR
    subgraph Triggers["Tool Calls"]
        BASH[Bash tool<br/>kubectl/helm/aws]
        MCP[MCP tools<br/>victoriametrics/grafana/slack]
    end

    subgraph PreHooks["PreToolUse"]
        KG[k8s-gate.sh<br/>tier enforcement<br/>exit 0 or 2]
        AP[audit-pre.sh<br/>extract INTENT<br/>log to JSONL]
    end

    subgraph PostHooks["PostToolUse"]
        AL[audit-log.sh<br/>capture stdout/stderr<br/>log to JSONL]
        MA[mcp-audit.sh<br/>capture tool + params<br/>log to MCP JSONL]
    end

    subgraph Logs["Audit Logs"]
        L1[logs/YYYY-MM-DD.jsonl<br/>K8s command audit]
        L2[logs/mcp-YYYY-MM-DD.jsonl<br/>MCP tool audit]
    end

    subgraph Tools["Inspection Tools"]
        AV[audit-view.py<br/>human-readable viewer]
        SLO[slo.py<br/>quality metrics]
        VER[verify.py<br/>output verifier]
    end

    BASH --> KG --> AP
    BASH --> AL
    MCP --> MA

    AP --> L1
    AL --> L1
    MA --> L2

    L1 --> AV
    L2 --> AV
    L1 --> SLO
    L2 --> SLO
```

## 6. Hook Registration Model

hooks-manifest.json 作为 source of truth，setup.sh 负责同步到本地环境。

```mermaid
flowchart TD
    subgraph Repo["Agent Repo (source of truth)"]
        HS[hooks/*.sh<br/>hook scripts]
        HM[hooks-manifest.json<br/>registration entries]
    end

    subgraph Setup["setup.sh"]
        S1[1. Symlink scripts<br/>→ ~/.claude/hooks/]
        S2[2. Merge manifest entries<br/>→ settings.json hooks section]
        S3[3. Normalize paths<br/>legacy cleanup]
    end

    subgraph Local["~/.claude/ (machine-local)"]
        LH[hooks/<br/>symlinks to repo]
        LS[settings.json<br/>personal config +<br/>hook entries from manifest]
    end

    HS --> S1 --> LH
    HM --> S2 --> LS
    LS --> S3
```
