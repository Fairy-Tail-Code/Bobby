from pathlib import Path

import yaml


def read_yaml(file_path: str | Path = None) -> dict:
    """
    安全读取 YAML 文件
    返回：字典（dict）
    """
    # 把路径转成 Path 对象（更安全）
    path = Path(file_path)

    # 检查文件是否存在
    if not path.exists():
        raise FileNotFoundError(f"YAML 文件不存在：{file_path}")

    # 读取并解析
    with open(path, "r", encoding="utf-8") as f:
        # 使用 safe_load 防止安全风险
        data = yaml.safe_load(f)

    return data