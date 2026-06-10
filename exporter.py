import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from config import DATA_DIR, IMAGES_DIR
from logger import logger
from markdown_builder import convert_post_json_to_markdown
from spider.index_manage import IndexManager
from spider.utils import get_display_name, post_subdir_name


def export_posts(post_keys: List[str], export_root: str | Path, index_manager: IndexManager):
    """
    导出一个或多个帖子到指定目录。

    Args:
        post_keys: 帖子键列表，如 ["10270233938_full", "5741816903_see_lz"]
        export_root: 导出目录的父路径（用户选的文件夹）
        index_manager: 索引管理器实例

    Returns:
        str: 创建的导出文件夹路径，失败返回 None
    """
    export_root = Path(export_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = export_root / f"TiebaShelf_share_{timestamp}"

    try:
        index, _ = index_manager.load_index()
    except Exception as e:
        logger.error(f"加载索引失败: {e}")
        return None

    # 收集有效帖子
    posts_meta = []
    for post_key in post_keys:
        if post_key not in index:
            logger.warning(f"索引中未找到帖子 {post_key}，跳过")
            continue
        post_info = index[post_key]
        json_rel_path = post_info['file_path']
        json_path = DATA_DIR / json_rel_path
        if not json_path.exists():
            logger.warning(f"JSON 文件不存在: {json_path}，跳过")
            continue
        posts_meta.append((post_key, post_info, json_path))

    if not posts_meta:
        logger.warning("没有有效的帖子可导出")
        return None

    # 创建导出目录结构
    export_md_dir = export_dir / "markdowns"
    export_images_dir = export_dir / "images"
    export_posts_dir = export_dir / "posts"
    export_md_dir.mkdir(parents=True, exist_ok=True)
    export_images_dir.mkdir(parents=True, exist_ok=True)
    export_posts_dir.mkdir(parents=True, exist_ok=True)

    export_list = []
    for post_key, post_info, json_path in posts_meta:
        post_id = post_info['post_id']
        see_lz = post_info['see_lz']
        image_subdir_name = post_subdir_name(post_id, see_lz)

        # 1. 先复制图片目录，再以导出 images/ 为基准渲染 MD
        src_images = IMAGES_DIR / image_subdir_name
        dst_images = export_images_dir / image_subdir_name
        dst_images.mkdir(parents=True, exist_ok=True)  # 确保导出包有目录
        if src_images.exists():
            try:
                shutil.copytree(src_images, dst_images, dirs_exist_ok=True)
            except Exception as e:
                logger.warning(f"复制图片失败 {image_subdir_name}: {e}")

        # 2. 重新渲染 MD（跳过 patch，引用导出自身的 images/）
        try:
            md_path = convert_post_json_to_markdown(
                json_path,
                output_md_dir=export_md_dir,
                apply_patch=False,
                image_base_dir=export_images_dir,
            )
            md_rel_path = Path(md_path).relative_to(export_dir).as_posix()
        except Exception as e:
            logger.error(f"渲染 Markdown 失败 {post_key}: {e}")
            continue

        # 3. 复制原始 JSON
        json_filename = json_path.name
        dst_json = export_posts_dir / json_filename
        try:
            shutil.copy2(json_path, dst_json)
        except Exception as e:
            logger.warning(f"复制 JSON 失败 {json_filename}: {e}")
            continue

        # 4. 收集元数据（模仿 index.json 格式）
        export_list.append({
            "post_id": post_id,
            "title": post_info['title'],
            "see_lz": see_lz,
            "url": post_info['url'],
            "last_crawled": post_info['last_crawled'],
            "total_pages": post_info.get('total_pages', 0),
            "total_floors": post_info['total_floors'],
            "file_path": f"posts/{json_filename}",
            "display_name": get_display_name(post_info['title'], see_lz),
            "max_floor_number": post_info.get('max_floor_number', 0),
            "markdown": md_rel_path,
            "images_dir": f"images/{image_subdir_name}/",
        })

    # 5. 写入 export.json
    export_data = {
        "export_version": "1.0",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tool": "TiebaShelf v2.7",
        "total_posts": len(export_list),
        "posts": export_list,
    }

    export_json_path = export_dir / "export.json"
    try:
        with open(export_json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"写入 export.json 失败: {e}")
        return None

    logger.info(f"导出完成: {export_dir} ({len(export_list)} 个帖子)")
    return str(export_dir)
