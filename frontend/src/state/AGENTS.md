# src/state/

React Context + useReducer，不引入状态管理库。

| 文件 | 内容 |
|---|---|
| `auth.tsx` | 当前用户、启动时 `/auth/me` 恢复、登录/退出、资料更新、全局 401 处理 |
| `chat.tsx` | 瘦 Provider：组合 reducer 与各业务域 hook、组装 context value、持有路由跳转（新建会话后进入、删除当前会话后回首页） |
| `chatReducer.ts` | 纯 reducer：`ChatState`/`ChatAction`/`DisplayMessage` 与全部状态迁移（无 React 依赖）；会话列表、消息加载、发送回合、流事件结果都翻译成 action 在这里落地 |
| `chatActions.ts` | 业务域 hook：`useConversationList`（列表加载/刷新/合并、新建/重命名/删除）、`useMessageStream`（runTurn 流事件消费与 dispatch 翻译、消息加载与切换、后台生成轮询）、`useSending`（连发防重入锁 + 发送展示态的单一真相）、`useFigurePanel`（图示面板开合，useState 不进 reducer） |
