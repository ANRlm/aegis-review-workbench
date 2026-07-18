# 成员贡献核验

> 生成：2026-07-18
> shortlog 快照：`fce0281`（最终文档提交前）
> 数据来源：`git shortlog -sne --all` 与 `gh pr list --state all --limit 100`

## 真实提交统计

```text
24  cnhyk <nai.ying.cnhyk@gmail.com>
24  孙畅 <904834073@qq.com>
15  楼泽华 <2607909599@qq.com>
14  朱可心 <2140931620@qq.com>
 7  cnhky <nai.ying.cnhyk@gmail.com>
 7  戴瑜 <1926846020@qq.com>
```

`cnhyk` 与 `cnhky` 是李佳铭同一邮箱、同一 GitHub 身份的历史拼写，原始
shortlog 不改写；快照中合并后为 31 个 authored commits。朱可心的 14 条
raw shortlog 包含一次普通 merge commit `48c2509`，其本人独立功能/测试/
文档提交为计划约定的 **13 个 non-merge commits**，不改作者、不追加伪贡献。

## 成员映射与交付

| 角色 | 姓名 | 学号 | GitHub | 快照提交 | 主要产出 |
|---|---|---|---|---:|---|
| 组长 40% | 李佳铭 | 20231060257 | ANRlm | 31（合并别名） | 架构、存储、状态机、集成、运行环境、最终 QA/交付 |
| 后端 15% | 楼泽华 | 20231060057 | llongzhanl | 15 | API、上传校验、错误包络、安全下载、测试 |
| CV 15% | 戴瑜 | 20231060139 | DangoSakana | 7 | 数据、训练、CV 管线、规则、证据与产物 |
| 前端 15% | 孙畅 | 20231340027 | Helen-444 | 24 | 三栏工作台、轮询、审核、下载、响应式与契约测试 |
| QA 15% | 朱可心 | 20231060277 | xin-rabbit | 13 non-merge | 验收矩阵、安全测试、发布脚本与阶段 QA 文档 |

本轮组长 QA 收尾提交为 `f960482`、`1331d46`、`25c799c`、`6b0342e`、
`fce0281` 及此后的最终证据/发布提交；它们不计入朱可心的 15% 贡献。

## Pull Request 核验

| PR | 标题/用途 | 作者 | 状态 |
|---:|---|---|---|
| #1 | 团队成员与 Git 身份 | ANRlm | merged |
| #2 | 组长持久化核心 | ANRlm | merged |
| #3 | 旧前端分支 | Helen-444 | closed，未作为最终实现合入 |
| #4 | CV 管线与训练模型 | DangoSakana | merged |
| #5 | 后端 API | llongzhanl | merged |
| #6 | 干净前端工作台 | Helen-444 | merged |
| #7 | 集成与 CI 基线 | ANRlm | merged |
| #8 | 运行时绑定训练模型 | ANRlm | merged |

所有已合并功能 PR 均使用普通 merge commit；没有 squash、rebase 或伪造作者。
