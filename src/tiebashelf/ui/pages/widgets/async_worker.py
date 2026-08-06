import asyncio
from PySide6.QtCore import Signal, QObject
from tiebashelf.logger import logger
from tiebashelf.spider.re_spider import TiebaShelf


class AsyncWorker(QObject):
    """
    异步任务处理器：适配 re_spider 的批量爬取接口

    工作流程：
    1. 在 QThread 中运行 asyncio 事件循环
    2. 调用 TiebaSpider.crawl_multi_posts() 批量处理所有 URL
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
        self.shelf: TiebaShelf | None = None
        self.new_urls = new_urls or []
        self.update_urls = update_urls or []
        self.recrawl_urls = recrawl_urls or []

    def run_async_task(self):
        """运行异步任务（在 QThread 中调用）"""
        try:
            # 创建新的事件循环（每个线程独立）
            results = asyncio.run(self._run_crawl())
            # 清理爬虫客户端
            self._cleanup_shelf()
            # 发送完成信号
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"异步任务执行失败：{e}")
            self._cleanup_shelf()
            self.error.emit(str(e))

    def _cleanup_shelf(self):
        """清理爬虫对象"""
        if self.shelf is not None:
            self.shelf = None

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
        self.shelf = TiebaShelf()

        def on_post_done(result: dict):
            url = result['url']
            if url in self.update_urls:
                task_type = 'update'
            elif url in self.recrawl_urls:
                task_type = 'recrawl'
            else:
                task_type = 'crawl'
            self.task_completed.emit(url, task_type)

        try:
            # 批量并发爬取，但每完成一个就通过 on_post_done 回调触发进度信号
            results = await self.shelf.crawl_multi_posts(
                urls=all_urls,
                recrawl_urls=self.recrawl_urls,
                on_post_done=on_post_done
            )

            return results

        finally:
            # 确保客户端被清理（即使在任务执行过程中）
            # await self.spider.cleanup()
            pass