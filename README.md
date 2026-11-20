# CodeFlow

CodeFlow 面向本地项目的静态调用关系分析。当前版本提供 FastAPI 后端、Vue 3 + TypeScript 前端和服务连接检查。

## 本地开发

需要 Python 3.11+ 和 Node.js 22.12+。在仓库根目录启动后端。

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ./backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload --reload-dir backend
```

Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1` 激活虚拟环境。

另开一个终端启动前端。

```sh
cd frontend
npm ci
npm run dev
```

打开 Vite 输出的本地地址。页面显示「分析服务已连接」时，前端已通过 Vite 代理访问后端的 `GET /api/health`。在 `frontend/` 下运行 `npm run build` 可以执行类型检查并生成静态资源。

## 分析模块规划

| 路径 | 职责 |
| --- | --- |
| `backend/app/scanner.py` | 只读枚举目标项目的源码 |
| `backend/app/parsers/spring.py` | 接入 Java 分析器，提取方法调用、Spring 路由和注入线索 |
| `backend/app/parsers/vue.py` | 接入 Vue 分析器，提取模板事件、脚本调用和 HTTP 请求 |
| `backend/tools/java-analyzer/` | Java 和 Spring 静态分析工具 |
| `backend/tools/vue-analyzer/` | Vue 单文件组件和 JavaScript / TypeScript 静态分析工具 |
| `backend/app/analyzer.py` | 统一分析结果，将 Vue HTTP 请求匹配到 Spring 路由 |

第一个分析样例计划验证从 Vue 按钮到 Spring Service 的链路，并为图中的每段关系保留源码位置。
