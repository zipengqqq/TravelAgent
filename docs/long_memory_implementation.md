# 长期记忆功能实施计划

## 目标
在用户对话或规划行程时，能够检索到长期记忆，为 AI 提供更个性化的回答。

## 设计原则
只使用 `memory` 表存储对话历史，通过语义检索获取相关记忆，让 AI 自己从对话中提取用户偏好（饮食、预算、兴趣等）。

---

## 现状分析

### 已有组件
| 组件 | 文件 | 状态 |
|------|------|------|
| MemoryRAG 类 | `graph/memory_rag.py` | ✅ 已实现 |
| Memory 实体 | `entity/memory_entity.py` | ✅ 已实现 |

### 需要实现的功能
1. **记忆存储**：何时将对话内容存储到长期记忆？
2. **记忆检索**：何时从长期记忆检索？
3. **记忆集成**：如何将检索到的记忆集成到提示词中？

---

## 实施步骤

### 步骤 1：修改 `graph/config.py` - 扩展 State

在 `PlanExecuteState` 中添加 `memories` 字段：

```python
class PlanExecuteState(TypedDict):
    question: str
    plan: List[str]
    past_steps: List[Tuple[str, str]]
    response: str
    route: str
    messages: Annotated[List[Tuple], operator.add]
    user_id: int
    memories: List[str]          # 新增：检索到的长期记忆
```

---

### 步骤 2：新增 `memory_retrieve_node` - 检索记忆节点

在 `graph/nodes.py` 中新增节点：

```python
from graph.memory_rag import memory_rag

def memory_retrieve_node(state: PlanExecuteState):
    """检索长期记忆"""
    user_id = state["user_id"]
    question = state["question"]

    # 基于当前问题检索相关历史记忆
    memories = memory_rag.search_memories(user_id, question, top_k=5)
    logger.info(f"检索到 {len(memories)} 条相关记忆")

    return {"memories": memories}
```

---

### 步骤 3：新增 `memory_save_node` - 保存记忆节点

```python
def memory_save_node(state: PlanExecuteState):
    """保存对话内容到长期记忆"""
    user_id = state["user_id"]
    question = state["question"]
    response = state.get("response", "")

    if not response:
        return {}

    # 将对话内容保存为记忆
    conversation = f"用户：{question}\nAI：{response}"
    memory_rag.add_memory(user_id, conversation)
    logger.info(f"已保存对话到长期记忆")

    return {}
```

---

### 步骤 4：修改提示词 - 集成记忆

在 `graph/prompts.py` 中修改相关提示词：

#### 4.1 修改 `route_prompt`
```python
route_prompt = """
# 你是一个专业的意图分类器

## 相关历史记忆
{memories}

## 意图分类
只有两种意图：
- planner: 用户明确要求"做规划/制定计划/安排步骤/输出行程或待办清单"。
  - 典型表达：规划、制定计划、安排一下、做个行程、路线怎么走、几天怎么玩、给我一个步骤清单。
  - 注意：只有出现"要一个计划/行程/步骤"的诉求才选 planner。
- direct_answer: 除 planner 以外的所有情况。
  - 包括：闲聊、情绪表达、常识问答、解释概念、给建议、以及基于对话历史的回顾/总结/确认/列举。
  - 关键规则：如果用户在问"刚才/之前/上面/你提到过/我们聊到的……是什么"，这是在引用对话历史，不是在要规划，一律选 direct_answer。

## 输出格式
输出格式为JSON，字段为route（字符串）

## 用户输入
{user_request}
"""
```

#### 4.2 修改 `direct_answer_prompt`
```python
direct_answer_prompt = """
# 你是一个专业的旅行助手

## 相关历史记忆
{memories}
（这些是用户之前的对话记录，你可以从中了解用户的偏好和需求）

## 当前问题
{user_request}

## 对话历史
{messages}
"""
```

#### 4.3 修改 `planner_prompt`
```python
planner_prompt = """
# 你是一个专业的旅游规划专家

## 相关历史记忆
{memories}
（这些是用户之前的对话记录，你可以从中了解用户的偏好和需求）

## 任务说明
根据用户的旅行需求，制定一个清晰、可行、按顺序排列的多步骤计划。
计划应覆盖从出发准备到行程结束的关键环节，如交通、住宿、景点、餐饮等。

## 输出格式
仅输出 JSON，包含一个字段：
- steps：字符串数组（string[]），每个元素为一个具体、可执行的步骤。

不要包含任何额外文本、解释、注释或 Markdown。

## 用户问题
{user_request}

## 对话历史
{messages}
"""
```

---

### 步骤 5：修改节点 - 传入记忆参数

在 `graph/nodes.py` 中修改各节点，传入记忆参数：

```python
def router_node(state: PlanExecuteState):
    logger.info("🚀路由师正在判断意图")
    question = state["question"]

    prompt = route_prompt.format(
        user_request=question,
        memories=state.get("memories", [])
    )
    # ... 其余代码不变 ...

def direct_answer_node(state: PlanExecuteState):
    logger.info("🚀直接回答中")
    question = state["question"]
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = direct_answer_prompt.format(
        user_request=question,
        messages=messages,
        memories=state.get("memories", [])
    )
    # ... 其余代码不变 ...

def planner_node(state: PlanExecuteState):
    logger.info("🚀规划师正在规划任务")
    question = state["question"]
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = planner_prompt.format(
        user_request=question,
        messages=messages,
        memories=state.get("memories", [])
    )
    # ... 其余代码不变 ...
```

---

### 步骤 6：修改工作流 - 集成记忆节点

在 `graph/workflow.py` 中添加记忆节点到工作流：

```python
from graph.nodes import router_node, planner_node, executor_node, direct_answer_node, reflect_node, memory_retrieve_node, memory_save_node

workflow = StateGraph(PlanExecuteState)

# 添加节点
workflow.add_node("router", router_node)
workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)
workflow.add_node("reflect", reflect_node)
workflow.add_node("direct_answer", direct_answer_node)
workflow.add_node("memory_retrieve", memory_retrieve_node)      # 新增
workflow.add_node("memory_save", memory_save_node)              # 新增

# 定义边
workflow.add_edge(START, "memory_retrieve")                      # 先检索记忆
workflow.add_edge("memory_retrieve", "router")

# router 条件分支
workflow.add_conditional_edges(
    "router",
    route_by_intent,
    {
        "planner": "planner",
        "direct_answer": "direct_answer"
    }
)

# direct_answer 流程
workflow.add_edge("direct_answer", "memory_save")
workflow.add_edge("memory_save", END)

# planner 流程
workflow.add_edge("planner", "executor")
workflow.add_edge("executor", "reflect")

# reflect 流程
workflow.add_conditional_edges(
    "reflect",
    should_end,
    {
        True: "memory_save",    # 完成时保存记忆
        False: "executor"
    }
)
workflow.add_edge("memory_save", END)
```

---

### 步骤 7：删除不需要的代码

删除 `entity/user_profiles_entity.py` 文件（如果不需要）。

删除 `graph/nodes.py` 中的 `profile_node` 函数。

删除 `graph/prompts.py` 中的 `profile_prompt`。

删除 `graph/nodes.py` 中对 `UserProfile` 的导入。

---

## 工作流程图

```
用户请求
    ↓
memory_retrieve (检索长期记忆)
    ↓
router (意图分类)
    ├─→ planner (规划) → executor → reflect ──┐
    │                                            │
    └─→ direct_answer (直接回答) ──────────────┤
                                                 │
                                                 ↓
                                           memory_save (保存对话到长期记忆)
                                                 ↓
                                                END
```

---

## 测试步骤

### 测试 1：记忆检索
```
发送："我上次提到的餐厅有哪些？"
预期：检索到相关的历史对话记录
```

### 测试 2：偏好记忆
```
发送："我喜欢吃辣的菜"
发送："推荐一些美食"
预期：AI 基于检索到的历史，推荐辣菜
```

### 测试 3：规划场景
```
发送："规划去成都三天行程，预算中等"
发送："再规划一次行程"
预期：第二次规划时，考虑之前的预算信息
```

### 测试 4：日志检查
```
- 确认 memory_retrieve 有日志：检索到 N 条相关记忆
- 确认 memory_save 有日志：已保存对话到长期记忆
```

---

## 注意事项

1. **异常处理**：记忆检索失败时使用空列表 `[]`，不影响主流程
2. **隐私安全**：敏感信息不应存储到长期记忆
3. **性能优化**：考虑记忆数量限制（如只保留最近 N 条）
4. **Token 消耗**：`top_k` 不宜过大，避免超过 token 限制
