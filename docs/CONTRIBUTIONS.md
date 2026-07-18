# 成员贡献映射

> 生成时间：2026-07-18 13:30 UTC+8
> 基础数据来源：`git shortlog -sne --all` + `git log --graph --oneline --all` + remote branches

## 真实提交统计

```bash
$ git shortlog -sne --all

     2  cnhyk <nai.ying.cnhyk@gmail.com>
     1  cnhky <nai.ying.cnhyk@gmail.com>
```

## 提交详情

```bash
$ git log --graph --oneline --decorate --all

*   dc3313c (HEAD -> main, origin/main, ...) Merge pull request #1 from ANRlm/agent/team-roster
|\
| * 8cdf5a0 (origin/agent/team-roster) docs: record team roster and Git identities
|/
* 1c583da chore: scaffold Aegis Review team contracts
```

## 成员与产出映射

| 角色 | 姓名 | GitHub | 分支 | 提交数（当前） | 可验证产出 | PR |
|---|---|---|---|---|---|---|
| 组长/产品集成 | 李佳铭 | ANRlm (cnhyk) | main | 3 | 契约骨架、团队花名册、README、PR merge | #1 |
| 后端工程师 | 楼泽华 | llongzhanl | feature/backend-api | 0 | （未提交） | — |
| CV 算法工程师 | 戴瑜 | DangoSakana | feature/cv-pipeline | 0 | （未提交） | — |
| 前端工程师 | 孙畅 | Helen-444 | feature/frontend-workbench | 0 | （未提交） | — |
| 测试与交付工程师 | 朱可心 | xin-rabbit | feature/qa-delivery | 0（本次自 PR 前） | 夹具、验收矩阵、测试、交付脚本 | 待创建 |

> 注：cnhyk 和 cnhky 均为组长 ANRlm 的不同 Git 配置别名。已确认
> cnhyk/cnhky <nai.ying.cnhyk@gmail.com> = 李佳铭。

## 远程分支状态

```bash
$ git ls-remote origin | Select-String "heads"

refs/heads/agent/team-roster    8cdf5a0
refs/heads/main                 dc3313c
refs/heads/feature/backend-api  dc3313c
refs/heads/feature/cv-pipeline  dc3313c
refs/heads/feature/frontend-workbench dc3313c
refs/heads/feature/leader-core  dc3313c
refs/heads/feature/qa-delivery  dc3313c
```

所有功能分支（不含 agent/team-roster）当前指向同一 commit `dc3313c`，
即为组长契约骨架的最终状态。四名成员均在各自的 feature 分支上工作但尚未
推送独立提交。

## 贡献核验命令

```bash
git shortlog -sne --all
git log --graph --oneline --decorate --all
git log --format='%h %an <%ae> %ad %s' --date=iso --all
gh pr list --state merged --limit 20
```

## 已合并 PR

| # | 标题 | 作者 | 合并方式 |
|---|---|---|---|
| 1 | add team roster via agent/team-roster | ANRlm | merge commit |

最终贡献核验将使用 `feature/qa-delivery` 合入后的最新 `main` 重新执行。
