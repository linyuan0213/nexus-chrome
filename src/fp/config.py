"""指纹配置中心连接配置。

通过环境变量注入，避免硬编码：
- FP_CENTER_URL: 配置中心地址（如 https://fp-center.example.com）
- FP_CENTER_TOKEN: 节点令牌
- FP_NODE_ID: 当前节点标识（默认取 hostname）
"""

import os
import socket

FP_CENTER_URL: str = os.getenv("FP_CENTER_URL", "")
FP_CENTER_TOKEN: str = os.getenv("FP_CENTER_TOKEN", "")
FP_NODE_ID: str = os.getenv("FP_NODE_ID", socket.gethostname())
FP_SYNC_INTERVAL: int = int(os.getenv("FP_SYNC_INTERVAL", "300"))
