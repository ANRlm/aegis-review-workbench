# 小组成员与贡献映射

成员按任务比重与固定分支进行真实协作。四名协作者邀请已于 2026-07-18 发出；成员接受邀请并确认 Git 身份后方可开始提交。

| 角色 | 比重 | 姓名 | 学号 | GitHub 用户名 | Git 提交邮箱（需本人确认已验证） | 固定分支 |
|---|---:|---|---|---|---|---|
| 组长/产品与集成 | 40% | 李佳铭 | 待补充 | ANRlm | nai.ying.cnhyk@gmail.com | `main` 或 `feature/leader-core` |
| 后端工程师 | 15% | 楼泽华 | 待补充 | llongzhanl | 2607909599@qq.com | `feature/backend-api` |
| CV 算法工程师 | 15% | 戴瑜 | 待补充 | DangoSakana | 1926846020@qq.com | `feature/cv-pipeline` |
| 前端工程师 | 15% | 孙畅 | 待补充 | Helen-444 | 904834073@qq.com | `feature/frontend-workbench` |
| 测试与交付工程师 | 15% | 朱可心 | 待补充 | xin-rabbit | 2140931620@qq.com | `feature/qa-delivery` |

当前契约骨架作者身份为：

```text
cnhyk <nai.ying.cnhyk@gmail.com>
GitHub: ANRlm
```

李佳铭已确认为本机组长账号，因此本次契约骨架提交计入组长贡献。不得为了匹配本表修改或伪造 Git 作者。

最终交付包名称从组长真实姓氏生成：

```text
李_A_day08/
```

## 成员首次提交前检查

每名成员需在自己的开发设备运行并确认：

```bash
git config user.name "本人姓名"
git config user.email "上表中已在 GitHub 验证的邮箱"
gh auth status
```

若邮箱尚未在 GitHub 验证，应先完成验证，或改用本人 GitHub 提供的 `noreply` 邮箱并同步更新本表。禁止共用组长 Git 身份或 GitHub 登录状态。
