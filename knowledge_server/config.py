from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8900
    db_path: str = ""
    master_api_key: str = ""
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> ServerConfig:
        db_default = str(Path(__file__).parent.parent / "knowledge_server.db")
        return cls(
            host=os.getenv("KNOWLEDGE_SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("KNOWLEDGE_SERVER_PORT", "8900")),
            db_path=os.getenv("KNOWLEDGE_SERVER_DB_PATH", db_default),
            master_api_key=os.getenv("KNOWLEDGE_SERVER_MASTER_KEY", ""),
            log_level=os.getenv("KNOWLEDGE_SERVER_LOG_LEVEL", "info"),
        )
