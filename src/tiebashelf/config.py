import sys
from pathlib import Path

def get_data_path() -> Path:
    """
    获取数据文件的绝对路径 (用于保存 json, logs, db 等)
    打包后指向 exe 文件所在的目录 (即 dist 目录)
    开发模式指向项目根目录下的 data 文件夹
    """
    if hasattr(sys, "_MEIPASS"):
        # sys.executable 指向打包后的 exe 文件
        base_dir = Path(sys.executable).parent
    else:
        # 开发模式下，指向项目根目录
        base_dir = Path(__file__).resolve().parent.parent.parent

    return base_dir


# 全局定义数据路径
BASE_PATH = get_data_path()
DATA_DIR = BASE_PATH / 'data'
POSTS_DIR = DATA_DIR / "posts"
IMAGES_DIR = DATA_DIR / "images"
MARKDOWN_DIR = DATA_DIR / "markdowns"
PATCHES_DIR = DATA_DIR / "patches"

PACKAGE_DIR = Path(__file__).parent

# 创建目录，在 exe 同目录下
for directory in [DATA_DIR, POSTS_DIR, IMAGES_DIR, MARKDOWN_DIR, PATCHES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = 5
TIMEOUT = 10  
REQUEST_INTERVAL = 2  