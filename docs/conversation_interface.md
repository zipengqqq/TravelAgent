# 对话接口文档接口对接说明
1. 以下所有接口设计调用时，都将user_id的值固定为1
2. 用户进入index.html，首先调用/conversation/list接口，查询所有对话列表
3. 用户点击某个对话，调用/conversation/select接口，查询该对话的所有交互记录
4. 用户点击“新对话按钮”，调用/conversation/add接口，新增一个对话记录
5. 当点击对话/新增对话按钮时，之后发送的信息，要调用/chat接口，将信息发送给AI
