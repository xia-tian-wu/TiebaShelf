from itertools import takewhile
from fake_useragent import UserAgent
import re
import os
from pathlib import Path

def normalize_url(url: str, see_lz: bool) -> str | None:
    """
    标准化贴吧帖子URL，确保格式为：
    - 完整版: https://tieba.baidu.com/p/12345
    - 只看楼主: https://tieba.baidu.com/p/12345?see_lz=1
    """
    base_prefix = "https://tieba.baidu.com/p/"
    
    if not url.startswith(base_prefix):
        return None 

    # 提取帖子ID
    after_p = url[len(base_prefix):]
    post_id = ''.join(takewhile(str.isdigit, after_p))
    
    if not post_id:
        return None

    # 构建基础URL
    base_url = f"{base_prefix}{post_id}"
    
    # 添加参数
    return f"{base_url}?see_lz=1" if see_lz else base_url

def extract_posts_id(url: str | None) -> str | None:
    if not url:  # 处理 url 为 None 或空字符串的情况
        return None
    match = re.search(r'/p/(\d+)', url)
    return match.group(1) if match else None

def append_pn_param(base_url: str, page: int) -> str:
    """安全地为 URL 添加 pn= 分页参数"""
    if '?' in base_url:
        return f"{base_url}&pn={page}"
    else:
        return f"{base_url}?pn={page}"
    
ua = UserAgent(browsers=['chrome', 'edge', 'firefox'], os=['windows', 'macos'])

# generate a random User-Agent
def get_headers():
    """返回模拟真实浏览器的 headers"""
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'DNT': '1',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Referer': 'https://tieba.baidu.com/',
        'User-Agent': ua.random,  # 动态随机 UA
    }
    return headers

def get_safe_filename_part(raw_str: str, max_len: int = 50) -> str:
    """
    通用安全文件名处理：过滤非法字符、截断长度。
    
    Args:
        raw_str: 原始字符串（标题/显示名）
        max_len: 最大长度
        
    Returns:
        安全的字符串
    """
    # 过滤Windows/Linux非法文件名字符
    safe_str = re.sub(r'[<>:"/\\|?*]', '_', raw_str)
    # 截断长度（保留省略号）
    if len(safe_str) > max_len:
        safe_str = f"{safe_str[:max_len-3]}..."
    return safe_str

def get_display_name(title: str, see_lz: bool, for_filename: bool = False) -> str:
    """
    生成帖子的友好显示名称（含查看模式后缀），支持适配文件名场景。
    
    Args:
        title: 帖子原始标题
        see_lz: 是否为「只看楼主」模式
        for_filename: 是否为文件名场景（开启则过滤非法字符、截断长度）
        
    Returns:
        格式化后的显示名称（如 "帖子标题 (只看楼主)"）；
        若for_filename=True，返回安全的文件名格式（如 "帖子标题(只看楼主)"）
    """
    mode_suffix = " (只看楼主)" if see_lz else " (完整版)"
    clean_title = title.strip() or "未命名帖子"
    display_name = f"{clean_title}{mode_suffix}"
    
    if for_filename:
        return get_safe_filename_part(display_name, max_len=50)
    return display_name

def post_subdir_name(post_id: str | int, see_lz: bool) -> str:
    """生成帖子资源子目录名，如 '10287031162_see_lz'。"""
    mode = "see_lz" if see_lz else "full"
    return f"{post_id}_{mode}"

def get_safe_filename(post_id: str, see_lz: bool, title: str = "") -> str:
    """
    生成安全的帖子JSON文件名（过滤非法字符、截断过长标题）。
    
    规则：
    1. 基础格式：{safe_title}_{post_id}_{see_lz}.json
    2. 过滤标题中的 <>:"/\\|?* 等非法字符
    3. 标题截断为30字符
    4. 无有效标题时仅保留基础格式
    
    Args:
        post_id: 帖子ID
        see_lz: 是否为「只看楼主」模式
        title: 帖子标题（可选）
        
    Returns:
        安全的文件名字符串
    """
    base_name = post_subdir_name(post_id, see_lz)
    if title and title != "未知标题":
        safe_title = get_safe_filename_part(title, max_len=30)
        return f'{safe_title}_{base_name}.json'
    else:
        return f"{base_name}.json"
    
def json_to_md_path(json_flie_path: str | Path) -> Path:
    """将单个帖子 JSON 文件 路径转换为 Markdown 文件路径。
    
    Args:
        json_flie_path: 如 'data/posts/安全标题_7833341768_see_lz.json'
    
    Returns:
        生成的 Markdown 文件路径：如 'data/markdowns/安全标题_7833341768_see_lz.md'
    """
    json_path = Path(json_flie_path)
    md_path_obj = json_path.with_suffix(".md") 
    return Path("data") / "markdowns" / md_path_obj.name