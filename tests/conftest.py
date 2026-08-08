"""测试配置：指纹画像使用独立临时数据库。"""

import os

os.environ["FP_CENTER_DB"] = "/tmp/nexus_chrome_fp_test.db"
