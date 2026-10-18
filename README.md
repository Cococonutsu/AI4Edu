# AI4Edu

面向小学至高中学生的数学 AI 辅导网页应用。学生发送数学题（文字或图片），AI 老师通过追问引导学生自己完成推理。

## 环境要求

- Python 3.12 与 [uv](https://docs.astral.sh/uv/)
- Node.js 18 及以上
- 一个 OpenAI 兼容接口的多模态模型 API Key（默认使用智谱 `glm-5.3-flash`）

## 运行

### 1. 配置密钥

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，填写 `LLM_API_KEY`。

### 2. 安装依赖

```bash
cd backend && uv sync && cd ..
cd frontend && npm install && cd ..
```

### 3. 创建学生账号

系统不开放注册，账号由管理员创建：

```bash
cd backend && uv run ai4edu-admin create-user --username s001 --password '你的密码' --grade 8
```

`--grade` 为 1–12 年级。

### 4. 启动

```bash
./scripts/dev.sh
```

打开 http://localhost:5173 ，用上一步的账号登录。

## 测试

```bash
cd backend && uv run pytest ../tests/backend
cd frontend && npm test
```
