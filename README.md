# 12306 自动化抢票系统

这是一个基于 Python FastAPI 和 Vue 3 开发的 12306 自动化抢票系统。包含后端 API 服务、前端管理界面以及一些独立的自动化脚本。

## 目录结构

- `backend/`: FastAPI 后端服务
    - `app/`: 应用代码
    - `data/`: 数据存储 (日志, Session 等)
- `frontend/`: Vue 3 + Vite 前端项目

## 环境准备

### 后端环境
- Python 3.10+

### 前端环境
- Node.js 16+
- npm 或 yarn

## 快速开始

### 1. 启动后端服务

进入 `backend` 目录，安装依赖并启动服务：

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Swagger API 文档地址: http://localhost:8000/docs

### 2. 启动前端界面

```bash
cd frontend
npm install
npm run dev
```

访问地址: http://localhost:5173

- 本项目仅供学习交流使用，请勿用于非法用途。

## 每日监控 + 企业微信确认

本分支新增“每天定时监控、发现余票后由企业微信确认再下单”的模式。原有一次性抢票模式仍然保留。

流程：

```text
每天固定时间
  ↓
按指定车次 / 席别查询余票
  ↓
发现余票
  ↓
企业微信智能机器人发送确认卡片
  ↓
用户点击「确认预定」
  ↓
服务端重新查询同一日期 / 车次 / 席别
  ↓
仍有票才提交 12306 订单
  ↓
企业微信通知订单号
  ↓
用户前往官方 12306 完成支付
```

### 企业微信智能机器人配置

后端使用企业微信官方 `wecom-aibot-python-sdk` WebSocket 长连接 SDK。创建企业微信智能机器人后，将 Bot ID 和 Secret 配置到环境变量中。

可以从根目录的 `.env.example` 复制所需变量：

```bash
WECOM_BOT_ENABLED=true
WECOM_BOT_ID=your_bot_id
WECOM_BOT_SECRET=your_bot_secret
WECOM_BOT_CHAT_ID=your_chat_id
WECOM_ALLOWED_USER_IDS=user_a,user_b
WECOM_CONFIRM_EXPIRE_SECONDS=60
```

`WECOM_ALLOWED_USER_IDS` 可留空；配置后只有白名单中的企业微信用户可以点击确认触发下单。确认有效期限制在 15–300 秒，默认 60 秒。

> 不要把 Bot Secret 提交到 Git 仓库。生产环境请通过 Docker 环境变量、密钥管理服务或私有 `.env` 注入。

### 创建每日任务

在“创建抢票任务”页面选择：

- 任务模式：`每天自动监控`
- 每日启动时间：例如 `07:00`
- 日期策略：
  - `固定乘车日期`：每天监控同一个日期；或
  - `每天动态计算`：例如偏移 `14` 天，表示每天监控当天往后第 14 天的车票
- 指定车次：可同时填多个，例如 `G101`、`G103`
- 席别优先级：例如二等座、一等座
- 企业微信确认：每日任务强制启用

每日任务不会走原有 `auto_submit` 直接下单路径。发现票后必须先完成企业微信确认，并且系统会在确认后重新查一次最新余票。

### 安全与行为边界

- 不保存或复用第一次查票得到的 `secret_str` 来提交订单。
- 一个确认 token 最多触发一次下单尝试，重复按钮事件不会重复下单。
- 不绕过验证码、风控或访问频率限制。
- 不自动支付；订单提交后仍需在官方 12306 完成支付。
- 老版本 SQLite 数据库启动时会自动补充本功能需要的新字段，无需删除原数据库。

## 工程治理

本项目使用 Spec Kit 宪章记录工程原则，见 `.specify/memory/constitution.md`。
需求、计划和任务应通过宪章检查，重点覆盖风险驱动测试、结构化错误处理和渐进式可维护性。

## Docker 一键运行（前后端）

已提供前后端容器化配置，执行以下命令即可一键启动：

```bash
# 在项目根目录执行
docker compose up -d --build
```

启动后访问：

- 前端页面: http://localhost:5173
- 后端 API 文档: http://localhost:8000/docs

### Docker 配置企业微信

在 `docker-compose.yml` 的 backend 环境变量或你自己的 `.env` 中注入上述 `WECOM_*` 配置，然后重新构建/启动：

```bash
docker compose up -d --build
```

### 常用命令

```bash
docker compose ps
docker compose logs -f
docker compose logs -f backend
docker compose down
```

### 数据持久化

`docker-compose.yml` 已将宿主机目录 `backend/data` 挂载到容器内 `/app/backend/data`，数据库、会话、日志会被保留。

### 说明

- 该 Docker 方案为 Web 版前后端一键运行，不包含 Electron 桌面 GUI 容器化。
- 前端通过 Nginx 反向代理 `/api` 和 WebSocket 到后端容器，无需改动现有业务 API 调用。

## Electron 桌面应用打包（Windows）

本项目支持将前后端一起打包为 Windows 桌面应用（内置后端可执行文件）。

### 环境要求

- Python 3.10+
- Node.js 16+
- npm 8+

### 一键构建（推荐）

```bash
python build_app.py --target windows
```

该命令会自动完成：

1. 后端 PyInstaller 构建
2. 前端 Vite 构建
3. Electron Builder 打包（Windows NSIS 安装包）

### 构建产物

- 安装包输出目录：`frontend/release/`
- 典型产物：`12306抢票助手-1.0.0-x64.exe`

### 常用参数

```bash
python build_app.py --clean
python build_app.py --skip-backend --target windows
python build_app.py --skip-frontend --target windows
```
