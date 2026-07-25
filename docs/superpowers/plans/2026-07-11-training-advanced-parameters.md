# 新建训练高级参数折叠 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 默认收起新建训练表单中的非核心训练参数。

**Architecture:** `TrainingPage` 将字段分为核心字段和高级字段。高级字段置于原生 `details` 元素，避免新增依赖并保留浏览器可访问性语义。

**Tech Stack:** React 19、TypeScript、Vitest、Testing Library。

## Global Constraints

- 只修改训练表单的展示层，不改变提交字段、默认值或 API 契约。
- 保持资源和依赖均在项目目录内。

---

### Task 1: 为高级参数默认折叠建立组件测试

**Files:**
- Create: `frontend/src/pages/TrainingPage.test.tsx`
- Modify: `frontend/src/pages/TrainingPage.tsx`

**Interfaces:**
- Consumes: `TrainingPage` React 页面组件。
- Produces: 默认关闭、可展开的“高级训练参数”区域。

- [ ] **Step 1: 写入失败测试**

```tsx
expect(screen.getByText('高级训练参数').closest('details')).not.toHaveAttribute('open')
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `npm test -- TrainingPage.test.tsx`
Expected: FAIL，因为高级参数区域尚不存在。

- [ ] **Step 3: 实现最小表单分组**

```tsx
<details className="training-advanced">
  <summary>高级训练参数</summary>
  <div className="form-grid">…高级字段…</div>
</details>
```

- [ ] **Step 4: 运行测试、类型检查和构建**

Run: `npm test -- TrainingPage.test.tsx; npm run lint; npm run build`
Expected: 三项命令均成功。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/TrainingPage.tsx frontend/src/pages/TrainingPage.test.tsx docs/superpowers/specs/2026-07-11-training-advanced-parameters-design.md docs/superpowers/plans/2026-07-11-training-advanced-parameters.md
git commit -m "feat: collapse advanced training parameters"
```
