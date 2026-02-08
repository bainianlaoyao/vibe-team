# Frontend Vue 3 像素级复刻任务清单

## 项目概述
将 `AImanager/demo` (React 18 + TypeScript) 像素级复刻到 `frontend/` (Vue 3 + TypeScript)

## 技术栈映射

| React 原版 | Vue 3 版本 |
|-----------|-----------|
| React 18.2 | Vue 3.x |
| React Router DOM 6 | Vue Router 4 |
| React Context | Pinia |
| @phosphor-icons/react | @phosphor-icons/vue |
| @dnd-kit | vuedraggable (待添加) |
| Tailwind CSS 3.3.6 | Tailwind CSS 3.x |

---

## 进度追踪

### Phase 1: 项目初始化 ✅
- [x] 创建 Vue 3 + Vite 项目
- [x] 安装依赖 (vue-router, pinia, @phosphor-icons/vue, tailwindcss)
- [x] 配置 tailwind.config.js (设计 token)
- [x] 配置 postcss.config.js
- [x] 创建 style.css (全局样式 + CSS 变量)

### Phase 2: 类型与数据 🔄
- [x] 创建 `src/types/index.ts` - 类型定义
- [ ] 创建 `src/data/mockData.ts` - Mock 数据
- [ ] 创建 `src/data/mockFiles.ts` - 文件树 Mock 数据

### Phase 3: 状态管理 ⏳
- [ ] 创建 `src/stores/fileSystem.ts` - Pinia store (替代 FileSystemContext)

### Phase 4: 公共组件 ⏳
- [ ] `src/components/Avatar.vue`
- [ ] `src/components/TaskCard.vue`

### Phase 5: 布局组件 ⏳
- [ ] `src/components/layout/LeftSidebar.vue`
- [ ] `src/components/layout/TopNav.vue`
- [ ] `src/components/layout/ProjectHeader.vue`
- [ ] `src/components/layout/ViewTabs.vue`

### Phase 6: 视图页面 ⏳
- [ ] `src/views/DashboardView.vue`
- [ ] `src/views/InboxView.vue`
- [ ] `src/views/ChatView.vue`
- [ ] `src/views/TableView.vue`
- [ ] `src/views/KanbanView.vue`
- [ ] `src/views/CustomizeView.vue`
- [ ] `src/views/WhiteboardView.vue`
- [ ] `src/views/FilesView.vue`
- [ ] `src/views/FileViewer.vue`
- [ ] `src/views/RolesView.vue`
- [ ] `src/views/ApiView.vue`

### Phase 7: 路由与入口 ⏳
- [ ] 创建 `src/router/index.ts` - Vue Router 配置
- [ ] 更新 `src/App.vue` - 主布局逻辑
- [ ] 更新 `src/main.ts` - 入口文件
- [ ] 更新 `index.html` - HTML 模板

---

## 路由结构

```
/                   → DashboardView
/inbox              → InboxView
/chat               → ChatView
/agents             → redirect to /agents/table
/agents/table       → TableView
/agents/kanban      → KanbanView
/agents/customize   → CustomizeView
/workflow           → WhiteboardView
/files              → FilesView
/files/view/:id     → FileViewer
/roles              → RolesView
/api                → ApiView
```

---

## 关键转换模式

### 1. React useState → Vue ref/reactive
```typescript
// React
const [count, setCount] = useState(0);

// Vue
const count = ref(0);
```

### 2. React useEffect → Vue onMounted/watch
```typescript
// React
useEffect(() => { ... }, [deps]);

// Vue
watch([deps], () => { ... });
onMounted(() => { ... });
```

### 3. React Context → Pinia
```typescript
// React
const { value } = useContext(MyContext);

// Vue
const store = useMyStore();
const { value } = storeToRefs(store);
```

### 4. React Router NavLink → Vue RouterLink
```vue
<!-- React -->
<NavLink to="/path" className={({ isActive }) => ...}>

<!-- Vue -->
<RouterLink to="/path" v-slot="{ isActive }">
```

### 5. React 条件渲染 → Vue v-if/v-show
```vue
<!-- React -->
{condition && <Component />}

<!-- Vue -->
<Component v-if="condition" />
```

---

## 注意事项

1. **Tailwind 类名完全保留** - 样式系统框架无关
2. **TypeScript 类型直接复用** - 接口定义相同
3. **Phosphor Icons API 差异** - Vue 版本使用 kebab-case 属性
4. **事件处理差异** - `onClick` → `@click`, `onChange` → `@update:modelValue`
5. **v-model 双向绑定** - 替代受控组件模式

---

## 验收标准

- [ ] 所有路由可访问
- [ ] 侧边栏导航正常
- [ ] 主题样式一致
- [ ] 响应式布局正常
- [ ] 组件交互正常
- [ ] TypeScript 无报错
- [ ] `npm run dev` 可运行
- [ ] `npm run build` 可构建

---

## 当前工作焦点

**下一步**: 完成 Phase 2 数据文件创建，然后依次完成 Phase 3-7
