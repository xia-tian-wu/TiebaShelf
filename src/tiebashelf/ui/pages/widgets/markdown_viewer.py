from PySide6.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl
from pathlib import Path
from markdown_it import MarkdownIt
import uuid
import tempfile

def build_standalone_html(md_path: Path, html_body: str) -> str:
    """构建包含完整 CSS/JS 的独立 HTML 文档，可用于浏览器打开。

    Args:
        md_path: Markdown 文件路径（用于解析图片相对路径）。
        html_body: markdown-it 渲染后的 HTML 正文。

    Returns:
        完整的 HTML 文档字符串。
    """
    base_href = QUrl.fromLocalFile(str(md_path.parent.absolute()) + "/").toString()

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<base href="{base_href}">
<style>
/* --- 基础设置 --- */
body {{
    background: #eef1f5;
    margin: 0;
    padding: 20px;
    font-family: "Segoe UI","Microsoft YaHei",sans-serif;
    transition: background 0.3s ease;
}}

.layout {{
    display: flex;
    justify-content: center;
    gap: 20px;
    max-width: 1200px;
    margin: 0 auto;
    align-items: flex-start;
}}

/* --- 侧边栏 TOC --- */
.toc-wrapper {{
    width: 140px;
    flex-shrink: 0;
    position: sticky;
    top: 20px;
    max-height: 93vh;
    overflow-y: auto;
    background: rgba(255, 255, 255, 0.9);
    border-radius: 8px;
    padding: 10px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    direction: rtl;
}}
.toc {{ display: flex; flex-direction: column; gap: 5px; direction: ltr; }}
.toc-wrapper::-webkit-scrollbar {{ width: 6px; }}
.toc-wrapper::-webkit-scrollbar-thumb {{ background-color: #ccc; border-radius: 3px; }}
.toc-wrapper::-webkit-scrollbar-track {{ background: transparent; }}
.toc a {{
    text-decoration: none; color: #555; font-size: 14px; padding: 6px 8px;
    border-radius: 4px; transition: all 0.2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.toc a:hover {{ color: #4a90e2; background: rgba(74, 144, 226, 0.1); }}
.toc a.active {{ color: #4a90e2; font-weight: bold; background: rgba(74, 144, 226, 0.15); border-left: 3px solid #4a90e2; }}

/* --- 侧边栏跳转输入框 --- */
.toc-input-sticky {{
    position: sticky; top: 0; z-index: 2;
    padding: 0 0 8px 0; direction: ltr;
    background: inherit;
}}
.toc-jump-input {{
    width: 100%; box-sizing: border-box; padding: 6px 8px;
    border: 1px solid #ddd; border-radius: 4px; font-size: 13px;
    outline: none; transition: border-color 0.2s; direction: ltr;
    background: white; color: #333;
}}
.toc-jump-input:focus {{ border-color: #4a90e2; }}
.toc-jump-input::placeholder {{ color: #aaa; }}
body.dark-mode .toc-jump-input {{ background: #2d2d44; color: #d0d0e0; border-color: #555577; }}
body.dark-mode .toc-jump-input:focus {{ border-color: #7eb8ff; }}
body.dark-mode .toc-jump-input::placeholder {{ color: #777; }}

/* --- 侧边栏 toast 提示 --- */
.toc-toast {{
    position: fixed; top: 12px; left: 50%; transform: translateX(-50%);
    background: #e74c3c; color: white; padding: 8px 18px; border-radius: 6px;
    font-size: 13px; z-index: 9999; opacity: 0; transition: opacity 0.25s;
    pointer-events: none;
}}
.toc-toast.show {{ opacity: 1; }}

/* --- 主内容区域 --- */
.container {{ flex: 1; max-width: 900px; min-width: 0; }}
.container > p, .container > ul, .container > ol, .container > blockquote, .container > pre, .container > img {{
    background: white; margin: 0; padding: 8px 20px; line-height: 1.6; color: #333; display: block;
}}
.container > ul, .container > ol {{ padding-left: 40px; }}
.container > blockquote {{
    border-left: 4px solid #ddd; margin: 0 0 20px 0; padding: 10px 16px; background: #fafafa; color: #666; border-radius: 6px;
}}
h1 {{ text-align: center; color: #333; margin-bottom: 30px; border-radius: 8px 8px 0 0; }}
h3 {{
    margin-top: 30px; margin-bottom: 0; padding: 15px 20px; background: #ffffff;
    border-left: 5px solid #4a90e2; border-radius: 8px 8px 0 0; font-size: 18px; color: #333; scroll-margin-top: 20px;
}}
h3 + p, h3 + ul, h3 + blockquote {{ border-top: none; }}
hr {{ border: none; height: 1px; background: #ddd; position: relative; }}

img {{
    display: block; margin: 0 auto; background: white; max-width: 100%; height: auto;
    padding: 10px 16px; border-radius: 6px; cursor: zoom-in; box-sizing: border-box; border: 1px solid #eee;
}}

/* --- 搜索高亮样式 --- */
mark {{ background-color: #ffeaa7; color: #2d3436; border-radius: 2px; padding: 0 2px; }}
mark.active-match {{ background-color: #ff9f43; color: white; font-weight: bold; box-shadow: 0 0 4px rgba(255,159,67,0.5); }}

/* --- 深色模式 --- */
body.dark-mode {{ background: #1a1a2e; }}
body.dark-mode .container > p, body.dark-mode .container > ul, body.dark-mode .container > ol,
body.dark-mode .container > blockquote, body.dark-mode .container > pre, body.dark-mode .container > img, body.dark-mode h3 {{
    background: #2d2d44; color: #d0d0e0;
}}
body.dark-mode h3 {{ border-left-color: #7eb8ff; }}
body.dark-mode .toc-wrapper {{ background: rgba(43, 43, 58, 0.95); }}
body.dark-mode a {{ color: #7eb8ff; }}
body.dark-mode .toc a {{ color: #b8b8d1; }}
body.dark-mode .toc a:hover {{ color: #7eb8ff; background: rgba(126, 184, 255, 0.15); }}
body.dark-mode .toc a.active {{ color: #7eb8ff; font-weight: bold; background: rgba(126, 184, 255, 0.2); border-left: 3px solid #7eb8ff; }}
body.dark-mode h1 {{ color: #e8e8f0; }}
body.dark-mode p, body.dark-mode img, body.dark-mode blockquote, body.dark-mode pre {{ background: #2d2d44; color: #d0d0e0; }}
body.dark-mode blockquote {{ border-left-color: #555577; }}
body.dark-mode code {{ background: #3d3d5c; color: #ff9ebb; }}
body.dark-mode hr {{ background: #444466; }}
body.dark-mode img {{ border-color: #444466; }}
body.dark-mode mark {{ background-color: #7c5a00; color: #e8e8f0; }}
body.dark-mode mark.active-match {{ background-color: #d98000; color: #ffffff; }}

/* --- 右上角悬浮工具栏 (搜索 + 日夜切换) --- */
.floating-tools {{
    position: fixed; top: 20px; right: 20px; display: flex; flex-direction: row; gap: 12px; z-index: 1000; align-items: center;
}}

.tool-btn {{
    width: 44px; height: 44px; border-radius: 50%; border: none; cursor: pointer;
    background: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    display: flex; align-items: center; justify-content: center; font-size: 20px; transition: all 0.3s ease; flex-shrink: 0;
}}
.tool-btn:hover {{ transform: scale(1.1); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
body.dark-mode .tool-btn {{ background: #2d2d44; color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }}

/* 日夜模式图标 */
.sun-icon {{ display: block; }} .moon-icon {{ display: none; }}
body.dark-mode .sun-icon {{ display: none; }} body.dark-mode .moon-icon {{ display: block; }}

/* 搜索框组件 */
.search-widget {{
    display: flex; align-items: center; background: #ffffff; border-radius: 22px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15); overflow: hidden; width: 44px; transition: width 0.3s ease;
}}

/* --- 修改后的工具栏样式 --- */

.tool-btn, .search-widget {{ 
    /* 让搜索组件拥有和普通按钮一样的基础过渡和阴影 */
    transition: transform 0.3s ease, background 0.3s ease, box-shadow 0.3s ease, width 0.3s ease;
}} 

/* 统一悬浮放大效果 */
.tool-btn:hover, 
.search-widget:not(:focus-within):not(.expanded):hover {{ 
    transform: scale(1.1); 
    box-shadow: 0 4px 12px rgba(0,0,0,0.2); 
}} 

/* 搜索框组件微调 */
.search-widget {{ 
    display: flex; 
    align-items: center; 
    background: #ffffff; 
    border-radius: 22px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15); 
    overflow: hidden; 
    width: 44px; 
    
}} 


.search-widget .tool-btn:hover {{ 
    transform: none;
    box-shadow: none;
}} 

/* 当搜索框展开时，固定住，不要缩放 */
.search-widget:focus-within, .search-widget.expanded {{
    width: 360px;   /* 从 300px 增加到 360px */
    transform: scale(1) !important;
}}


body.dark-mode .search-widget {{ background: #2d2d44; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }}
.search-input {{
    border: none; outline: none; background: transparent;
    padding: 0 10px;
    flex: 1;          /* 占用剩余空间 */
    min-width: 0;     /* 允许收缩 */
    color: #333; font-size: 14px;
    opacity: 0; transition: opacity 0.3s ease;
}}
body.dark-mode .search-input {{ color: #d0d0e0; }}
.search-widget:focus-within .search-input, .search-widget.expanded .search-input {{ opacity: 1; }}
.search-controls {{
    display: none; align-items: center; padding-right: 22px; gap: 5px; color: #888; font-size: 12px; flex-shrink: 0;max-width: 140px;overflow: hidden;
}}

.search-widget:focus-within .search-controls, .search-widget.expanded .search-controls {{ display: flex; }}
.search-nav-btn {{
    background: transparent; border: none; cursor: pointer; color: #666; font-size: 16px; padding: 2px 5px; border-radius: 4px;
}}
.search-nav-btn:hover {{ background: rgba(0,0,0,0.05); }}
body.dark-mode .search-nav-btn {{ color: #aaa; }} body.dark-mode .search-nav-btn:hover {{ background: rgba(255,255,255,0.1); }}
#searchStats {{
    display: inline-block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 70px;          
}}


/* --- 灯箱 (Lightbox) --- */
.lightbox {{
    position: fixed; display: none; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.85); justify-content: center; align-items: center; z-index: 9999; opacity: 0; transition: opacity 0.3s ease;
}}
.lightbox.active {{ display: flex; opacity: 1; }}
.lightbox img {{
    max-width: 90%; max-height: 90%; background: transparent; padding: 0; border-radius: 4px;
    box-shadow: 0 0 20px rgba(0,0,0,0.5); cursor: zoom-out; transition: transform 0.2s ease;
}}

/* 灯箱右上角 跳转楼层按钮 */
.jump-floor-btn {{
    position: absolute; top: 20px; right: 20px; background: rgba(74, 144, 226, 0.9);
    color: white; border: none; padding: 8px 16px; border-radius: 4px; font-size: 14px;
    cursor: pointer; display: flex; align-items: center; gap: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); transition: background 0.2s;
}}
.jump-floor-btn:hover {{ background: rgba(53, 122, 201, 1); }}

/* 灯箱左上角楼层标签 */
.floor-label {{
    position: absolute;
    top: 20px;
    left: 20px;
    background: rgba(0, 0, 0, 0.6);
    color: white;
    padding: 6px 14px;
    border-radius: 4px;
    font-size: 14px;
    pointer-events: none;   /* 避免遮挡下方按钮 */
    z-index: 10;
}}

.nav {{ position: absolute; top: 50%; transform: translateY(-50%); font-size: 40px; background: rgba(255,255,255,0.1); border: none; color: white; cursor: pointer; padding: 20px 15px; border-radius: 8px; transition: all 0.2s; user-select: none; }}
.nav:hover {{ background: rgba(255,255,255,0.3); }}
.prev {{ left: 20px; }} .next {{ right: 20px; }}
.toolbar {{ position: absolute; bottom: 30px; display: flex; gap: 10px; background: rgba(0,0,0,0.6); padding: 10px 15px; border-radius: 8px; }}
.toolbar button {{ padding: 8px 12px; font-size: 16px; background: rgba(255,255,255,0.2); border: none; color: white; border-radius: 4px; cursor: pointer; transition: all 0.2s; }}
.toolbar button:hover {{ background: rgba(255,255,255,0.4); }}
.image-counter {{ position: absolute; top: 20px; left: 50%; transform: translateX(-50%); color: white; font-size: 14px; background: rgba(0,0,0,0.6); padding: 6px 12px; border-radius: 4px; }}

::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: #e6e6e6; border-radius: 5px; }}
::-webkit-scrollbar-thumb {{ background: #888; border-radius: 5px; opacity: 0.8; }}
::-webkit-scrollbar-thumb:hover {{ background: #555; opacity: 1; }}
body.dark-mode ::-webkit-scrollbar-track {{ background: #2d2d44; }}
</style>
</head>
<body>

<div class="floating-tools">

    <div class="search-widget" id="searchWidget">
        <button class="tool-btn" id="searchIconBtn" title="搜索楼层内容" style="box-shadow:none;">🔍</button>
        <input type="text" id="searchInput" class="search-input" placeholder="在楼层中搜索...">
        <div class="search-controls">
            <span id="searchStats">0/0</span>
            <button class="search-nav-btn" id="searchPrev">▲</button>
            <button class="search-nav-btn" id="searchNext">▼</button>
        </div>
    </div>
    <button class="tool-btn" id="themeToggle" title="切换日夜模式">
        <span class="sun-icon">☀️</span>
        <span class="moon-icon">🌙</span>
    </button>
    
</div>

<div class="layout">
    <div class="toc-wrapper">
        <div class="toc-input-sticky">
            <input type="text" id="jumpInput" class="toc-jump-input" placeholder="跳转至：1~总楼层">
        </div>
        <div class="toc" id="toc">
            <div style="font-size:12px; color:#999; padding:10px;">加载中...</div>
        </div>
    </div>
    <div class="toc-toast" id="tocToast"></div>
    <div class="container">
        {html_body}
    </div>
</div>

<div class="lightbox" id="lightbox">
    <div class="floor-label" id="floorLabel"></div>
    <button class="jump-floor-btn" id="jumpFloorBtn">跳转到该楼层</button>
    <button class="nav prev" id="prevBtn">◀</button>
    <div class="image-counter" id="imageCounter">1 / 1</div>
    <img id="lightbox-img" src="">
    <button class="nav next" id="nextBtn">▶</button>

    <div class="toolbar" id="toolbar">
        <button id="zoom-in">＋</button>
        <button id="zoom-out">－</button>
        <button id="rotate">⟳</button>
        <button id="flip-h">⇋</button>
        <button id="flip-v">⇅</button>
        <button id="reset">还原</button>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {{
    /* ==========================================
       1. 生成目录
       ========================================== */
    const headings = document.querySelectorAll("h1, h3");
    const tocContainer = document.getElementById("toc");
    tocContainer.innerHTML = "";

    if (headings.length === 0) {{
        tocContainer.innerHTML = '<div style="padding:10px; color:#999;">无楼层目录</div>';
    }} else {{
        const fragment = document.createDocumentFragment();
        headings.forEach((h, i) => {{
            const id = "floor_" + i;
            h.id = id;
            const a = document.createElement("a");
            a.href = "#" + id;
            a.textContent = h.tagName === "H1" ? "简介" : "楼层 " + i;
            a.onclick = (e) => {{
                e.preventDefault();
                document.querySelectorAll('.toc a').forEach(link => link.classList.remove('active'));
                a.classList.add('active');
                isManualScroll = true;
                h.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                setTimeout(() => {{
                    isManualScroll = false;
                }}, 1000);
            }};
            fragment.appendChild(a);
        }});
        tocContainer.appendChild(fragment);
    }}

    // 高亮当前楼层
    let isManualScroll = false;
    const tocLinks = document.querySelectorAll(".toc a");
    const observer = new IntersectionObserver((entries) => {{
    if (isManualScroll) return;

    // 从所有正在交叉的条目中，选出距离视口顶部最近的那个楼层
    let bestEntry = null;
    let minTop = Infinity;

    entries.forEach(entry => {{
        if (entry.isIntersecting) {{
            const rect = entry.boundingClientRect;
            // 取元素顶部距离视口顶部的绝对距离
            const top = Math.abs(rect.top);
            if (top < minTop) {{
                minTop = top;
                bestEntry = entry;
            }}
        }}
    }});

    if (bestEntry) {{
        const id = bestEntry.target.id;
        tocLinks.forEach(a => {{
            a.classList.toggle("active", a.getAttribute("href") === "#" + id);
        }});
    }}
}}, {{ threshold: 0.3 }});

    headings.forEach(h => observer.observe(h));

    /* ==========================================
        2. 图片灯箱与【跳转楼层】功能
       ========================================== */
    const imgs = document.querySelectorAll(".container img");
    const lightbox = document.getElementById("lightbox");
    const lightboxImg = document.getElementById("lightbox-img");
    const imageCounter = document.getElementById("imageCounter");
    const jumpFloorBtn = document.getElementById("jumpFloorBtn");

    let currentIndex = 0;
    let scale = 1, rotate = 0, flipH = 1, flipV = 1;
    let currentFloorId = null;

    // 向上查找距离图片最近的楼层标题 (h1 或 h3)
    function findClosestFloor(element) {{
        let curr = element;
        // 先跳出可能包裹的段落 p 标签，直接到达 container 的子元素层级
        while(curr && curr.parentElement && !curr.parentElement.classList.contains('container')) {{
            curr = curr.parentElement;
        }}
        // 往前找同级的标题
        while(curr) {{
            if (curr.tagName === 'H1' || curr.tagName === 'H3') {{
                return curr.id;
            }}
            curr = curr.previousElementSibling;
        }}
        return null;
    }}

    function updateTransform() {{
        lightboxImg.style.transform = `scale(${{scale}}) rotate(${{rotate}}deg) scaleX(${{flipH}}) scaleY(${{flipV}})`;
    }}

    function showImage(index) {{
        if(index < 0) index = imgs.length - 1;
        if(index >= imgs.length) index = 0;
        currentIndex = index;
        lightboxImg.src = imgs[index].src;

        scale = 1; rotate = 0; flipH = 1; flipV = 1;
        updateTransform();
        if (imgs.length > 0) imageCounter.textContent = (currentIndex + 1) + " / " + imgs.length;

        // 查找当前图片所在楼层
        currentFloorId = findClosestFloor(imgs[index]);
        jumpFloorBtn.style.display = currentFloorId ? "flex" : "none";
        
        // 更新左上角楼层标签
        const floorLabel = document.getElementById('floorLabel');
        if (currentFloorId) {{
        const floorElement = document.getElementById(currentFloorId);
        if (floorElement) {{
                const index = parseInt(currentFloorId.split('_')[1], 10);
                floorLabel.textContent = `📍 楼层 ${{index}}`;
        }}
    floorLabel.style.display = 'block';
}} else {{
    floorLabel.style.display = 'none';
}}
    }}

    imgs.forEach((img, i) => {{
        img.onclick = (e) => {{
            e.stopPropagation();
            lightbox.classList.add("active");
            document.body.style.overflow = 'hidden';
            showImage(i);
        }}
    }});

    // 跳转楼层点击事件
    jumpFloorBtn.onclick = (e) => {{
        e.stopPropagation();
        if (currentFloorId) {{
            closeLightbox();
            const target = document.getElementById(currentFloorId);
            if(target) target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
    }};

    lightbox.onclick = (e) => {{ if (e.target === lightbox) closeLightbox(); }};
    document.getElementById("prevBtn").onclick = (e) => {{ e.stopPropagation(); showImage(currentIndex - 1); }}
    document.getElementById("nextBtn").onclick = (e) => {{ e.stopPropagation(); showImage(currentIndex + 1); }}
    document.getElementById("zoom-in").onclick = (e) => {{ e.stopPropagation(); scale *= 1.2; updateTransform(); }}
    document.getElementById("zoom-out").onclick = (e) => {{ e.stopPropagation(); scale /= 1.2; updateTransform(); }}
    document.getElementById("rotate").onclick = (e) => {{ e.stopPropagation(); rotate += 90; updateTransform(); }}
    document.getElementById("flip-h").onclick = (e) => {{ e.stopPropagation(); flipH *= -1; updateTransform(); }}
    document.getElementById("flip-v").onclick = (e) => {{ e.stopPropagation(); flipV *= -1; updateTransform(); }}
    document.getElementById("reset").onclick = (e) => {{ e.stopPropagation(); scale = 1; rotate = 0; flipH = 1; flipV = 1; updateTransform(); }}

    const closeLightbox = () => {{
        lightbox.classList.remove('active');
        setTimeout(() => {{ lightboxImg.src = ""; }}, 300);
        document.body.style.overflow = '';
    }};

    document.addEventListener('keydown', (e) => {{
        // 灯箱打开时只处理灯箱快捷键
        if (lightbox.classList.contains('active')) {{
            if (e.key === "Escape") closeLightbox();
            if (e.key === "ArrowRight") showImage(currentIndex + 1);
            if (e.key === "ArrowLeft") showImage(currentIndex - 1);
            return;
        }}

        // 在输入框中打字时不触发页面快捷键
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        if (e.ctrlKey) {{
            switch (e.key.toLowerCase()) {{
                case 'd':  // Ctrl+D 切换日夜模式
                    themeToggle.click();
                    e.preventDefault();
                    break;
                case 's':  // Ctrl+S 展开搜索框
                    searchWidget.classList.add('expanded');
                    searchInput.focus();
                    e.preventDefault();
                    break;
                case 'a':  // Ctrl+A 聚焦楼层跳转输入框
                    if (jumpInput) jumpInput.focus();
                    e.preventDefault();
                    break;
            }}
        }}

        if (e.key === 'Escape') {{  // Escape 收起搜索框
            searchWidget.classList.remove('expanded');
            clearSearch();
            e.preventDefault();
        }}
    }});

    /* ==========================================
       3. 日夜模式切换
       ========================================== */
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    if (localStorage.getItem('theme') === 'dark') body.classList.add('dark-mode');

    themeToggle.onclick = () => {{
        body.classList.toggle('dark-mode');
        localStorage.setItem('theme', body.classList.contains('dark-mode') ? 'dark' : 'light');
    }};

    /* ==========================================
       4. 仅限楼层内容的搜索功能
       ========================================== */
    const searchInput = document.getElementById('searchInput');
    const searchWidget = document.getElementById('searchWidget');
    const searchStats = document.getElementById('searchStats');
    const container = document.querySelector('.container');
    let searchMatches = [];
    let currentMatchIdx = -1;

    // 清除原有高亮 (还原文本节点，不破坏原有事件)
    function clearSearch() {{
        const marks = container.querySelectorAll('mark');
        marks.forEach(mark => {{
            const parent = mark.parentNode;
            parent.replaceChild(document.createTextNode(mark.textContent), mark);
            parent.normalize(); // 合并相邻文本节点
        }});
        searchMatches = [];
        currentMatchIdx = -1;
        searchStats.textContent = "0/0";
    }}

    // 执行搜索与高亮
    function performSearch(keyword) {{
        clearSearch();
        if (!keyword.trim()) return;

        // 使用 TreeWalker 仅遍历 .container 下的纯文本节点
        const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    {{
        acceptNode: function(node) {{
            if (!node.parentElement) return NodeFilter.FILTER_REJECT;

            const el = node.parentElement;

            // 排除 h3（作者名/楼层标题）
            if (el.tagName === 'H3') {{
                return NodeFilter.FILTER_REJECT;
            }}

            // 排除：紧跟 h3 的"作者信息 p"，且必须包含"楼"和"时间"
            if (el.tagName === 'P') {{
                let prev = el.previousElementSibling;

                while (prev && prev.tagName !== 'H3') {{
                    prev = prev.previousElementSibling;
                }}

                if (prev && prev.tagName === 'H3') {{
                    const text = el.innerText || "";
                    if (text.includes("楼") && text.includes("时间")) {{
                        return NodeFilter.FILTER_REJECT;
                    }}
                }}
            }}

            return NodeFilter.FILTER_ACCEPT;
        }}
    }},
    false
);
        const textNodes = [];
        let node;
        while (node = walker.nextNode()) textNodes.push(node);

        const regex = new RegExp(`(${{keyword}})`, 'gi');
        
        textNodes.forEach(textNode => {{
            if (textNode.nodeValue.match(regex)) {{
                const fragment = document.createDocumentFragment();
                let lastIdx = 0;
                // 利用正则替换创建 mark 标签
                textNode.nodeValue.replace(regex, (match, p1, offset) => {{
                    fragment.appendChild(document.createTextNode(textNode.nodeValue.slice(lastIdx, offset)));
                    const mark = document.createElement('mark');
                    mark.textContent = match;
                    fragment.appendChild(mark);
                    lastIdx = offset + match.length;
                }});
                fragment.appendChild(document.createTextNode(textNode.nodeValue.slice(lastIdx)));
                textNode.parentNode.replaceChild(fragment, textNode);
            }}
        }});

        searchMatches = container.querySelectorAll('mark');
        if (searchMatches.length > 0) {{
            focusMatch(0);
        }} else {{
            searchStats.textContent = "0/0";
        }}
    }}

    // 聚焦到指定索引的高亮结果
    function focusMatch(index) {{
        if (searchMatches.length === 0) return;
        
        if (currentMatchIdx >= 0 && currentMatchIdx < searchMatches.length) {{
            searchMatches[currentMatchIdx].classList.remove('active-match');
        }}
        
        currentMatchIdx = (index + searchMatches.length) % searchMatches.length;
        const targetMark = searchMatches[currentMatchIdx];
        targetMark.classList.add('active-match');
        
        // 滚动到视图并考虑顶部悬浮栏遮挡
        const rect = targetMark.getBoundingClientRect();
        const absoluteY = window.pageYOffset + rect.top - 100; // 留出100px顶部余量
        window.scrollTo({{ top: absoluteY, behavior: 'smooth' }});

        searchStats.textContent = `${{currentMatchIdx + 1}}/${{searchMatches.length}}`;
    }}

    // 事件绑定
    let searchTimeout;
    searchInput.addEventListener('input', (e) => {{
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => performSearch(e.target.value), 300); // 防抖
    }});

    searchInput.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter') {{
            e.preventDefault();
            focusMatch(currentMatchIdx + 1);
        }}
    }});

    document.getElementById('searchPrev').onclick = () => focusMatch(currentMatchIdx - 1);
    document.getElementById('searchNext').onclick = () => focusMatch(currentMatchIdx + 1);
    
    // 点击图标展开搜索框
    document.getElementById('searchIconBtn').onclick = () => {{
        searchWidget.classList.add('expanded');
        searchInput.focus();
    }};

    /* ==========================================
       5. 侧边栏楼层跳转输入框
       ========================================== */
    // toast 提示
    const toastEl = document.getElementById('tocToast');
    let toastTimer = null;
    function showToast(msg) {{
        toastEl.textContent = msg;
        toastEl.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2500);
    }}

    const jumpInput = document.getElementById('jumpInput');
    if (jumpInput) {{
        // 统计侧边栏楼层数量（排除 "简介"）
        const floorLinks = [...document.querySelectorAll(".toc a")].filter(a =>
            a.textContent.startsWith("楼层 ")
        );
        const maxFloor = floorLinks.length;

        if (maxFloor > 0) {{
            jumpInput.placeholder = `跳转至：1~${{maxFloor}}`;
            jumpInput.addEventListener('keydown', (e) => {{
                if (e.key === 'Enter') {{
                    const val = jumpInput.value.trim();
                    const num = Number(val);
                    if (!Number.isInteger(num) || num < 1 || num > maxFloor) {{
                        showToast(`请输入 1~${{maxFloor}} 之间的楼层数字`);
                        jumpInput.value = '';
                        return;
                    }}
                    const targetText = `楼层 ${{num}}`;
                    const link = floorLinks.find(a => a.textContent === targetText);
                    if (link) link.click();
                    jumpInput.value = '';
                }}
            }});
        }}
    }}
}});
</script>
</body>
</html>'''


def render_markdown_to_temp_html(md_path: Path) -> Path:
    """将 Markdown 文件渲染为独立 HTML 临时文件，返回文件路径。"""
    md_text = md_path.read_text(encoding="utf-8")
    md = MarkdownIt("commonmark", {"html": False})
    html_body = md.render(md_text)
    html = build_standalone_html(md_path, html_body)

    temp_dir = Path(tempfile.gettempdir())
    file_name = f"Tshelf_render_{uuid.uuid4().hex}.html"
    temp_path = temp_dir / file_name
    temp_path.write_text(html, encoding="utf-8")
    return temp_path


def cleanup_stale_temp_html():
    """删除 %TEMP% 中所有 Tshelf_render_*.html 遗留文件"""
    temp_dir = Path(tempfile.gettempdir())
    for f in temp_dir.glob("Tshelf_render_*.html"):
        try:
            f.unlink()
        except OSError:
            pass


class MarkdownViewer(QWidget):
    """Markdown 阅读器组件 - 使用 QWebEngineView 渲染"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_md_path = None
        self._temp_html_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        self.setLayout(layout)

    def load_markdown(self, md_path: Path) -> bool:
        """加载并渲染 Markdown 文件"""
        try:
            self.current_md_path = md_path

            if not md_path.exists():
                QMessageBox.warning(
                    self,
                    "文件不存在",
                    f"找不到 Markdown 文件：\n{md_path}"
                )
                return False

            self._cleanup_temp_file()

            temp_file_path = render_markdown_to_temp_html(md_path)
            self._temp_html_path = temp_file_path

            file_url = QUrl.fromLocalFile(temp_file_path)
            self.web_view.load(file_url)

            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "加载失败",
                f"无法加载 Markdown 文件：\n{str(e)}"
            )
            return False

    def _cleanup_temp_file(self):
        """删除临时文件"""
        if self._temp_html_path and self._temp_html_path.exists():
            try:
                self._temp_html_path.unlink()
            except Exception:
                pass
            self._temp_html_path = None

    def closeEvent(self, event):
        """窗口关闭时清理"""
        self._cleanup_temp_file()
        super().closeEvent(event)

    def __del__(self):
        """对象销毁时清理"""
        self._cleanup_temp_file()

