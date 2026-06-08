from typing import TypedDict, List, Optional

# 帖子索引元数据（用于去重/记录爬取状态）
class PostIndex(TypedDict, total=False):
    post_id: str
    title: str
    see_lz: bool
    url: str
    last_crawled: str
    total_pages: int
    total_floors: int
    file_path: str
    display_name: str
    max_floor_number: int
    pinned: bool
    tags: List[str]

# 单楼层结构
class FloorData(TypedDict):
    author: str
    content: str
    images: List[str]
    local_images: List[str]
    floor_number: int
    post_time: str
    ip_location: str
    device: str

# 完整帖子数据（最终输出的json结构）
class PostData(TypedDict):
    post_id: str
    title: str
    see_lz: bool
    url: Optional[str]
    crawl_time: str
    total_pages: int
    total_floors: int
    floors: List[FloorData]
    images_downloaded: int
    images_dir: str
    max_floor_number: int
    bar: str
