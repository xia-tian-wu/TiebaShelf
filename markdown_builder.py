import os
import re
import json
from pathlib import Path
from urllib.parse import quote
from config import MARKDOWN_DIR, IMAGES_DIR, PATCHES_DIR
from spider.type_models import PostData

def convert_post_json_to_markdown(
    json_path: str | Path,
    output_md_dir: Path | None = None,
    apply_patch: bool = True,
    image_base_dir: Path | None = None,
) -> str:
    """
    将单个帖子 JSON 文件转换为 Markdown，并保存到 markdowns/ 下。
    
    Args:
        json_path: 如 'data/posts/安全标题_7833341768_see_lz.json'
        output_md_dir: 自定义输出目录，默认 MARKDOWN_DIR
        apply_patch: 是否应用 patch，导出时为 False
        image_base_dir: 图片基准目录，默认 IMAGES_DIR，导出时用 export/images/
    
    Returns:
        生成的 Markdown 文件路径
    """
    json_path = Path(json_path)
    with open(json_path, 'r', encoding='utf-8') as f:
        post_data = json.load(f)
    
    if apply_patch:
        post_data = _apply_patch_if_exists(json_path, post_data)
    
    post_id = post_data['post_id']
    see_lz = post_data.get('see_lz', False)
    mode_suffix = "see_lz" if see_lz else "full"
    image_abs_dir = (image_base_dir or IMAGES_DIR) / f"{post_id}_{mode_suffix}"
    
    md_dir = output_md_dir or MARKDOWN_DIR
    md_content = _render_markdown_from_post_data(post_data, image_abs_dir, markdown_base_dir=md_dir)
    
    md_filename = f'{json_path.stem}.md'
    md_path = md_dir / md_filename
    
    md_dir.mkdir(parents=True, exist_ok=True)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    return str(md_path)
    
def _render_markdown_from_post_data(
    post_data: PostData,
    image_abs_dir: Path,
    markdown_base_dir: Path | None = None
) -> str:
    """将帖子数据渲染为 Markdown 文本。

    Args:
        post_data: 帖子数据（含楼层列表）。
        image_abs_dir: 图片目录的绝对路径。
        markdown_base_dir: 计算图片相对路径的基准目录，默认 MARKDOWN_DIR。

    Returns:
        Markdown 文本。
    """
    lines = []
    
    title = post_data.get('title', '无标题')
    lines.append(f"# {title}\n")
    bar_name = post_data.get('bar', '未知吧名')
    original_url = post_data['url']
    mode = '只看楼主' if post_data.get('see_lz') else '完整版'
    crawl_time = post_data.get('crawl_time', '')
    total_pages = post_data['total_pages']
    total_floors = post_data['total_floors']
    lines.append(
        f"> **原始链接**: {original_url}  \n"
        f"> **帖子所在**: {bar_name}  \n"
        f"> **模式**: {mode}  \n"
        f"> **总楼层数**: {total_floors}  \n"
        f"> **总页数**: {total_pages}  \n"
        f"> **抓取时间**: {crawl_time}  \n"
    )
    lines.append('---\n')
    
    for floor in post_data["floors"]:
        floor_num = floor["floor_number"]
        author = floor["author"]
        post_time = floor.get("post_time", "")
        ip = floor.get("ip_location", "")
        content = floor.get("content", "")
        device = floor.get('device', '')
        
        meta_dict = {
        "时间": post_time,
        "IP": ip,
        "设备": device
            }
        meta_parts = [f"{k}：{v}" for k, v in meta_dict.items() if v.strip()]
        floor_meta = [f"{floor_num}楼"] + meta_parts
        floor_meta_str = " · ".join(floor_meta)
        
        lines.append(f"### {author} \n{floor_meta_str}\n")
        
        # 替换 [图片：xxx.jpg] 为 ![image](相对路径) 
        def replace_image_tag(match):
            img_filename = match.group(1)
            img_abs_path = image_abs_dir / img_filename

            if not img_abs_path.exists():
                return f"[图片：{img_filename} (未找到)]"

            md_base = markdown_base_dir or MARKDOWN_DIR
            rel_path = os.path.relpath(img_abs_path, md_base).replace("\\", "/")
            rel_path = quote(rel_path, safe="/")
            return f"![image]({rel_path})"
        
        renderded_content = re.sub(r'\[图片：([^\]]+)\]', replace_image_tag, content)
        renderded_content = renderded_content.replace('\n', '  \n')
        lines.append(renderded_content.strip() or '「该楼层无内容」')
        lines.append('\n---\n')
    
    return '\n'.join(lines)
         

def _apply_patch_if_exists(json_path: Path, post_data: dict) -> dict:
    """
    如果存在补丁文件，则应用补丁到帖子数据。
    补丁文件统一存放在 PATCHES_DIR 目录下。
    """
    patch_path = PATCHES_DIR / f"{json_path.stem}.patch.json"
    if not patch_path.exists():
        return post_data
    
    try:
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch_data = json.load(f)
        
        edits = patch_data.get('edits', {})
        for floor_num_str, edited_floor in edits.items():
            floor_num = int(floor_num_str)
            for i, floor in enumerate(post_data['floors']):
                if floor['floor_number'] == floor_num:
                    post_data['floors'][i].update(edited_floor)
                    break
    except Exception as e:
        from logger import logger
        logger.warning(f"应用补丁文件失败 {patch_path}: {e}")
    
    return post_data
