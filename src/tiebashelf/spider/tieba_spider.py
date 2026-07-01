# 此文件已废弃，仅作为某种留念，或许有一天还是需要老版本贴吧的元素布局做点什么的
# 具体的信息获取逻辑已迁移至 scr/tiebashelf/spider/re_spider.py

import sys
import os
import shutil
from pathlib import Path

# 项目核心常量/路径
from tiebashelf.config import (
    POSTS_DIR, 
    IMAGES_DIR, 
    TIMEOUT, 
    MAX_RETRIES   
)

from typing import Optional, List, Dict, Tuple
from tiebashelf.spider.type_models import PostData, FloorData, PostIndex 

# 网络/异步（爬虫核心IO）
import asyncio
import httpx

# 数据解析（HTML/URL处理）
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# 数据处理
import json
import re
import random
import time

# 项目内部模块
from .utils import normalize_url, extract_posts_id, append_pn_param, get_headers, get_safe_filename, get_display_name
from tiebashelf.markdown_builder import convert_post_json_to_markdown
from tiebashelf.spider.index_manage import IndexManager
import tiebashelf.spider.exceptions as ex

from tiebashelf.logger import logger

class TiebaShelf:
    # =============== 初始化与基础配置 ===============
    def __init__(self, client: None | httpx.AsyncClient = None) -> None:
        """初始化爬虫对象"""
        self.client = client 
        self.index_manager = IndexManager()  
        self.index_file = os.path.join('data', 'index.json')
        self._client_lock = asyncio.Lock()
        self.delay_config = {
            'min_delay': 0.8,
            'max_delay': 3.0,
            'base_delay': 1.0,
            'jitter': True,
            'adaptive': True
        }
    def cleanup(self):
        """
        清理已知的复杂对象
        """
        if self.client:
            try:
                # httpx 客户端清理
                self.client = None
            except Exception as e:
                logger.error(f"清理 httpx 客户端失败: {e}")
                
        self.index_manager = None
                
    # =============== 异步网络请求（核心IO） ===============

    async def _initialize_client(self):
        """确保全局只有一个初始化任务在执行，且执行完毕后才释放"""
        if self.client is not None and not self.client.is_closed:
            return

        async with self._client_lock:
            # 再次检查，防止等待锁期间另一个协程已经初始化好了
            if self.client is not None and not self.client.is_closed:
                return

            logger.info("正在初始化异步HTTP客户端并进行强制预热...")
            headers = get_headers()
            # 模拟更像真实浏览器的头部
            headers['Referer'] = 'https://www.google.com/'
            
            new_client = httpx.AsyncClient(
                headers=headers, 
                timeout=TIMEOUT, 
                http2=True,
                follow_redirects=True # 建议开启，预热时可能有重定向
            )

            try:
                # 必须在锁内等待预热完成
                resp = await new_client.get('https://www.baidu.com/', timeout=5.0)
                # 只有预热成功了，才正式赋值给 self.client
                self.client = new_client
            except Exception as e:
                logger.warning(f"百度Cookies预热失败: {e}")
                self.client = new_client # 即使失败也要赋值，否则会死循环，但建议记录异常
            
    async def  close_client(self):
        """
        关闭异步HTTP客户端，释放资源。
        """
        if self.client:
            logger.info("正在关闭异步HTTP客户端...")
            await self.client.aclose()
            self.client = None

    async def make_tieba_request(self, url: str) -> httpx.Response:
        """
        异步发送请求到贴吧页面。

        Args:
            url (str): 贴吧页面的URL。

        Returns:
            httpx.Response: HTTP响应对象。

        Raises:
            ex.NetworkError: 如果请求在最大重试次数后仍然失败。
        """
                
        await self._initialize_client()

        headers = get_headers()
        headers['Referer'] = 'https://tieba.baidu.com/'

        for attempt in range(MAX_RETRIES):
            if attempt > 0:
                retry_delay = random.uniform(3.0, 6.0)
                logger.info(f"等待 {retry_delay:.2f} 秒后重试...")
                await asyncio.sleep(retry_delay)

            try:
                response = await self.client.get(url, headers=headers)

                if ("百度安全验证" in response.text or 
                    "bioc-static.cdn.bcebos.com" in response.text):
                    logger.error("被百度验证码拦截！")
                    raise ex.NetworkError("请求被验证码拦截", url=url)

                if response.status_code == 200:
                    return response
                else:
                    logger.warning(f"非200响应: {response.status_code}")

            except httpx.RequestError as e:
                logger.warning(f"网络错误 (第 {attempt + 1}/{MAX_RETRIES} 次): {e}")
            except Exception as e:
                logger.error(f"意外错误: {e}")

        raise ex.NetworkError(f"请求在 {MAX_RETRIES} 次重试后失败", url=url)

    async def _get_response(self, url: str) -> httpx.Response:
        """
        获取指定URL的HTTP响应。

        Args:
            url (str): 要获取的URL。

        Returns:
            httpx.Response: HTTP响应对象。

        Raises:
            ex.NetworkError: 如果请求失败。
        """
        try:
            response = await self.make_tieba_request(url)
            return response
        except ex.NetworkError as e:
            logger.warning(f"请求失败: {url} - {e.message}")
            raise

    async def wait_before_next_request(self):
        """
        异步等待一段时间后再发送下一个请求。

        等待时间根据配置的延迟设置计算。
        """
        delay = self._get_delay()
        await asyncio.sleep(delay)

    def _get_delay(self) -> float:
        """
        计算发送下一个请求前的延迟时间。

        Returns:
            float: 计算出的延迟时间（秒）。
        """
        base = self.delay_config['base_delay']
        if self.delay_config['jitter']:
            jitter = random.uniform(-0.3, 0.3)
            delay = base * (1 + jitter)
        else:
            delay = base
        return max(self.delay_config['min_delay'], min(delay, self.delay_config['max_delay']))

    # =============== 页面解析（纯同步/数据提取） ===============

    def get_max_page(self, soup: BeautifulSoup) -> int:
        """
        获取帖子最大页数。

        Args:
            soup (BeautifulSoup): 帖子页面的HTML解析对象。

        Returns:
            int: 帖子最大页数，默认为1。
        """
        max_page = 1
        if not soup or not self.is_valid_post_page(soup):
            return max_page
        try:
            last_page_tag = soup.find('a', string='尾页')
            if not last_page_tag:
                last_page_tag = soup.find('a', string=lambda s: s and '尾页' in s)
            if last_page_tag:
                href = last_page_tag.get('href', '')
                if href:
                    parsed = urlparse(href)
                    query_params = parse_qs(parsed.query)
                    pn_value = query_params.get('pn', [None])[0]
                    if pn_value and pn_value.isdigit():
                        max_page = int(pn_value)
        except Exception as e:
            logger.warning(f"提取最大页数失败：{e}")
        return max_page

    def is_valid_post_page(self, soup: BeautifulSoup) -> bool:
        """
        检查页面是否为有效的帖子页面。

        Args:
            soup (BeautifulSoup): 帖子页面的HTML解析对象。

        Returns:
            bool: 如果是有效帖子页面返回True，否则返回False。
        """
        if soup.find('body', class_=lambda x: x and 'page404' in x):
            error_title = soup.find('h1', class_='main-title')
            if error_title and '被隐藏' in error_title.get_text():
                return False
        body = soup.find('body')
        if not body or not body.get_text(strip=True):
            return False
        if not soup.select('.l_post, .j_l_post'):
            if soup.find(string=lambda text: text and ('不存在' in text or '无法访问' in text)):
                return False
        if not soup.find('h3', class_='core_title_txt'):
            return False
        return True

    def extract_all_floors(self, soup: BeautifulSoup) -> List[FloorData]:
        """
        提取帖子页面中的所有楼层数据。

        Args:
            soup (BeautifulSoup): 帖子页面的HTML解析对象。

        Returns:
            List[FloorData]: 楼层数据列表。
        """
        floors_data = []
        floor_containers = soup.find_all('div', class_='l_post')
        for container in floor_containers:
            floor_data = self.extract_single_floor(container)
            if floor_data:
                floors_data.append(floor_data)
        return floors_data

    def extract_single_floor(self, container: BeautifulSoup) -> FloorData:
        """
        提取单个楼层的数据。

        Args:
            container (BeautifulSoup): 楼层的HTML容器。

        Returns:
            FloorData: 单个楼层的数据。
        """
        author_elem = container.find(
            'a', class_=lambda classes: classes and 'p_author_name' in classes and 'j_user_card' in classes
        )
        author = author_elem.text.strip() if author_elem else '未知作者'

        content_elem = container.find('div', class_='post_bubble_middle_inner')
        if not content_elem:
            content_elem = container.find('div', class_='d_post_content j_d_post_content')
        content, images = self.extract_content_with_formatting(content_elem)

        floor_info = self.extract_floor_info(container)
        return {
            'author': str(author),
            'content': str(content),
            'images': list(images),
            'local_images': [],
            'floor_number': int(floor_info['floor_number']),
            'post_time': str(floor_info['post_time']),
            'ip_location': str(floor_info['ip_location']),
            'device': str(floor_info['device']),
        }

    def extract_content_with_formatting(self, content_elem: BeautifulSoup | None) -> Tuple[str, List[str]]:
        """
        提取楼层内容并格式化，同时提取图片链接。

        Args:
            content_elem (BeautifulSoup | None): 楼层内容的HTML元素。

        Returns:
            Tuple[str, List[str]]: 格式化后的内容和图片链接列表。
        """
        if not content_elem:
            return "", []
        content_parts = []
        images = []
        for element in content_elem.contents:
            if isinstance(element, str):
                text = element.strip()
                if text:
                    content_parts.append(text)
            elif element.name == 'br':
                content_parts.append('\n')
            elif element.name == 'img':
                if 'BDE_Image' in element.get('class', []):
                    img_url = element.get('src', '')
                    if img_url:
                        images.append(img_url)
                        filename = self.get_image_filename(img_url)
                        content_parts.append(f'[图片：{filename}]')
            # 新增：处理<a>标签的链接提取
            elif element.name == 'a':
                href = element.get('href', '').strip()
                link_text = element.get_text(strip=True)
                # 过滤空链接，保留有效链接（按Markdown格式拼接）
                if href:
                    # 如果链接文本为空，用"网页链接"作为默认文本
                    if not link_text:
                        link_text = "网页链接"
                    content_parts.append(f"[{link_text}]({href})")
                # 即使链接为空，也保留链接文本（避免丢失内容）
                elif link_text:
                    content_parts.append(link_text)
        full_content = ' '.join(content_parts)
        return full_content, images

    def extract_floor_info(self, container: BeautifulSoup) -> Dict[str, int | str]:
        """
        提取楼层的附加信息（楼层号、时间、IP属地、设备）。

        Args:
            container (BeautifulSoup): 楼层的HTML容器。

        Returns:
            Dict[str, int | str]: 楼层的附加信息。
        """
        floor_info = {'floor_number': 0, 'post_time': '', 'ip_location': '', 'device': ''}
        tail_wrap = container.find('div', class_='post-tail-wrap')
        if not tail_wrap:
            return floor_info

        ip_span = tail_wrap.find('span', string=lambda text: text and 'IP属地:' in text)
        if ip_span:
            floor_info['ip_location'] = ip_span.get_text().replace('IP属地:', '').strip()

        tail_infos = tail_wrap.find_all('span', class_='tail-info')
        for info in tail_infos:
            text = info.get_text().strip()

            if '来自' in text:
                device_link = info.find('a')
                if device_link:
                    floor_info['device'] = device_link.get_text().strip()
            elif '楼' in text:
                floor_text = text.replace('楼', '').strip()
                try:
                    floor_info['floor_number'] = int(floor_text)
                except ValueError:
                    floor_info['floor_number'] = 0
            elif self.is_time_format(text):
                floor_info['post_time'] = text
        return floor_info

    def is_time_format(self, text: str) -> bool:
        """
        检查字符串是否为时间格式。

        Args:
            text (str): 要检查的字符串。

        Returns:
            bool: 如果是时间格式返回True，否则返回False。
        """
        time_pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}'
        return re.match(time_pattern, text) is not None

    def extract_new_floors(self, current_floors: List[FloorData], history_max_floor: int) -> List[FloorData]:
        """
        从当前楼层列表中提取新增楼层。

        Args:
            current_floors (List[FloorData]): 当前楼层数据列表。
            history_max_floor (int): 历史最大楼层号。

        Returns:
            List[FloorData]: 新增楼层数据列表。
        """
        return [
            floor for floor in current_floors
            if floor['floor_number'] > history_max_floor]

    # =============== 核心爬取逻辑（完整/增量） ===============
    async def crawl_full_post(self, url: str, see_lz: bool = False) -> PostData | None:
        """
        异步抓取帖子的完整内容（全页数、全楼层），支持「只看楼主」模式。
        
        Args:
            url: 帖子原始URL
            see_lz: 是否强制只看楼主模式（默认从URL中解析）
            
        Returns:
            完整的帖子数据对象（含所有楼层、图片信息）；帖子无效时返回None
            
        Raises:
            InvalidURLError: 无法从URL提取帖子ID
            NetworkError: 请求失败或响应状态码非200
        """
        if not see_lz:
            see_lz = 'see_lz=1' in url

        normalized_url = normalize_url(url=url, see_lz=see_lz)
        post_id = extract_posts_id(url=normalized_url)
        if not post_id:
            raise ex.InvalidURLError("无法提取帖子ID", url=url)

        all_floors: List[FloorData] = []

        max_validation_retries = 3
        for attempt in range(1, max_validation_retries):
            response = await self._get_response(normalized_url)
            soup = BeautifulSoup(response.content, 'lxml')
            
            if response.status_code != 200:
                logger.warning(f"获取页面失败（第 {attempt} 次）: {normalized_url}")
                if attempt < max_validation_retries - 1:
                    await self.wait_before_next_request()
                    continue
                raise ex.NetworkError("请求失败或响应无效", url=normalized_url)
            
            if self.is_valid_post_page(soup):
                break  # 验证成功
            
            logger.warning(f"帖子验证失败（第 {attempt} 次），重试中...: {normalized_url}")
            if attempt < max_validation_retries - 1:
                await self.wait_before_next_request()
        else:
            # 所有重试都失败
            logger.warning(f"帖子无效（被隐藏/已删除/不存在）: {normalized_url}")
            return None

        bar_elem = soup.find('a', class_='card_title_fname')
        bar_name = bar_elem.get_text(strip=True) if bar_elem else ''

        title_elem = soup.find('h3', class_='core_title_txt')
        title = title_elem.get('title', '').strip() if title_elem else '未知标题'

        first_page_floors = self.extract_all_floors(soup)
        all_floors.extend(first_page_floors)

        max_page_num = self.get_max_page(soup)

        # 重写抓取后续页逻辑，引入线程池
        if max_page_num > 1:
            concurrency = 3
            semaphore = asyncio.Semaphore(concurrency)
            tasks = [
                self.crawl_single_post_page(normalized_url, page_num, semaphore)
                for page_num in range(2, max_page_num + 1)
            ]
            
            page_results = await asyncio.gather(*tasks, return_exceptions=False)
            for page_floors in page_results:
                all_floors.extend(page_floors)
        
        max_floor_number = max((f['floor_number'] for f in all_floors), default=0)

        post_data: PostData = {
            'post_id': post_id,
            'title': title,
            'see_lz': see_lz,
            'url': normalized_url,
            'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_pages': max_page_num,
            'total_floors': len(all_floors),
            'floors': all_floors,
            'images_downloaded': 0,
            'images_dir': '',
            'max_floor_number': max_floor_number,
            'bar': bar_name
        }

        # 下载图片
        await self.download_all_images(post_data, post_id)
        self.save_post_data(post_data)
        logger.info(f"爬取成功！帖子：《{title}》，共 {len(all_floors)} 层")
        self.index_manager.add_to_index(post_data)
        return post_data
    
    async def crawl_single_post_page(
        self, 
        base_url: str, 
        page: int, 
        semaphore: asyncio.Semaphore | None = None
    ) -> List[FloorData]:
        """
        复用型异步爬取帖子指定页码的楼层数据，支持信号量限制并发。
        
        Args:
            base_url: 帖子基准URL（不含pn页码参数）
            page: 要爬取的页码
            semaphore: 异步信号量（可选，用于限制并发爬取数）
            
        Returns:
            该页码下的所有楼层数据列表
        """
        if semaphore:
            async with semaphore:
                return await self._do_crawl_single_page(base_url, page)
        else:
            return await self._do_crawl_single_page(base_url, page)
    
    async def _crawl_pages_concurrently(
    self,
    normalized_url: str,
    start_page: int,
    end_page: int,
    concurrency: int = 3
) -> List[FloorData]:
        """
        通用并发爬取指定页码范围的页面，返回所有楼层数据
        
        Args:
            normalized_url: 标准化后的帖子URL
            start_page: 起始页码（包含）
            end_page: 结束页码（包含）
            concurrency: 并发数（默认3）
        
        Returns:
            所有页面的楼层数据列表（含异常页面的空列表）
        """
        if start_page > end_page:
            return []  # 页码范围无效，直接返回空
        
        semaphore = asyncio.Semaphore(concurrency)
        # 生成爬取任务
        tasks = [
            self.crawl_single_post_page(normalized_url, page_num, semaphore)
            for page_num in range(start_page, end_page + 1)
        ]
        await self.wait_before_next_request()
        # 执行任务并合并结果
        page_results = await asyncio.gather(*tasks, return_exceptions=True)
        all_floors = []
        for idx, page_floors in enumerate(page_results):
            page_num = start_page + idx
            # 跳过异常结果，避免混入Exception对象
            if isinstance(page_floors, Exception):
                logger.error(f"并发爬取第 {page_num} 页失败：{str(page_floors)}")
                continue
            all_floors.extend(page_floors)
        return all_floors
        
    async def _do_crawl_single_page(self, base_url: str, page: int) -> List[FloorData]:
        """
        内部实现：执行单页爬取的核心逻辑（拼接URL、请求、解析楼层）。
        
        Args:
            base_url: 帖子基准URL（不含pn页码参数）
            page: 要爬取的页码
            
        Returns:
            该页码下的所有楼层数据列表
        """
        page_url = append_pn_param(base_url=base_url, page=page)
        page_resp = await self._get_response(page_url)
        page_soup = BeautifulSoup(page_resp, 'lxml')
        page_floors = self.extract_all_floors(page_soup)
        
        await self.wait_before_next_request()
        
        return page_floors
    
    async def crawl_additional_pages(
    self, 
    start_page: int, 
    end_page: int, 
    normalized_url: str, 
    history_max_floor_number: int,
    concurrency: Optional[int] = None,  # None表示串行，>0表示并发数
    batch_size: int = 5  # 当并发时，控制每批处理的页数
) -> List[FloorData]:
        """
        爬取指定页码范围的新增页面，并筛选出历史未爬取的楼层。
        支持串行和并发两种模式。
        
        Args:
            start_page: 起始页码（包含）
            end_page: 结束页码（不包含）
            normalized_url: 标准化后的帖子URL
            history_max_floor_number: 历史最大楼层号（用于过滤重复楼层）
            concurrency: 并发数，None表示串行，>0表示最大并发请求数
            batch_size: 当使用并发模式时，每批处理的页数，避免一次性创建过多任务
            
        Returns:
            新增页面中的所有新增楼层数据列表
        """
        additional_floors = []
        pages_to_fetch = list(range(start_page, end_page))
        
        if not pages_to_fetch:
            return additional_floors
        
        # 根据页面数量自动决定策略
        if concurrency is None:
            # 自动选择策略：页面少则串行，页面多则并发
            if len(pages_to_fetch) <= 3:  # 少于等于3页，串行更简单
                concurrency = None
            else:
                concurrency = min(3, len(pages_to_fetch))  # 默认最大3个并发
        
        if concurrency is None or concurrency <= 1:
            # 串行模式（原有逻辑）
            for page in pages_to_fetch:
                page_url = append_pn_param(normalized_url, page)
                page_response = await self._get_response(url=page_url)

                if not page_response or page_response.status_code != 200:
                    logger.warning(f"无法获取第 {page} 页，跳过")
                    continue
                
                page_soup = BeautifulSoup(page_response.content, 'lxml')
                page_floors = self.extract_all_floors(page_soup)
                page_new_floors = self.extract_new_floors(page_floors, history_max_floor_number)
                additional_floors.extend(page_new_floors)
                await self.wait_before_next_request()  # 控制请求频率
                
        else:
            # 并发模式（分批次处理）
            semaphore = asyncio.Semaphore(concurrency)
            
            # 将页面分批处理，避免一次性创建过多任务
            for i in range(0, len(pages_to_fetch), batch_size):
                batch = pages_to_fetch[i:i + batch_size]
                
                async def fetch_page(page: int) -> List[FloorData]:
                    async with semaphore:
                        page_url = append_pn_param(normalized_url, page)
                        try:
                            page_response = await self._get_response(url=page_url)
                            if not page_response or page_response.status_code != 200:
                                logger.warning(f"无法获取第 {page} 页，跳过")
                                return []
                            
                            page_soup = BeautifulSoup(page_response.content, 'lxml')
                            page_floors = self.extract_all_floors(page_soup)
                            page_new_floors = self.extract_new_floors(page_floors, history_max_floor_number)
                            
                            # 控制请求频率（即使是并发，也要适当延迟）
                            await self.wait_before_next_request()
                            
                            return page_new_floors
                        except Exception as e:
                            logger.error(f"处理第 {page} 页时出错: {e}")
                            return []
                
                # 并发执行当前批次
                tasks = [fetch_page(page) for page in batch]
                batch_results = await asyncio.gather(*tasks)
                
                # 合并结果
                for result in batch_results:
                    additional_floors.extend(result)
        
        return additional_floors
             
    async def update_existed_post(self, url: str) -> None | PostData:
        """
        增量更新已爬取的帖子：优先检查历史末页新增楼层，再爬取新增页码，合并数据并下载图片。
        
        Returns:
            有更新时返回更新后的帖子数据；无更新返回None
        
        Raises:
            InvalidURLError: URL格式无效或无法提取帖子ID
            PostNotFoundError: 帖子不在索引中
            NetworkError: 网络请求失败（含历史末页无法访问）
            ParseError: 页面解析失败（如末页无楼层数据）
            FileIndexError: 读取本地历史帖子数据失败
        """
        # 加载现有数据
        logger.info(f"开始增量更新帖子: {url}")
        current_see_lz = 'see_lz=1' in url
        normalized_url = normalize_url(url, current_see_lz)
        if not normalized_url:
            logger.error("无法标准化URL，无法更新")
            raise ex.InvalidURLError("URL格式无效，无法更新", url=url)

        post_id = extract_posts_id(normalized_url)
        if not post_id:
            logger.error("无法从URL中提取帖子ID，无法更新")
            raise ex.InvalidURLError("无法提取帖子ID，无法更新", url=url)    

        # 加载索引和现有数据
        index = self.index_manager.load_index()
        index_key = self.index_manager.get_index_key(post_id, current_see_lz)
        if index_key not in index:
            logger.error("索引中未找到该帖子，无法更新")
            raise ex.PostNotFoundError("帖子未找到，无法更新", url=url)
    
        history_post_index = index[index_key]
        history_file_path = os.path.join(os.path.dirname(self.index_file), history_post_index['file_path'])

        # 读取本地历史记录
        try:
            with open(history_file_path, 'r', encoding='utf-8') as f:
                history_post_data = json.load(f)
        except Exception as e:
            logger.error(f"读取历史帖子数据失败: {e}")
            raise ex.FileIndexError("读取历史帖子数据失败，无法更新", url=url)

        # 获取当前帖子首页信息
        response = await self._get_response(normalized_url)
        current_soup = BeautifulSoup(response.content, 'lxml')
        if not self.is_valid_post_page(current_soup):
            logger.warning(f"帖子已失效（被隐藏或删除），跳过更新: {normalized_url}")
            return None
    
        current_max_page_number = self.get_max_page(current_soup)
    
        # 提取历史数据
        history_max_page_number = history_post_data.get('total_pages', 1)
        history_max_floor_number = history_post_data.get('max_floor_number', 0)
        recorded_images_dir = history_post_data.get('images_dir', '')
        present_images_dir = self.get_image_path(current_see_lz, post_id=post_id)
        if recorded_images_dir and recorded_images_dir != present_images_dir:
            logger.info(f"检测到图片目录变更，更新历史记录中的图片目录路径;{present_images_dir}")
            history_post_data['images_dir'] = present_images_dir

        new_floors: List[FloorData] = []  # 用于存储新增楼层

        # 核心优化：优先检查历史末页是否有更新
        effective_last_page = min(history_max_page_number, current_max_page_number)
    
        # 获取历史末页内容（带重试机制）
        effective_last_page_url = append_pn_param(normalized_url, effective_last_page)
        effective_last_page_response = None
    
        max_try = 3
        for attempt in range(max_try):
            effective_last_page_response = await self._get_response(effective_last_page_url)
            if effective_last_page_response and effective_last_page_response.status_code == 200:
                break
            elif attempt < max_try - 1:
                logger.info(f"获取历史末页失败，第{attempt + 1}次重试...")
                await self.wait_before_next_request()
    
        # 如果历史末页获取失败，直接退回
        if not effective_last_page_response or effective_last_page_response.status_code != 200:
            logger.warning(f"无法访问历史末页（第{effective_last_page}页），更新终止")
            raise ex.NetworkError("无法访问历史末页，更新终止", url=effective_last_page_url)

        # 解析历史末页楼层
        effective_last_page_soup = BeautifulSoup(effective_last_page_response.content, 'lxml')
        effective_last_page_floors = self.extract_all_floors(effective_last_page_soup)
    
        if not effective_last_page_floors:
            logger.warning("历史末页未找到楼层数据，可能帖子结构已变化")
            raise ex.ParseError("历史末页未找到楼层数据，可能帖子结构已变化", url=effective_last_page_url)
    
        # 计算历史末页的最大楼层号
        effective_last_page_max_floor = max(floor['floor_number'] for floor in effective_last_page_floors)
        have_new_floors = effective_last_page_max_floor > history_max_floor_number
    
        logger.info(f"历史末页最大楼层: {effective_last_page_max_floor}, 是否有新增: {have_new_floors}")
        
        # 逻辑判断：根据是否有新增楼层和页数变化决定后续操作
        if have_new_floors:
            # 提取历史末页中的新增楼层
            page_new_floors = self.extract_new_floors(effective_last_page_floors, history_max_floor_number)
            new_floors.extend(page_new_floors)
            logger.info(f"历史末页发现 {len(page_new_floors)} 个新增楼层")
            
            if current_max_page_number > history_max_page_number:
                # 页数增加：爬取新增页码范围，直接合并所有楼层
                additional_floors = await self._crawl_pages_concurrently(
                    normalized_url=normalized_url,
                    start_page=history_max_page_number + 1,
                    end_page=current_max_page_number,
                    concurrency=3
                )
                new_floors.extend(additional_floors)

            elif current_max_page_number < history_max_page_number:
                # 页数减少：全量爬取当前所有页面，筛选新增楼层
                logger.warning(f"帖子页数从 {history_max_page_number} 减少到 {current_max_page_number}，可能发生了删楼")
                all_current_floors = await self._crawl_pages_concurrently(
                    normalized_url=normalized_url,
                    start_page=1,
                    end_page=current_max_page_number,
                    concurrency=3
                )
                # 筛选出历史最大楼层之后的新增楼层
                new_floors.extend(self.extract_new_floors(all_current_floors, history_max_floor_number))

            else:
                # 页数不变：仅日志提示，无额外操作（新增楼层逻辑在别处处理）
                logger.info("页数未更新，完成对历史末页新增楼层的爬取")
            
        else:
            # 没有新增楼层，但可能有新增页
            if current_max_page_number > history_max_page_number:
                logger.info("历史末页无新增楼层，但检测到新增页数，开始爬取新增页")
                additional_floors = await self.crawl_additional_pages(
                    start_page=history_max_page_number + 1, 
                    end_page=current_max_page_number + 1, 
                    normalized_url=normalized_url, 
                    history_max_floor_number=history_max_floor_number,
                    concurrency=None,
                    batch_size=5
                )
                new_floors.extend(additional_floors)
            else:
                logger.info(f"《{history_post_data['title']}》未检测到任何更新，帖子已是最新状态")
                return None

        # 处理无新增楼层的情况（可能在新增页中也没有找到新楼层）
        if not new_floors:
            logger.info("未检测到任何新增楼层，帖子已是最新状态")
            return None

        # 合并楼层数据（去重并排序）
        updated_floors = history_post_data['floors'] + new_floors
        unique_floors = {f['floor_number']: f for f in updated_floors}.values()
        updated_floor_list = sorted(unique_floors, key=lambda x: x['floor_number'])

        # 下载新增楼层图片
        await self.download_new_images(history_post_data, new_floors)

        # 计算更新后的数据
        new_max_floor_number = max(f['floor_number'] for f in updated_floor_list)
        total_images = sum(len(floor['local_images']) for floor in updated_floor_list)
        new_images_count = sum(len(floor['local_images']) for floor in new_floors)

        # 构建更新后的数据对象
        updated_post_data: PostData = {
            'post_id': history_post_data['post_id'],
            'title': history_post_data['title'],
            'see_lz': history_post_data['see_lz'],
            'url': history_post_data['url'],
            'crawl_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_pages': current_max_page_number,
            'total_floors': len(updated_floor_list),
            'floors': updated_floor_list,
            'images_downloaded': history_post_data.get('images_downloaded', 0) + new_images_count,
            'images_dir': history_post_data.get('images_dir', ''),
            'max_floor_number': new_max_floor_number,
            'bar':history_post_data.get('bar', '')
        }

        # 保存更新后的数据并更新索引
        self.save_post_data(updated_post_data)
        self.index_manager.add_to_index(updated_post_data)
        
        logger.info(f'更新完成：新增 {len(new_floors)} 个楼层，新增 {new_images_count} 张图片，'
            f'当前总楼层 {len(updated_floor_list)}，总图片数 {total_images}')
        
        return updated_post_data

    # =============== 图片处理（下载/去重/存储） ===============
    
    async def _download_images_concurrently(
        self,
        image_urls: List[str],
        save_dir: str,
        post_id: str,
        existing_map: Optional[Dict[str, str]] = None,
        max_concurrency: int = 5
    ) -> Dict[str, str]:
        """
        通用并发图片下载器（支持去重 + 限流）
        
        Args:
            image_urls: 所有需要下载的图片URL列表
            save_dir: 本地保存目录
            post_id: 帖子ID（用于Referer）
            existing_map: 已存在图片映射 {url: local_path}（用于跳过）
            max_concurrency: 最大并发数
        
        Returns:
            {img_url: local_path 或 '[下载失败...]'}
        """
        os.makedirs(save_dir, exist_ok=True)
        existing_map = existing_map or {}
        result_map = dict(existing_map)  # 包含已存在的
        
        # 去重：只下载未存在的
        urls_to_download = [url for url in image_urls if url not in existing_map]
        if not urls_to_download:
            return result_map

        semaphore = asyncio.Semaphore(max_concurrency)

        async def _download_single(url: str) -> Tuple[str, str]:
            async with semaphore:
                if url in result_map:
                    return url, result_map[url]
                path = await self.download_image(url, save_dir, post_id)
                return url, path or f'[下载失败：{url}]'

        tasks = [_download_single(url) for url in urls_to_download]
        results = await asyncio.gather(*tasks)
        
        # 合并结果
        for url, path in results:
            result_map[url] = path
        
        return result_map
    
    async def download_image(self, img_url: str, save_dir: str, post_id: str) -> None | str | Path:
        """
        异步下载单张图片，支持重试机制和反爬Referer头。
        
        Args:
            img_url: 图片远程URL
            save_dir: 本地保存目录
            post_id: 帖子ID（用于构造Referer头）
            
        Returns:
            图片本地保存路径（下载成功）；None（下载失败）
        """
        if self.client is None or self.client.is_closed:
            await self._initialize_client()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                headers = {"Referer": f"https://tieba.baidu.com/p/{post_id}"}
                
                response = await self.client.get(img_url, timeout=10, headers=headers)
                response.raise_for_status()

                filename = self.get_image_filename(img_url)
                save_path = os.path.join(save_dir, filename)
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                return save_path
                            
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.warning(f"图片下载失败：{img_url}，错误：{e}")
                    return None
                wait_time = 1 * (attempt + 1)
                logger.info(f"图片下载失败（第{attempt + 1}次重试，{wait_time}秒后重试）：{img_url}，错误：{e}")
                await asyncio.sleep(wait_time)
        return None

    async def download_all_images(self, post_data: PostData, post_id: str) -> None:
        """
        从新抓取的贴吧帖子中下载所有图片并保存到本地。

        此方法适用于首次下载的帖子。它会基于帖子ID和查看模式（see_lz/full）创建一个专门的图片目录，
        并发地下载所有楼层中的独特图片（有速率限制），并将每个楼层对应的本地图片路径添加至`local_images`字段。

        Args:
            post_data: 包含所有楼层及其图片URL的帖子数据结构。
            post_id: 贴子的数字ID，用于构建Referer请求头和图片存储目录名称。

        Side Effects:
            - 在`IMAGES_DIR`下创建子目录（例如："7833341768_see_lz"）
            - 将图片文件写入磁盘
            - 修改`post_data`，添加：
                - 每个楼层的`local_images`列表
                - `images_downloaded` (int): 成功下载的图片总数
                - `images_dir` (str): 图片存储目录路径
        """
        save_dir = self.get_image_path(post_data['see_lz'], post_id)
        os.makedirs(save_dir, exist_ok=True)
        
        all_urls = [img for floor in post_data['floors'] for img in floor['images']]
        url_to_path = await self._download_images_concurrently(
            image_urls=all_urls,
            save_dir=save_dir,
            post_id=post_id,
            max_concurrency=5
        )
        
        # 回填 local_images
        for floor in post_data['floors']:
            floor['local_images'] = [url_to_path[img] for img in floor['images']]
        
        post_data['images_downloaded'] = sum(
            1 for p in url_to_path.values() if not p.startswith('[下载失败')
        )
        post_data['images_dir'] = save_dir
        
    async def download_new_images(self, post_data: PostData, new_floors: List[FloorData]) -> None:
        """
        此方法设计用于对现有帖子的增量更新，仅从帖子更新时新增的楼层下载图片。

        Args:
            post_data: 上次抓取的帖子数据，必须包含有效的`images_dir`和带有`local_images`的历史`floors`。
            new_floors: 新发现的可能含有新图片的楼层数据对象列表。

        Side Effects:
            - 重用现有的图片目录 (`post_data['images_dir']`)
            - 只下载之前未见过的图片
            - 修改`new_floors`中的每一层，填充其`local_images`字段
            - 不修改`post_data['images_downloaded']`
        """
        if not new_floors:
            return
        
        # 构建历史已存在映射
        existing_map = {}
        for floor in post_data['floors']:
            for url, local in zip(floor.get('images', []), floor.get('local_images', [])):
                if local and not local.startswith('[下载失败'):
                    existing_map[url] = local

        new_urls = [img for floor in new_floors for img in floor['images']]
        url_to_path = await self._download_images_concurrently(
            image_urls=new_urls,
            save_dir=post_data['images_dir'],
            post_id=post_data['post_id'],
            existing_map=existing_map,
            max_concurrency=5
        )
        
        # 回填新楼层
        for floor in new_floors:
            floor['local_images'] = [url_to_path[img] for img in floor['images']]
            
    def get_image_filename(self, img_url: str) -> str:
        """
        从图片URL提取纯净的文件名（去除URL参数）。
        
        Args:
            img_url: 图片远程URL
            
        Returns:
            仅包含文件名+后缀的字符串（如 "123456.jpg"）
        """
        if '?' in img_url:
            img_url = img_url.split('?')[0]
        return os.path.basename(img_url)
    
    def get_image_path(self, mode: bool, post_id: str) -> str:
        mode_suffix = 'see_lz' if mode else 'full'
        save_dir = os.path.join(IMAGES_DIR, f"{post_id}_{mode_suffix}")
        return save_dir
    
    def _find_existing_image_path(self, post_data: PostData, target_url: str) -> str | None:
        """
        同步查找帖子中已下载图片的本地路径（按URL匹配）。
        
        Args:
            post_data: 帖子完整数据对象
            target_url: 目标图片URL
            
        Returns:
            匹配到的本地路径；未找到/下载失败返回None
        """
        for floor in post_data['floors']:
            for idx, img_url in enumerate(floor['images']):
                if img_url == target_url:
                    return floor['local_images'][idx]
        return None

    # =============== 工具方法（辅助/格式化/存储/删除） ===============
        
    def save_post_data(self, post_data: PostData) -> None:
        """
        同步保存帖子数据到本地JSON文件（UTF-8编码、格式化缩进），并自动生成Markdown文档。
        
        Args:
            post_data: 完整的帖子数据对象
        """
        filename = get_safe_filename(
            post_data['post_id'], post_data['see_lz'], post_data['title']
        )
        filepath = os.path.join(POSTS_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(post_data, f, ensure_ascii=False, indent=2)
        logger.info(f"帖子数据已保存：{filepath}")
        try:
            md_path = convert_post_json_to_markdown(filepath)
        except Exception as e:
            logger.error(f'Markdonw生成失败：{e}')
        

        