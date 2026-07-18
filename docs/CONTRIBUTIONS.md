# 成员贡献映射

> 更新：2026-07-18（首次 QA 同步后）
> 数据来源：`git shortlog -sne --all` + `git log --graph --oneline --all` + `git branch -avv`

## 真实提交统计

```bash
$ git shortlog -sne --all

    11  cnhyk <nai.ying.cnhyk@gmail.com>
     5  朱可心 <2140931620@qq.com>
     2  cnhky <nai.ying.cnhyk@gmail.com>
```

## 提交详情

```bash
$ git log --graph --oneline --decorate --all -20

*   48c2509 (HEAD -> feature/qa-delivery, origin/feature/qa-delivery)
|\    Merge remote-tracking branch 'origin/main' into feature/qa-delivery
| *   c58419b (origin/main) Merge pull request #2 from ANRlm/feature/leader-core
| |\
| | * 3293077 (origin/feature/leader-core) docs: make pull request reviews optional
| | * b195d55 test: close leader core failure cases
| | * 3e6c732 test: harden core contract validation
| | * dde303c docs: publish leader core integration guide
| | * 538aa91 build: wire single-process job service
| | * 530f987 feat: add recovery review and reporting services
| | * a1eabd6 feat: implement persistent job lifecycle
| | * 1e7bbf0 feat: add safe atomic job storage
| | * 0c65779 feat: define durable job and asset contracts
| |/
* 30e5b9d build: add deterministic release package validation
* 4a59e04 docs: record verified bugs and regression evidence
* a858f47 test: cover path safety recovery and delivery artifacts
* 20b40ea test: add normal and abnormal acceptance matrix
*   dc3313c Merge pull request #1 from ANRlm/agent/team-roster
|\
| * 8cdf5a0 docs: record team roster and Git identities
|/
* 1c583da chore: scaffold Aegis Review team contracts
```

## 分支状态

```bash
$ git branch -avv

* feature/qa-delivery             48c2509 [origin/feature/qa-delivery] Merge...
  main                            dc3313c [origin/main: behind 10]
  remotes/origin/main             c58419b Merge pull request #2
  remotes/origin/feature/qa-delivery 48c2509 Merge...
  remotes/origin/feature/leader-core 3293077 docs: make pull request reviews...
  remotes/origin/feature/backend-api  dc3313c Merge pull request #1
  remotes/origin/feature/cv-pipeline  dc3313c Merge pull request #1
  remotes/origin/feature/frontend-workbench dc3313c Merge pull request #1
```

## 成员与产出映射

| 角色 | 姓名 | GitHub | 分支 | 提交 | 可验证产出 | PR |
|---|---|---|---|---|---|---|
| 组长/产品集成 | 李佳铭 | ANRlm (cnhyk) | feature/leader-core → main | 13 | 契约骨架、JobStorage、JobService、状态机、恢复、改判、统计、产物白名单 | #1, #2 |
| 后端工程师 | 楼泽华 | llongzhanl | feature/backend-api | 0 | （未提交） | — |
| CV 算法工程师 | 戴瑜 | DangoSakana | feature/cv-pipeline | 0 | （未提交） | — |
| 前端工程师 | 孙畅 | Helen-444 | feature/frontend-workbench | 0 | （未提交） | — |
| 测试与交付工程师 | 朱可心 | xin-rabbit | feature/qa-delivery | 6 | 夹具、验收/安全/交付测试矩阵、测试报告、Bug 记录、验收清单、贡献表、截图索引、交付脚本 | Draft PR |

> 朱可心提交明细：
> - 20b40ea `test: add normal and abnormal acceptance matrix`
> - a858f47 `test: cover path safety recovery and delivery artifacts`
> - 4a59e04 `docs: record verified bugs and regression evidence`
> - 30e5b9d `build: add deterministic release package validation`
> - 48c2509 `Merge remote-tracking branch 'origin/main' into feature/qa-delivery`
> - （本阶段待提交）test/docs 更新

## 已合并 PR

| # | 标题 | 作者 | 状态 |
|---|---|---|---|
| 1 | add team roster via agent/team-roster | ANRlm | merged |
| 2 | leader core: storage + service + recovery + review + stats | ANRlm | merged |

## QA Draft PR

`https://github.com/ANRlm/aegis-review-workbench/compare/main...feature/qa-delivery`

PR 当前为 Draft，禁止合并（等待 CV → 后端 → 前端 合并）。
