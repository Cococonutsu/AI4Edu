# src/components/

只负责展示与交互的 React 组件，网络请求通过 `state/` 与 `api/`。

| 文件 | 内容 |
|---|---|
| `Icons.tsx` | 内联 SVG 图标，不引入图标库 |
| `MarkdownContent.tsx` | react-markdown + remark-gfm/math + rehype-katex，不渲染原始 HTML |
| `MessageBubble.tsx` | 用户/助手气泡、图片缩略图、等待状态（阶段文案 + 已等秒数 + 工具状态 + 进度走线） |
| `ImageLightbox.tsx` | 点击图片后的放大查看层 |
| `MessageList.tsx` | 消息列表、欢迎语、加载/错误状态、自动滚动 |
| `FigureBoard.tsx` | JSXGraph 画布：点、线段、多边形、曲线、圆；坐标是闭包，随参数重算；坐标恰为参数的点可直接拖动 |
| `FigurePanel.tsx` | 右侧图示面板：标题、提示、画布、观察值、参数滑块、移动轨迹演示；可收起为窄条 |
| `Composer.tsx` | 多行输入、Enter/输入法处理、图片选择/粘贴/拖入与上传 |
| `ConversationSidebar.tsx` | 会话列表、新建、重命名、删除、用户信息与退出；点击用户卡片打开个人设置 |
| `SettingsDialog.tsx` | 个人设置弹层：修改显示名与年级，客户端校验后保存 |
