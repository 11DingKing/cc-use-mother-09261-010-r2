# 课程教材匹配评估

纯 Python 服务端基础项目，提供版本化状态、幂等命令、SQLite 持久化和 JSON API 边界。

## 行为约定

- 入口先校验：`id` 需为 1–64 位字母数字（可含 `-`、`_`，须以字母数字开头），`actor`、`state`、`idempotency_key` 需为非空字符串；不合格直接拒绝（422），不写入任何记录。
- 写入原子化：校验通过后，案例先在单条 SQLite 事务中落库，再提交到内存；校验失败、写入中断或复核异常都不会留下可被误认成正式任务的半成品记录。
- 幂等：`idempotency_key` 随记录持久化，重试返回原记录，不产生重复待办。
- 恢复一致：重启后从 SQLite 重建内存状态，接口待办与原始提交一一对应。

测试命令：python3 -m unittest discover -s tests -v

编译命令：python3 -m compileall -q service_09261_010 tests
