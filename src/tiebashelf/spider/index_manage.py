import json
import shutil
from pathlib import Path
from tiebashelf.logger import logger
from typing import Dict, Tuple
from tiebashelf.spider.type_models import PostData, PostIndex

from tiebashelf.spider.utils import extract_posts_id, get_safe_filename, get_display_name, json_to_md_path, post_subdir_name
from tiebashelf.config import DATA_DIR, PATCHES_DIR

class IndexManager:
    def __init__(self):
        self.data_dir = DATA_DIR
        self.index_file = self.data_dir / "index.json"
        self.ensure_index_file()

    def ensure_index_file(self) -> None:
        """
        确保索引文件存在（同步，无 I/O 阻塞）

        Raises:
            OSError: 如果文件或目录创建失败。
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            logger.info("创建新的索引文件")

            
    def load_index(self) -> Tuple[Dict[str, PostIndex], Dict]:
        """
        加载索引（同步）

        Returns:
            - 帖子条目Dict[str, PostIndex]：键为 post_key，值为 PostIndex 格式。
            - 元数据Dict：prefer_label 等根级键值对。

        Raises:
            FileNotFoundError: 如果索引文件不存在。
            json.JSONDecodeError: 如果索引文件格式错误。
        """
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            posts = {k: v for k, v in data.items() if isinstance(v, dict) and 'post_id' in v}
            meta = {k: v for k, v in data.items() if not (isinstance(v, dict) and 'post_id' in v)}
            return posts, meta
        except FileNotFoundError:
            logger.info("索引文件不存在，创建新索引")
            return {}, {}
        except json.JSONDecodeError as e:
            logger.warning(f"索引文件格式错误: {e}，使用空索引")
            return {}, {}
        except Exception as e:
            logger.warning(f"加载索引失败: {e}，使用空索引")
            return {}, {}

    def save_index(self, index: Dict[str, PostIndex], meta: dict | None = None) -> None:
        """
        保存索引（同步）

        Args:
            index (Dict[str, PostIndex]): 帖子条目数据。
            meta (dict | None): 根级元数据（prefer_label 等），会合并后写入。

        Raises:
            Exception: 如果保存索引失败。
        """
        try:
            to_write = dict(meta) if meta else {}
            to_write.update(index)

            if self.index_file.exists():
                backup_file = self.index_file.with_suffix('.json.bak')
                shutil.copy2(self.index_file, backup_file)

            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(to_write, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存索引失败: {e}")
            
    def get_index_key(self, post_id: str, see_lz: bool) -> str:
        """
        获取索引键。

        Args:
            post_id (str): 帖子ID。
            see_lz (bool): 是否只看楼主。

        Returns:
            str: 索引键。
        """
        return f"{post_id}_{'see_lz' if see_lz else 'full'}"
    
    def parse_post_key(self, post_key: str, to_url=True) -> str | tuple[str, bool]:
        """
        解析帖子键（post_key），提取原始链接和是否只看楼主标识或者post_id/see_lz
        
        Args:
            post_key (str): 帖子键，格式如 "10321726616_see_lz"
            to_url(bool)：默认为True，转化为原始链接
        Returns:
            url(str): 原始帖子URL
            or
            post_id（str）：帖子身份标识
            see_lz（bool）：是否只看楼主
        """
        parts = post_key.split("_", maxsplit=1)
        post_id = parts[0]
        # 处理pattern：存在且等于see_lz才为True，否则False
        see_lz = len(parts) > 1 and parts[1] == "see_lz"
        if to_url:
            original_url = f"https://tieba.baidu.com/p/{post_id}"
            return original_url if not see_lz else f"{original_url}?see_lz=1"
        else:
            return post_id, see_lz
    
    
    def post_exists(self, post_id: str, see_lz: bool) -> bool:
        """检查帖子是否已在索引中。

        Args:
            post_id (str): 帖子 ID。
            see_lz (bool): 是否只看楼主。

        Returns:
            bool: 是否存在。
        """
        index, _ = self.load_index()
        key = self.get_index_key(post_id, see_lz)
        return key in index

    def add_to_index(self, post_data: PostData, preserve_last_crawled: bool = False) -> None:
        """
        将帖子数据添加到索引中。

        Args:
            post_data (PostData): 帖子数据。
            preserve_last_crawled (bool): 若为 True 且帖子已存在，保留本地的 last_crawled。

        Raises:
            Exception: 如果保存索引失败。
        """
        index, meta = self.load_index()
        filename = get_safe_filename(
            post_data['post_id'], post_data['see_lz'], post_data['title']
        )
        display_name = get_display_name(post_data['title'], post_data['see_lz'])
        index_entry: PostIndex = {
            'post_id': post_data['post_id'],
            'title': post_data['title'],
            'see_lz': post_data['see_lz'],
            'url': post_data['url'],
            'last_crawled': post_data['crawl_time'],
            'total_pages': post_data['total_pages'],
            'total_floors': post_data['total_floors'],
            'file_path': f"posts/{filename}",
            'display_name': display_name,
            'max_floor_number': post_data['max_floor_number']
        }
        index_key = self.get_index_key(post_data['post_id'], post_data['see_lz'])

        if preserve_last_crawled and index_key in index:
            index_entry['last_crawled'] = index[index_key]['last_crawled']

        # 保留已有的 pinned / tags
        if index_key in index:
            existing = index[index_key]
            if existing.get('pinned'):
                index_entry['pinned'] = True
            if existing.get('tags'):
                index_entry['tags'] = list(existing['tags'])

        index[index_key] = index_entry
        self.save_index(index, meta)
        logger.info(f"已添加到索引: 「{display_name}」")

    def set_pinned(self, post_key: str, pinned: bool) -> None:
        """设置帖子置顶状态"""
        index, meta = self.load_index()
        if post_key in index:
            index[post_key]['pinned'] = pinned
            self.save_index(index, meta)
            logger.info(f"{'置顶' if pinned else '取消置顶'}: 「{index[post_key].get('display_name', post_key)}」")

    def set_tags(self, post_key: str, tags: list[str]) -> None:
        """设置帖子的标签列表"""
        index, meta = self.load_index()
        if post_key in index:
            index[post_key]['tags'] = tags
            self.save_index(index, meta)
            logger.info(f"更新标签: 「{index[post_key].get('display_name', post_key)}」")

    def get_prefer_label(self) -> list[str]:
        """获取用户常用标签列表"""
        _, meta = self.load_index()
        return meta.get('prefer_label', [])

    def set_prefer_label(self, labels: list[str]) -> None:
        """设置用户常用标签列表（最多6个）"""
        index, meta = self.load_index()
        meta['prefer_label'] = labels[:6]
        self.save_index(index, meta)
        
    def check_repeated_url(self, url: str, see_lz: bool = False) -> str | None:
        """
        检查URL是否重复。

        Args:
            url (str): 帖子URL。
            see_lz (bool, optional): 是否只看楼主。默认为False。

        Returns:
            str: "new"（新URL），"same"（相同模式）。
        """
        post_id = extract_posts_id(url=url)
        if not post_id:
            return "new"
        index, _ = self.load_index()
        index_key = self.get_index_key(post_id, see_lz)
        if index_key not in index:
            return "new"
        existing_post = index[index_key]
        if existing_post['see_lz'] == see_lz:
            return "same"
        
    def delete_post(self, post_id: str, see_lz: bool) -> bool:
        """
        完全删除指定帖子的所有本地数据（JSON、图片、Markdown）并清理索引。
        
        Args:
            post_id (str): 帖子ID，如 "7833341768"
            see_lz (bool): 查看模式（True=只看楼主，False=完整版）
        
        Returns:
            bool: True 表示删除成功（或不存在），False 表示发生错误
        
         Side Effects:
            - 删除 data/posts/ 下的 JSON 文件
            - 删除 data/images/{post_id}_{mode}/ 目录
            - 删除 data/markdowns/ 下的 .md 文件
            - 删除 data/patches/{post_id}_{mode}/ 目录（含 patch.json 和补丁图片）
            - 从 index.json 中移除对应条目
        """
        try:
            # 1. 获取索引键并加载索引
            index_key = self.get_index_key(post_id, see_lz)
            index, meta = self.load_index()
            
            if index_key not in index:
                logger.warning(f"索引中未找到帖子 {index_key}，跳过删除")
                return True  # 视为“已不存在”，返回成功
            
            post_meta = index[index_key]
            file_path = post_meta["file_path"]  # 如 "posts/xxx.json"
            display_name = post_meta["display_name"]
            logger.info(f"开始删除帖子: 「{display_name}」")
            
            # 2. 删除 JSON 文件
            json_full_path = self.data_dir / file_path
            if json_full_path.exists():
                json_full_path.unlink()
            else:
                logger.warning(f"JSON 文件不存在: {json_full_path}")
            
            # 3. 删除图片目录
            subdir = post_subdir_name(post_id, see_lz)
            images_dir = self.data_dir / "images" / subdir
            if images_dir.exists():
                shutil.rmtree(images_dir)
            else:
                logger.warning(f"图片目录不存在: {images_dir}")
            
            # 4. 删除 Markdown 文件
            # Markdown 文件名与 JSON 同名（仅后缀不同）
            md_full_path = json_to_md_path(file_path)
            if md_full_path.exists():
                md_full_path.unlink()
            else:
                logger.warning(f"Markdown 文件不存在: {md_full_path}")

            # 5. 删除补丁目录（含 patch.json 和补丁图片）
            patch_dir = PATCHES_DIR / subdir
            if patch_dir.exists():
                shutil.rmtree(patch_dir)
            else:
                patch_path = PATCHES_DIR / f"{Path(file_path).stem}.patch.json"
                if patch_path.exists():
                    patch_path.unlink()

            # 6. 从索引中移除
            del index[index_key]
            self.save_index(index, meta)
            logger.info(f"已从索引中移除: 「{display_name}」")
            
            return True
            
        except Exception as e:
            logger.error(f"删除帖子时出错 (post_id={post_id}, see_lz={see_lz}): {e}")
            return False
