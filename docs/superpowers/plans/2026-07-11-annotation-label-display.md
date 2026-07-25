# 标注框类别名称显示实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 人工标注的矩形框和 OBB 框显示紧凑的类别名称，而不是内部类别 ID。

**Architecture:** `AnnotationCanvas` 已接收数据集类别，并通过标注的 `labelId` 解析类别。保持数据模型不变，仅渲染解析后的类别名称或用户可读的回退文案，并用现有 SVG 标签样式缩小显示尺寸。

**Tech Stack:** React、TypeScript、Vitest、SVG、CSS、Vite。

## 全局约束

- 仅修改矩形框和 OBB 框的前端显示。
- 不修改已保存的 `labelId`、API、类别管理、导出和训练流程。
- 类别未匹配时显示“未分类”，画布中不得显示内部 ID。

---

### Task 1：覆盖可读标签渲染

**Files:**

- Modify: `frontend/src/components/AnnotationCanvas.test.tsx`
- Modify: `frontend/src/components/AnnotationCanvas.tsx:119-133`
- Modify: `frontend/src/styles.css` 中已有的 `.annotation-label` 和 `.annotation-label-bg` 规则

**Interfaces:**

- Consumes: `Shape.labelId: string` 和传给 `AnnotationCanvas` 的 `AnnotationCategory { id, name, color }`。
- Produces: 每个矩形/OBB SVG 标签显示解析后的 `category.name`；未匹配时显示 `未分类`。

- [ ] **Step 1：先写失败测试**

将现有的类别标签断言替换为以下两个测试：

```tsx
it('shows the category name instead of the internal category ID on a rectangle', () => {
  const onChange = vi.fn()
  render(<AnnotationCanvas asset={asset} task="detect" labelId="category-uuid-123" categories={[{ id: 'category-uuid-123', name: 'car', color: '#e36a22' }]} shapes={[{ id: 'box-1', labelId: 'category-uuid-123', kind: 'rectangle', points: [[0.1, 0.1], [0.6, 0.6]] }]} onChange={onChange} />)
  expect(screen.getByText('car')).toBeInTheDocument()
  expect(screen.queryByText(/category-uuid-123/)).not.toBeInTheDocument()
})

it('shows an uncategorized fallback instead of an unmatched internal ID', () => {
  const onChange = vi.fn()
  render(<AnnotationCanvas asset={asset} task="detect" labelId="current-category" categories={[]} shapes={[{ id: 'box-1', labelId: 'missing-uuid', kind: 'rectangle', points: [[0.1, 0.1], [0.6, 0.6]] }]} onChange={onChange} />)
  expect(screen.getByText('未分类')).toBeInTheDocument()
  expect(screen.queryByText(/missing-uuid/)).not.toBeInTheDocument()
})
```

- [ ] **Step 2：确认测试按预期失败**

运行 `npm test -- --run src/components/AnnotationCanvas.test.tsx`。当前代码会渲染 `shape.labelId`，且没有“未分类”回退，因此测试应失败。

- [ ] **Step 3：最小实现**

在 `renderShape` 的矩形/OBB 分支中增加：

```tsx
const displayLabel = category?.name ?? '未分类'
const labelWidth = Math.max(width, Math.max(14, displayLabel.length * 4.5))
```

并使用 `displayLabel` 替换当前包含 `shape.labelId` 的 SVG 文本；将标签背景高度降为 `3.2`、顶部偏移改为 `3.6`，并把文字基线改为 `y - 1.2`。同步把 `.annotation-label` 调整为紧凑字号。

- [ ] **Step 4：确认目标测试通过**

运行 `npm test -- --run src/components/AnnotationCanvas.test.tsx`，预期两个新测试以及现有指针/画笔测试全部通过。

- [ ] **Step 5：运行回归验证**

依次运行 `npm test -- --run` 和 `npm run build`，预期所有前端测试通过，且 Vite 构建没有 TypeScript 或打包错误。

- [ ] **Step 6：提交聚焦改动**

```powershell
git add frontend/src/components/AnnotationCanvas.tsx frontend/src/components/AnnotationCanvas.test.tsx frontend/src/styles.css
git commit -m "fix: show category names on annotation boxes"
```
