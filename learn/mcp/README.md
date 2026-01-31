# PostgreSQL MCP 服务器

一个使用 MCP 协议查询 PostgreSQL 数据库的服务器。

## 功能

- `execute_sql` - 执行任意 SQL 查询
- `list_tables` - 列出所有表
- `describe_table` - 获取表结构

## 安装

```bash
cd learn/mcp
pip install -r requirements.txt
```

## 使用

### 1. 直接运行（测试）

```bash
python pg_server.py
```

### 2. 配置到 Claude Code

在你的 Claude Code 配置文件中添加（通常在 `~/.claude_code_config.json` 或 `~/.config/claude-code/config.json`）：

```json
{
  "mcpServers": {
    "postgres": {
      "command": "python",
      "args": ["C:/Users/apeng/PycharmProjects/TravelAgent/learn/mcp/pg_server.py"],
      "env": {
        "POSTGRES_URI": "postgresql://postgres:Z@y9qwY8FQN}@101.33.236.84:5432/postgres?sslmode=disable"
      }
    }
  }
}
```

### 3. 使用示例

配置完成后，在 Claude Code 中：

```
查询 postgres 数据库中所有的表
```

```
查看 users 表的结构
```

```
执行 SELECT * FROM users LIMIT 10
```

## 配置说明

数据库连接信息从环境变量 `POSTGRES_URI` 读取，当前配置在项目根目录的 `.env` 文件中。

## 依赖

- `mcp` - MCP 协议实现
- `psycopg2-binary` - PostgreSQL 数据库驱动
- `python-dotenv` - 环境变量加载
