import os
import re
import asyncio
import httpx
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from urllib.parse import quote, urlparse
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tiebashelf.spider.type_models import FloorData
from tiebashelf.logger import logger
from tiebashelf.spider.utils import get_headers

# === 配置常量 ===
MAX_DOWNLOAD_CONCURRENCY = 12
HTTP_TIMEOUT = 30
RETRY_MAX_ATTEMPTS = 3
RETRY_WAIT_MIN = 2
RETRY_WAIT_MAX = 10

HEADERS = get_headers()

class TiebaImageDownloader:
    """基于正则提取 waterurl 的贴吧图片下载器"""
    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self.client = client or httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=HTTP_TIMEOUT,
            verify=False
        )
        self._own_client = client is None

    async def close(self):
        if self._own_client and self.client and not self.client.is_closed:
            await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # === 正则提取 waterurl ===
    @retry(
        stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True
    )
    async def _extract_waterurl(self, preview_url: str) -> str | None:
        """
        从预览页HTML中用正则提取带签名的 waterurl（分层匹配，兼容多格式）
        
        匹配优先级：
        1. tiebapic.baidu.com (含 ?tbpicau= 参数，优先)
        2. imgsa.baidu.com/forum/pic/item/xxx.jpg (纯净jpg链接)
        3. 通用 https:// 开头的 waterurl (兜底)
        """
        resp = await self.client.get(preview_url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        
        html_text = resp.text
        
        # === 优先级 1: tiebapic.baidu.com (带参数的高清图) ===
        pattern1 = re.compile(r'"waterurl"\s*:\s*"(https://tiebapic\.baidu\.com[^"]+)"')
        match = pattern1.search(html_text)
        if match:
            url = match.group(1).replace("\\/", "/")
            return url
        
        # === 优先级 2: imgsa.baidu.com/forum/pic/item/ (纯净jpg) ===
        pattern2 = re.compile(r'"waterurl"\s*:\s*"(https://imgsa\.baidu\.com/forum/pic/item/[^"]+\.jpg[^"]*)"')
        match = pattern2.search(html_text)
        if match:
            url = match.group(1).replace("\\/", "/")
            return url
        
        # === 优先级 3: 通用 https:// 开头 (兜底方案) ===
        pattern3 = re.compile(r'"waterurl"\s*:\s*"(https://[^"]+)"')
        match = pattern3.search(html_text)
        if match:
            url = match.group(1).replace("\\/", "/")
            # 简单过滤明显无效的链接
            if not any(kw in url.lower() for kw in ['blank', 'error', '404', 'default']):
                return url
        
        # === 全部匹配失败 ===
        return None

    # === 核心：下载图片文件 ===
    @retry(
        stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True
    )
    async def _download_image_file(self, highres_url: str, save_path: Path, post_id: str) -> bool:
        """下载高清图片文件（原子性写入）"""
        download_headers = HEADERS.copy()
        download_headers["Referer"] = f"https://tieba.baidu.com/p/{post_id}"
        
        resp = await self.client.get(highres_url, headers=download_headers, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        
        # 确保目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 原子性写入：先写临时文件，成功后重命名
        temp_path = save_path.with_suffix(".downloading")
        try:
            with open(temp_path, "wb") as f:
                f.write(resp.content)
            temp_path.replace(save_path)
            return True
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass
            raise e

    # === 对外：单张图片下载 ===
    async def download_single_image(
        self,
        preview_url: str,
        save_dir: Path,
        post_id: str
    ) -> Optional[Path]:
        """
        下载单张图片的完整流程

        Args:
            preview_url: 图片预览页URL
            save_dir: 保存目录
            post_id: 帖子ID（用于防盗链）

        Returns:
            下载成功返回本地Path，失败返回None
        """
        try:
            # 1. 从URL提取图片hash，用于命名
            parsed = urlparse(preview_url)
            pic_hash = parsed.query.split("pic_id=")[-1] if "pic_id=" in parsed.query else None
            if not pic_hash:
                pic_hash = Path(parsed.path).stem
            
            filename = f"{pic_hash}.jpg"
            save_path = save_dir / filename

            # 2. 已存在直接返回，天然去重
            if save_path.exists():
                return save_path.resolve()

            # 3. 提取带签名的 waterurl
            highres_url = await self._extract_waterurl(preview_url+'&post_id=123') # 这是贴吧的bug，极少部分图片必须要加上 post_id 参数
            if not highres_url:
                return None

            # 4. 下载图片
            success = await self._download_image_file(highres_url, save_path, post_id)
            if success:
                return save_path.resolve()
            else:
                return None

        except Exception as e:
            logger.warning(f"图片下载失败，URL={preview_url}，错误：{str(e)}")
            return None

    # === 对外：批量下载+自动回填 ===
    async def download_and_backfill(
        self,
        new_floors: List[FloorData],
        new_images_list: List[str],
        save_dir: Path,
        post_id: str
    ) -> Tuple[int, Dict[str, Optional[Path]]]:
        """
        批量下载图片，并自动回填到 new_floors 的 local_images 字段

        Args:
            new_floors: 新增楼层列表（会被修改）
            new_images_list: 新增图片URL列表
            save_dir: 图片保存目录
            post_id: 帖子ID

        Returns:
            (成功下载数量, {图片URL: 本地Path})
        """
        if not new_images_list:
            return 0, {}

        # 1. URL去重
        unique_urls = list(set(new_images_list))
        if len(new_images_list) != len(unique_urls):
            logger.info(f"共 {len(new_images_list)} 张图片，去重后 {len(unique_urls)} 张")

        # 2. 并发控制+批量下载
        semaphore = asyncio.Semaphore(MAX_DOWNLOAD_CONCURRENCY)
        
        async def bounded_download(url: str):
            async with semaphore:
                return url, await self.download_single_image(url, save_dir, post_id)
        
        tasks = [bounded_download(url) for url in unique_urls]
        results = await asyncio.gather(*tasks)
        url_to_path: Dict[str, Optional[Path]] = dict(results)

        # 3. 自动回填到 new_floors
        for floor in new_floors:
            floor_local_paths = []
            for img_url in floor["images"]:
                local_path = url_to_path.get(img_url)
                floor_local_paths.append(str(local_path) if local_path else "")
            floor["local_images"] = [p for p in floor_local_paths if p]

        # 4. 统计成功数量
        success_count = sum(1 for p in url_to_path.values() if p is not None)
        logger.info(f"图片下载完成：成功 {success_count}/{len(unique_urls)} 张")
        
        return success_count, url_to_path