class SpiderError(Exception):
    """爬虫基类异常"""
    def __init__(self, message: str, url: str | None = None):
        self.message = message
        self.url = url
        super().__init__(message)

class NetworkError(SpiderError):
    """网络请求失败（超时、连接错误等）"""
    pass

class ParseError(SpiderError):
    """页面解析失败（HTML 结构变化、缺少关键元素）"""
    pass

class DeletedPostError(SpiderError):
    """帖子已被删除、隐藏或不存在(这个我没用上)"""
    pass

class InvalidURLError(SpiderError):
    """URL 格式无效"""
    pass

class FileIndexError(SpiderError):
    """索引文件读取或写入失败"""
    pass
class InvalidResponseError(SpiderError):
    """响应内容无效或不符合预期"""
    pass
class PostNotFoundError(SpiderError):
    """帖子未找到或不存在"""
    pass
class FloorExtractionError(SpiderError):
    """楼层数据提取失败"""
    pass