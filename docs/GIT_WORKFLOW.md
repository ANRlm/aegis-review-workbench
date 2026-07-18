# 五人 Git 协作规范

## 1. 身份要求

每名成员在自己的电脑和分支确认真实身份：

```bash
git config user.name "真实姓名或长期使用的 Git 名称"
git config user.email "本人 GitHub 已验证邮箱"
git config --get user.name
git config --get user.email
```

禁止使用其他成员姓名提交，禁止批量改写作者，禁止为了数量拆分无意义提交。

## 2. 分支

契约基线从 `main` 发布。成员执行：

```bash
git clone git@github.com:ANRlm/aegis-review-workbench.git
cd aegis-review-workbench
git switch main
git pull --ff-only
git switch -c feature/backend-api
```

四名成员分支固定为：

```text
feature/backend-api
feature/cv-pipeline
feature/frontend-workbench
feature/qa-delivery
```

组长在 `main` 完成自己的模块和集成；如果需开发较大组长功能，使用 `feature/leader-core` 并以普通 PR 合入。

组长核心 PR 合入前，其他功能分支不要锁定 `JobService` 的实现假设。合入后，
尚未提交功能代码的成员执行：

```bash
git fetch origin
git switch feature/<本人分支>
git merge --ff-only origin/main
```

若 `--ff-only` 失败，说明分支已有提交；停止并通知组长决定普通 merge 顺序，
禁止 rebase 或强推。

## 3. 提交

每个提交只表达一个可以解释和验证的成果。推荐前缀：

```text
feat: 新功能
test: 测试或测试素材
docs: 文档
fix: 真实 Bug 修复
build: Docker、Conda 或依赖
```

提交前：

```bash
git status --short
git diff --check
pytest -q
```

使用明确路径暂存，不把他人文件、缓存、输出目录或非最终权重带入提交：

```bash
git add aegis_review/api.py aegis_review/errors.py tests/test_api.py docs/API.md
git commit -m "feat: implement job API contract"
```

## 4. PR 与合并

```bash
git push -u origin feature/backend-api
gh pr create --base main --head feature/backend-api
```

规则：

- 每个 PR 至少由一名其他成员审阅；
- 合并顺序为 CV → 后端 → 前端 → QA；
- 使用 GitHub 的 **Create a merge commit**；
- 禁止 Squash and merge；
- 禁止 Rebase and merge；
- 功能问题由文件责任人继续在原分支修复；
- 组长只提交真实集成、环境和契约协调修改。

## 5. 冲突处理

成员不要直接改写其他角色独占路径。发现契约冲突时：

1. 停止当前实现；
2. 在 PR 描述或群聊写明涉及的接口、字段和文件；
3. 由组长决定是否修改契约；
4. 契约变更先单独合入 `main`；
5. 成员再合并最新 `main` 并继续。

不要用 `git checkout --theirs`、强推或大范围格式化掩盖冲突。

## 6. 贡献核验

最终验收前运行：

```bash
git shortlog -sne --all
git log --graph --oneline --decorate --all
git log --format='%h %an <%ae> %ad %s' --date=iso --all
gh pr list --state merged --limit 20
```

贡献表需要把成员、分支、PR、提交和可演示产出逐项对应。提交数量只是辅助证据，现场说明和真实可运行结果优先。
