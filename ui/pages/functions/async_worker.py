import asyncio
from PySide6.QtCore import Signal, QObject
from logger import logger
from spider.re_spider import TiebaShelf
from spider import exceptions as ex


class AsyncWorker(QObject):
    """
    异步任务处理器：适配 re_spider 的批量爬取接口

    工作流程：
    1. 在 QThread 中运行 asyncio 事件循环
    2. 调用 TiebaShelf.crawl_multi_posts() 批量处理所有 URL
    3. 爬取完成后清理客户端资源
    4. 通过信号返回结果到 UI 线程
    """
    finished = Signal(list)      # 返回 [{url, status, data/error}, ...]
    error = Signal(str)          # 全局错误信息
    progress = Signal(str)       # 进度提示
    task_completed = Signal(str, str)  # url, task_type

    def __init__(self, new_urls=None, update_urls=None, recrawl_urls=None):
        """
        初始化异步工作器

        Args:
            new_urls: 新帖子 URL 列表
            update_urls: 需更新的帖子 URL 列表（增量更新）
            recrawl_urls: 需重新爬取的帖子 URL 列表（强制重爬）
        """
        super().__init__()
        self.spider: TiebaShelf | None = None
        self.new_urls = new_urls or []
        self.update_urls = update_urls or []
        self.recrawl_urls = recrawl_urls or []

    def run_async_task(self):
        """运行异步任务（在 QThread 中调用）"""
        try:
            # 创建新的事件循环（每个线程独立）
            results = asyncio.run(self._run_crawl())
            # 清理爬虫客户端
            self._cleanup_spider()
            # 发送完成信号
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"异步任务执行失败：{e}")
            self._cleanup_spider()
            self.error.emit(str(e))

    def _cleanup_spider(self):
        """清理爬虫对象（非异步，仅置空引用）"""
        if self.spider is not None:
            # 注意：这里不能 await，因为不在异步上下文中
            # 客户端清理已在 _run_crawl 的 finally 中完成
            self.spider = None

    async def _run_crawl(self) -> list:
        """
        执行爬取任务的核心逻辑

        Returns:
            格式化的结果列表 [{url, status, data/error}, ...]
        """
        # 合并 URL 列表（re_spider 自动处理去重和增量判断）
        all_urls = list(set(self.new_urls + self.update_urls + self.recrawl_urls))

        if not all_urls:
            return []

        # 创建爬虫实例
        self.spider = TiebaShelf()

        try:
            # 批量爬取所有帖子
            results = await self.spider.crawl_multi_posts(
                urls=all_urls,
                recrawl_urls=self.recrawl_urls
            )

            # 发送任务完成信号（用于进度条更新）
            for result in results:
                url = result['url']
                if result['status'] == 'success':
                    self.task_completed.emit(url, 'crawl')
                elif result['status'] == 'no_update':
                    self.task_completed.emit(url, 'update')

            return results

        finally:
            # 确保客户端被清理（即使在任务执行过程中）
            await self.spider.cleanup()

    async def _crawl_new(self, url: str) -> dict:
        """
        爬取单个新帖子（保留用于兼容）

        Args:
            url: 帖子 URL

        Returns:
            爬取结果字典
        """
        self.progress.emit(f"爬取新帖：{url}")
        try:
            see_lz = 'see_lz=1' in url
            result = await self.spider.crawl_full_post(url, see_lz=see_lz)
            self.task_completed.emit(url, 'crawl')
            return {
                'url': url,
                'status': 'success' if result else 'failed',
                'data': result
            }
        except ex.InvalidURLError as e:
            logger.error(f"【URL 错误】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ URL 格式错误\n\n{e.url}\n\n请检查链接是否正确")
            return {'url': url, 'status': 'error', 'error': f"URL 错误：{e.message}"}
        except ex.NetworkError as e:
            logger.error(f"【网络错误】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ 网络请求失败\n\n{e.url}\n\n请检查网络连接后重试")
            return {'url': url, 'status': 'error', 'error': f"网络错误：{e.message}"}
        except ex.ParseError as e:
            logger.error(f"【解析错误】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ 页面解析失败\n\n{e.url}\n\n可能是贴吧更新了页面结构")
            return {'url': url, 'status': 'error', 'error': f"解析错误：{e.message}"}
        except ex.PostNotFoundError as e:
            logger.error(f"【帖子不存在】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ 帖子不存在或已被删除")
            return {'url': url, 'status': 'error', 'error': f"帖子不存在：{e.message}"}
        except Exception as e:
            logger.error(f"【未知错误】{type(e).__name__}: {e}")
            self.error.emit(f"❌ 发生未知错误:\n{str(e)}")
            return {'url': url, 'status': 'error', 'error': str(e)}

    async def _update_existing(self, url: str) -> dict:
        """
        更新单个旧帖子（保留用于兼容）

        Args:
            url: 帖子 URL

        Returns:
            更新结果字典
        """
        self.progress.emit(f"更新旧帖：{url}")
        try:
            # re_spider 中 crawl_full_post 已自动处理增量更新
            see_lz = 'see_lz=1' in url
            result = await self.spider.crawl_full_post(url, see_lz=see_lz)
            self.task_completed.emit(url, 'update')
            return {
                'url': url,
                'status': 'updated' if result else 'skipped',
                'data': result
            }
        except ex.InvalidURLError as e:
            logger.error(f"【URL 错误】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ URL 格式错误\n\n{e.url}\n\n请检查链接是否正确")
            return {'url': url, 'status': 'error', 'error': f"URL 错误：{e.message}"}
        except ex.NetworkError as e:
            logger.error(f"【网络错误】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ 网络请求失败\n\n{e.url}\n\n请检查网络连接后重试")
            return {'url': url, 'status': 'error', 'error': f"网络错误：{e.message}"}
        except ex.ParseError as e:
            logger.error(f"【解析错误】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ 页面解析失败\n\n{e.url}\n\n可能是贴吧更新了页面结构")
            return {'url': url, 'status': 'error', 'error': f"解析错误：{e.message}"}
        except ex.PostNotFoundError as e:
            logger.error(f"【帖子不存在】{e.message} | URL: {e.url}")
            self.error.emit(f"❌ 帖子不存在或已被删除")
            return {'url': url, 'status': 'error', 'error': f"帖子不存在：{e.message}"}
        except ex.FileIndexError as e:
            logger.error(f"【文件错误】{e.message}")
            self.error.emit(f"❌ 索引文件错误\n\n请重试或手动修复索引文件")
            return {'url': url, 'status': 'error', 'error': f"文件错误：{e.message}"}
        except Exception as e:
            logger.error(f"【未知错误】{type(e).__name__}: {e}")
            self.error.emit(f"❌ 发生未知错误:\n{str(e)}")
            return {'url': url, 'status': 'error', 'error': str(e)}
