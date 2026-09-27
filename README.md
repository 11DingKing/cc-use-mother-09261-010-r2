# 课程教材匹配评估

纯 Python 服务端基础项目，提供版本化状态、幂等命令、SQLite 持久化和 JSON API 边界。

行为约定：提交入口先校验 id/actor/material（material 须为含 title 与 ISBN-10/13 的对象），校验失败不落任何记录；合格提交连同幂等键在同一原子单元内入队并持久化，写入中断整体回滚；非法流转与复核异常不改变现有记录；重启后从 SQLite 快照恢复记录与幂等键，待办列表与原始提交保持一一对应，重试不产生重复。

测试命令：python3 -m unittest discover -s tests -v

编译命令：python3 -m compileall -q service_09261_010 tests
