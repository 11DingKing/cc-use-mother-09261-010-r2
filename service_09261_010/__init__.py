"""课程教材匹配评估服务端包。"""
PROJECT_CODE = "service_09261_010"
from .workflow import ValidationError, Workflow
from .store import SQLiteStore
