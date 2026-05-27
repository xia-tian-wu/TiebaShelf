import json
import shutil
from pathlib import Path
from typing import Tuple

from config import POSTS_DIR, IMAGES_DIR, MARKDOWN_DIR
from logger import logger
from spider.index_manage import IndexManager
from spider.type_models import PostData


def preview_export(export_dir: str | Path) -> dict | None:
    """解析导出文件夹中的 export.json，校验格式。

    Args:
        export_dir: TiebaShelf_share_xxx 文件夹路径

    Returns:
        export.json 数据，或 None（失败时）
    """
    export_dir = Path(export_dir)
    export_json_path = export_dir / "export.json"

    if not export_json_path.exists():
        logger.error(f"未找到 export.json: {export_json_path}")
        return None

    try:
        with open(export_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"export.json 格式错误: {e}")
        return None

    version = data.get("export_version", "")
    if version != "1.0":
        logger.warning(f"不支持的导出版本: {version}")

    return data


def get_post_integrity(export_dir: Path, post_entry: dict) -> tuple[bool, str]:
    """检查单个帖子的文件是否完整。

    Returns:
        (完整?, 缺失描述)
    """
    missing = []
    if not (export_dir / post_entry['file_path']).exists():
        missing.append("原始JSON")
    if not (export_dir / post_entry['markdown']).exists():
        missing.append("Markdown")
    if not (export_dir / post_entry['images_dir']).exists():
        missing.append("图片目录")
    if missing:
        return False, f"数据不完整（缺失: {'/'.join(missing)}）"
    return True, ""


def import_selected(
    export_dir: str | Path,
    export_data: dict,
    selected_post_keys: list[str],
    index_manager: IndexManager,
    parent=None,
) -> Tuple[int, int, int]:
    """导入选中的帖子。

    Args:
        export_dir: TiebaShelf_share_xxx 文件夹路径
        export_data: 已解析的 export.json 数据
        selected_post_keys: 要导入的帖子键列表 ["id_full", "id_see_lz"]
        index_manager: 索引管理器
        parent: 父窗口（用于弹窗）

    Returns:
        (success_count, skipped_count, failed_count)
    """
    from PySide6.QtWidgets import QMessageBox

    export_dir = Path(export_dir)
    posts = export_data.get('posts', [])
    index = index_manager.load_index()
    success = 0
    skipped = 0
    failed = 0

    for post_entry in posts:
        post_id = post_entry['post_id']
        see_lz = post_entry['see_lz']
        post_key = f"{post_id}_{'see_lz' if see_lz else 'full'}"

        if post_key not in selected_post_keys:
            continue

        display_name = post_entry.get('display_name', post_key)

        # 检查冲突
        if index_manager.post_exists(post_id, see_lz):
            existing = index.get(post_key, {})
            local_floor = existing.get('max_floor_number', '?')
            import_floor = post_entry.get('max_floor_number', '?')

            reply = QMessageBox.question(
                parent,
                "帖子已存在",
                f"帖子「{display_name}」本地已存在。\n"
                f"本地版本：{local_floor}楼 | 导入版本：{import_floor}楼\n"
                f"内容可能因抓取时间或不可控增删楼层而不同。\n"
                f"是否用导入版本覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                logger.info(f"跳过导入: 「{display_name}」")
                skipped += 1
                continue

        # 复制文件
        try:
            json_filename = Path(post_entry['file_path']).name
            src_json = export_dir / "posts" / json_filename
            if src_json.exists():
                dst_json = POSTS_DIR / json_filename
                shutil.copy2(src_json, dst_json)

            md_filename = Path(post_entry['markdown']).name
            src_md = export_dir / "markdowns" / md_filename
            if src_md.exists():
                dst_md = MARKDOWN_DIR / md_filename
                shutil.copy2(src_md, dst_md)

            images_subdir = Path(post_entry['images_dir'])
            src_images = export_dir / images_subdir
            dst_images = IMAGES_DIR / images_subdir.name
            if src_images.exists():
                shutil.copytree(src_images, dst_images, dirs_exist_ok=True)

            json_path = POSTS_DIR / json_filename
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    post_data: PostData = json.load(f)
                index_manager.add_to_index(post_data, preserve_last_crawled=True)

            logger.info(f"导入成功: 「{display_name}」")
            success += 1

        except Exception as e:
            logger.error(f"导入失败「{display_name}」: {e}")
            failed += 1

    return (success, skipped, failed)
