# 采数请求写入用户信息导致 JSON 失败

2026-10-06。执行 3 采数失败，错误是日期时间不能序列化成 JSON。

## 现象

管理端调用检索 `POST /internal/qa/eval` 时，Feign 把请求体 `model_dump` 成 JSON。页面报采数失败，堆栈停在日期字段。

## 原因

`EvalQaAnswerRequestVo` 继承 `BaseVo`。`BaseVo` 会自动带上 `userInfo`，里面有登录时间和密码更新时间，都是 `datetime`。

检索侧只需要 `question`、`userId`、`releaseTag`、`taskId`。用户信息由检索自己按 `userId` 加载。这批日期不该进请求体，默认的 `model_dump` 也不会把 `datetime` 转成字符串。

## 处理

Feign 序列化时排除 `userInfo`，并用 `mode='json'`，剩下的日期字段按 JSON 可接受的形式写出。

文件：`knowledge-common/src/knowledge_common/common/feign/feign.py` 的 `_dump_model`。
