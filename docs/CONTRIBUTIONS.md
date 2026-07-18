# 成员贡献映射

> 更新：2026-07-18（第三次更新）
> 数据来源：`git shortlog -sne HEAD` + `git log --graph --oneline --all`

## 真实提交统计

```bash
$ git shortlog -sne HEAD

    11  cnhyk <nai.ying.cnhyk@gmail.com>
     7  朱可心 <2140931620@qq.com>
     2  cnhky <nai.ying.cnhyk@gmail.com>
```

cnhky 与 cnhyk 为同一真实成员（李佳铭 / ANRlm）的不同 Git 拼写，原始输出保留不变。

## 朱可心提交详情（7 commits）

| 哈希 | 标题 | 日期 |
|------|------|------|
| f8ad6ab | docs: refresh QA baseline after leader core | 2026-07-18 |
| ccff8cd | test: activate leader core QA coverage | 2026-07-18 |
| 48c2509 | Merge remote-tracking branch 'origin/main' into feature/qa-delivery | 2026-07-18 |
| 30e5b9d | build: add deterministic release package validation | 2026-07-18 |
| 4a59e04 | docs: record verified bugs and regression evidence | 2026-07-18 |
| a858f47 | test: cover path safety recovery and delivery artifacts | 2026-07-18 |
| 20b40ea | test: add normal and abnormal acceptance matrix | 2026-07-18 |

## 分支状态

```bash
$ git branch -avv

* feature/qa-delivery              (origin/feature/qa-delivery)
  main                            dc3313c [origin/main: behind]
  remotes/origin/main             c58419b Merge pull request #2
  remotes/origin/feature/leader-core 3293077
  remotes/origin/feature/backend-api  dc3313c
  remotes/origin/feature/cv-pipeline  dc3313c
  remotes/origin/feature/frontend-workbench dc3313c
```

## 成员与产出

| 角色 | 姓名 | GitHub | 提交 | 状态 |
|---|---|---|---|---|
| 组长 | 李佳铭 | ANRlm (cnhyk) | 13 | 契约骨架 + 核心 PR #2 |
| 后端 | 楼泽华 | llongzhanl | 0 | 分支已创建，未提交 |
| CV | 戴瑜 | DangoSakana | 0 | 分支已创建，未提交 |
| 前端 | 孙畅 | Helen-444 | 0 | 分支已创建，未提交 |
| 测试交付 | 朱可心 | xin-rabbit | 7 | 夹具、验收/安全/交付矩阵、文档、交付脚本 |

## 已合并 PR

| # | 标题 | 作者 | 状态 |
|---|---|---|---|
| 1 | add team roster | ANRlm | merged |
| 2 | leader core: storage + service + recovery + review + stats | ANRlm | merged |

## 当前 PR 状态

GitHub 上当前不存在 QA Draft PR。

比较链接（不称为 PR）：
https://github.com/ANRlm/aegis-review-workbench/compare/main...feature/qa-delivery

QA 分支在 CV → 后端 → 前端 合并完成后由组长通知创建正式 PR。
