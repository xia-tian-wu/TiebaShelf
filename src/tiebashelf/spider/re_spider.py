import asyncio
import datetime
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from rs_aiotieba import Post, Posts, get_posts

from tiebashelf.config import POSTS_DIR, IMAGES_DIR
from tiebashelf.logger import logger
from tiebashelf.spider.type_models import PostData, FloorData, PostIndex
from tiebashelf.spider.index_manage import IndexManager
from tiebashelf.spider.image_link import TiebaImageDownloader
from tiebashelf.spider.utils import extract_posts_id, get_safe_filename, post_subdir_name
from tiebashelf.markdown_builder import convert_post_json_to_markdown
import tiebashelf.spider.exceptions as ex


def timestamp_to_datetime(timestamp: int, format_str: str = "%Y-%m-%d %H:%M") -> str:
    """
    精准转换 Unix 时间戳为本地时间（匹配界面显示逻辑）

    Args:
        timestamp: Unix 时间戳（整数）
        format_str: 输出格式

    Returns:
        格式化后的时间字符串
    """
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime(format_str)


class TiebaShelf:
    """基于 aiotieba 的贴吧爬虫类"""

    def __init__(self) -> None:
        """
        初始化爬虫对象
        """
        self.index_manager = IndexManager()
        self.index_path = Path('data') / 'index.json'

        # 并发控制：获取内容用独立 semaphore，下载图片另用一个
        self._fetch_semaphore = asyncio.Semaphore(4)
        self._download_semaphore = asyncio.Semaphore(3)

    # === 工具方法 ===

    def build_url_prefix(self, bar_name: str, tid: int) -> str:
        """构建贴吧图片 URL 前缀"""
        return f'https://tieba.baidu.com/photo/p?kw={bar_name}&flux=1&tid={tid}&pic_id='

    def get_image_path(self, mode: bool, post_id: int | str) -> str:
        """
        获取图片保存目录的绝对路径

        Args:
            mode: 是否只看楼主
            post_id: 帖子 ID

        Returns:
            图片目录的绝对路径
        """
        return str(IMAGES_DIR / post_subdir_name(post_id, mode))
    
    def escape_markdown(self, text: str) -> str:
        """转义 Markdown 元字符，防止被错误解析"""
        # 需要转义的字符（按标准 Markdown）
        escape_chars = r'\<>`*_{}[]()#+-.!~&'
        return re.sub(r'([' + re.escape(escape_chars) + r'])', r'\\\1', text)

    async def _get_posts(self, tid: int, pn: int, see_lz: bool):
        """异步包装 rs_aiotieba.get_posts：放到线程池执行，不阻塞事件循环"""
        return await asyncio.to_thread(get_posts, tid, pn, see_lz)

    def convert_post_to_floordata(self, post: Post, kw: str, tid: int) -> Tuple[FloorData, List[str]]:
        """
        将 aiotieba 的 Post 对象转换为 FloorData 格式

        Args:
            post: aiotieba 返回的 Post 对象
            kw: 吧名
            tid: 帖子 ID

        Returns:
            FloorData: 单个楼层的数据
            List[str]: 图片 URL 列表
        """
        content_parts = []
        image_url_list = []
        url_prefix = self.build_url_prefix(bar_name=kw, tid=tid)

        for obj in post.contents.objs:
            type_name = type(obj).__name__
            if 'FragText' in type_name:
                content_parts.append(self.escape_markdown(obj.text))
            elif 'FragLink' in type_name:
                content_parts.append(f'[{obj.title}]({obj.text})')
            elif 'FragImage' in type_name:
                image_url = url_prefix + obj.hash
                image_url_list.append(image_url)
                content_parts.append(f'[图片：{obj.hash}.jpg]')

        floor_data: FloorData = {
            'author': str(post.user.nick_name_new if post.user.nick_name_new else post.user.user_name),
            'content': ''.join(content_parts),
            'images': image_url_list,
            'local_images': [],
            'floor_number': int(post.floor),
            'post_time': timestamp_to_datetime(post.create_time),
            'ip_location': post.user.ip if post.user.ip else '',
            'device': '',
        }

        return floor_data, image_url_list

    def extract_new_floors(self, current_floors: List[FloorData], history_max_floor: int) -> List[FloorData]:
        """从当前楼层列表中提取新增楼层"""
        return [floor for floor in current_floors if floor['floor_number'] > history_max_floor]

    def is_valid_post_page(self, posts: Posts) -> bool:
        """检查 Posts 对象是否为有效的帖子页面"""
        return posts.status == "ok"

    # === 核心爬取逻辑 ===

    async def crawl_full_post(self, url: str, see_lz: bool = False, force_recrawl: bool = False) -> Optional[PostData]:
        """
        爬取帖子的统一入口（支持新爬、增量更新、强制重新爬取）

        Args:
            url: 帖子 URL
            see_lz: 是否只看楼主
            force_recrawl: 是否强制重新爬取（忽略历史数据，默认 False）

        Returns:
            PostData: 完整的帖子数据；无更新时返回 None

        Raises:
            InvalidURLError: URL 格式错误
            FileIndexError: 读取历史数据失败
            NetworkError: 网络请求失败
        """
        # 1. 解析 URL
        current_see_lz = see_lz or ('see_lz=1' in url)
        tid = extract_posts_id(url)
        if not tid:
            raise ex.InvalidURLError("无法提取帖子 ID", url=url)

        # 2. 检查索引（强制重爬时跳过）
        index, _ = self.index_manager.load_index()
        index_key = self.index_manager.get_index_key(tid, current_see_lz)

        history_post_data: Optional[PostData] = None
        start_pn = 1
        history_max_floor = 0

        if not force_recrawl and index_key in index:
            history_post_index = index[index_key]
            history_file_path = self.index_path.parent / history_post_index['file_path']

            try:
                with open(history_file_path, 'r', encoding='utf-8') as f:
                    history_post_data = json.load(f)
            except Exception as e:
                logger.error(f"读取历史帖子数据失败：{e}")
                raise ex.FileIndexError("读取历史帖子数据失败", url=url)

            if history_post_data and history_post_data.get('floors'):
                history_max_floor = history_post_data.get('max_floor_number', 0)
                start_pn = max(1, history_post_data.get('total_pages', 1))

            # === 检测图片目录变更（支持软件迁移） ===
            recorded_images_dir = history_post_data.get('images_dir', '')
            present_images_dir = self.get_image_path(current_see_lz, tid)
            if recorded_images_dir and recorded_images_dir != present_images_dir:
                logger.info(f"检测到图片目录变更，更新历史记录中的图片目录路径：{present_images_dir}")
                history_post_data['images_dir'] = present_images_dir

        else:
            if force_recrawl:
                logger.info(f"强制重新爬取模式，忽略历史数据：{tid}")
            else:
                logger.info(f"未找到历史数据，开始全文爬取：{tid}")

        post_sign = history_post_data.get('title') if history_post_data else url

        # 3. 执行爬取（受 _fetch_semaphore 限制，不阻塞其他帖子的下载）
        async with self._fetch_semaphore:
            new_floors, new_images_list, base_info = await self._sync_single_tid(
                int(tid), start_pn, current_see_lz, history_max_floor, post_sign
            )

        if not new_floors:
            logger.info(f"帖子「{post_sign}」没有新内容")
            return None

        # 4. 下载图片（受 _download_semaphore 限制，不阻塞其他帖子的获取）
        save_dir = IMAGES_DIR / post_subdir_name(tid, current_see_lz)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        async with self._download_semaphore:
            async with TiebaImageDownloader() as downloader:
                success_count, _ = await downloader.download_and_backfill(
                    new_floors=new_floors,
                    new_images_list=new_images_list,
                    save_dir=save_dir,
                    post_id=tid
                )

        # 5. 合并数据并保存
        if history_post_data:
            history_post_data['floors'].extend(new_floors)
            unique_floors = {f['floor_number']: f for f in history_post_data['floors']}.values()
            sorted_floors = sorted(unique_floors, key=lambda x: x['floor_number'])

            updated_post_data: PostData = {
                'post_id': history_post_data['post_id'],
                'title': history_post_data['title'],
                'see_lz': history_post_data['see_lz'],
                'url': history_post_data['url'],
                'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_pages': base_info['max_page_num'],
                'total_floors': len(sorted_floors),
                'floors': sorted_floors,
                'images_downloaded': history_post_data.get('images_downloaded', 0) + success_count,
                'images_dir': history_post_data.get('images_dir', ''),
                'max_floor_number': max(f['floor_number'] for f in sorted_floors),
                'bar': history_post_data.get('bar', '')
            }
        else:
            updated_post_data: PostData = {
                'post_id': tid,
                'title': base_info['title'],
                'see_lz': current_see_lz,
                'url': url,
                'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_pages': base_info['max_page_num'],
                'total_floors': len(new_floors),
                'floors': new_floors,
                'images_downloaded': success_count,
                'images_dir': str(save_dir),
                'max_floor_number': max(f['floor_number'] for f in new_floors),
                'bar': base_info['bar_name']
            }

        # 6. 保存到索引
        self._save_post_data(updated_post_data)
        return updated_post_data

    async def _sync_single_tid(
        self,
        tid: int,
        start_pn: int,
        see_lz: bool,
        history_max_floor: int,
        post_sign: str
    ) -> Tuple[List[FloorData], List[str], Dict]:
        """
        底层同步原子：从指定页码爬取到最后一页，并过滤旧楼层

        Args:
            tid: 帖子 ID
            start_pn: 起始页码
            see_lz: 是否只看楼主
            history_max_floor: 历史最大楼层号
            post_sign: 帖子标识（用于日志）

        Returns:
            List[FloorData]: 新增楼层列表
            List[str]: 新增图片 URL 列表
            Dict: 基础信息（总页数、标题、吧名）
        """
        # 第一步：请求起始页
        try:
            first_resp = await self._get_posts(tid, start_pn, see_lz)
        except Exception as e:
            logger.error(f"网络请求失败：{e}")
            raise ex.NetworkError(f"获取帖子失败：{e}", url=f"https://tieba.baidu.com/p/{tid}")

        if not self.is_valid_post_page(first_resp):
            logger.warning(f'「{post_sign}」帖子可能已被删除或隐藏')
            raise ex.ParseError("帖子页面解析失败，可能帖子不存在或结构已变化", url=f"https://tieba.baidu.com/p/{tid}")

        total_page = first_resp.page.total_page
        title = first_resp.thread.title
        bar_name = first_resp.bar_name

        # 处理页数缩减情况
        if start_pn > total_page:
            logger.info(f"检测到页数缩减（{start_pn} -> {total_page}），重置为从第 1 页重新同步")
            return await self._sync_single_tid(tid, 1, see_lz, 0, post_sign)

        # 第二步：异步并发抓取剩余页
        all_pages_resp = [first_resp]
        if total_page > start_pn:
            tasks = [self._get_posts(tid, p, see_lz) for p in range(start_pn + 1, total_page + 1)]
            others = await asyncio.gather(*tasks, return_exceptions=True)
            for r in others:
                if not isinstance(r, Exception):
                    all_pages_resp.append(r)

        # 第三步：解析楼层并过滤
        all_new_floors = []
        all_new_images = []

        for page in all_pages_resp:
            for post in page:
                floor_data, image_hash_list = self.convert_post_to_floordata(post, bar_name, tid)
                if floor_data['floor_number'] > history_max_floor:
                    all_new_floors.append(floor_data)
                    all_new_images.extend(image_hash_list)

        base_info = {
            'max_page_num': total_page,
            'title': title,
            'bar_name': bar_name
        }

        return all_new_floors, all_new_images, base_info

    async def crawl_multi_posts(
        self,
        urls: List[str],
        recrawl_urls: List[str] | None = None,
        on_post_done=None,
    ) -> List[Dict]:
        """
        批量爬取多个帖子（统一入口）

        Args:
            urls: 帖子 URL 列表
            recrawl_urls: 需要强制重新爬取的 URL 列表
            on_post_done: 每完成一个帖子时的回调（签名：Callable[[Dict], None]），
                用于渐进更新进度条。即使某个帖子抛出异常，回调也会被调用。

        Returns:
            List[Dict]: 每个帖子的爬取结果 [{url, status, data/error}, ...]
        """

        recrawl_urls = recrawl_urls or []

        async def _run_one(url: str) -> tuple:
            """包装单个帖子的爬取：异常被捕获，结果以 (url, res_or_exc) 返回"""
            try:
                res = await self.crawl_full_post(url, force_recrawl=url in recrawl_urls)
            except Exception as e:
                res = e
            return url, res

        # 为每个 URL 启动并发任务
        tasks = [asyncio.ensure_future(_run_one(url)) for url in urls]
        url_index = {url: i for i, url in enumerate(urls)}
        formatted_results: List[Optional[Dict]] = [None] * len(urls)

        # 用 as_completed 实现渐进回调：哪个先完成先发回调
        for task in asyncio.as_completed(tasks):
            url, res = await task

            if isinstance(res, Exception):
                result_dict = {
                    'url': url,
                    'status': 'error',
                    'error': str(res)
                }
            else:
                result_dict = {
                    'url': url,
                    'status': 'success' if res else 'no_update',
                    'data': res
                }

            formatted_results[url_index[url]] = result_dict

            if on_post_done is not None:
                on_post_done(result_dict)

        return formatted_results

    # === 数据持久化 ===

    def _save_post_data(self, post_data: PostData) -> None:
        """
        保存帖子数据到本地 JSON 文件，生成 Markdown，并更新索引

        Args:
            post_data: 完整的帖子数据对象
        """
        # 1. 保存 JSON
        filename = get_safe_filename(
            post_data['post_id'], post_data['see_lz'], post_data['title']
        )
        filepath = POSTS_DIR / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(post_data, f, ensure_ascii=False, indent=2)

        logger.info(f"帖子数据已保存：「{post_data['title']}」")

        # 2. 生成 Markdown
        try:
            md_path = convert_post_json_to_markdown(filepath)
            logger.info(f"Markdown 已生成：{Path(md_path).name}")
        except Exception as e:
            logger.error(f'Markdown 生成失败：{e}')

        # 3. 更新索引
        try:
            self.index_manager.add_to_index(post_data)
        except Exception as e:
            logger.error(f'索引更新失败：{e}')
