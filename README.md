# TiebaShelf

一个用于将贴吧帖子保存到本地并提供离线浏览的工具。

当前状态：维护中

---

## 截图预览

### 主界面

![主界面截图](./assets/screenshot/main.png)

### 批量管理

![批量管理截图](assets/screenshot/manage.png)

### 勾选和菜单

![批量管理截图](assets/screenshot/batch.png)

### 日志输出

![日志输出截图](assets/screenshot/log.png)

### 白天模式

![日志输出截图](assets/screenshot/day_mode.png)

### 夜间模式

![日志输出截图](assets/screenshot/night_mode.png)

### 图片浏览

![日志输出截图](assets/screenshot/pic_edit.png)

### 搜索功能

![帖子搜索截图](assets/screenshot/search.png)

### 跳转功能

![图片跳转截图](assets/screenshot/jumping.png)

### 修改功能

![帖子修改截图](assets/screenshot/post_edit.png)

### 导入功能

![帖子修改截图](assets/screenshot/import_1.png)
![帖子修改截图](assets/screenshot/import_2.png)

### 标签与顶置

![帖子修改截图](assets/screenshot/pin_and_label.png)
![帖子修改截图](assets/screenshot/label_manage.png)

---

## 功能

* 抓取帖子内容（楼层、用户、时间、IP 属地等）
* 转换为 Markdown 格式
* 本地存储与索引管理
* 增量更新与批量管理
* 支持只看楼主模式
* 内嵌 Chromium 渲染，实现离线浏览
* 内容搜索与图片所在楼层跳转
* 对帖子内容无伤化修改（修改部分保存在patches文件夹中）
* 帖子导入/导出，支持数据迁移与完整性校验
* 定制标签与顶置帖子

---

## 存储结构

```text
data/
├── posts/       # 原始数据（JSON）
├── markdowns/   # 渲染用 Markdown
├── images/      # 图片资源
├── patches/     # 帖子补丁
└── index.json   # 索引
```

---

## 设计

```text
aiotieba API → 数据解析 → 本地存储 → index → Markdown
```

支持智能增量更新、强制重新爬取、图片自动下载。

---

## 技术栈

* **后端核心**：[aiotieba](https://github.com/lumina37/aiotieba) - 贴吧 API 封装库
* **图片下载**：`asyncio` + `httpx`
* **界面框架**：`PySide6`
* **数据解析**：内置解析器

---

## 快速开始

- 在右侧 Release 中下载 `TiebaShelf.zip`，解压后运行 `TiebaShelf.exe` 即可。一般情况下选择最新版。
- 所有爬取内容自动保存在程序目录下的 `data/` 文件夹，与 `TiebaShelf.exe`同级。
- 请不要修改文件夹中的 `TiebaShelf.exe`位置。建议在桌面创建 `TiebaShelf`的快捷方式，方便使用和整体迁移。
- 如果你知道什么是🐭🐭饭，选择内置版本，否则选择纯净正式版。
- 受项目作者水平，编程语言和第三方库等的影响，软件启动较慢，还请谅解。在打开较大帖子时，会比较卡顿。

---

## 本地部署

### 环境要求

* Python 3.11
* Windows 10/11

### 安装步骤

```bash
git clone https://github.com/xia-tian-wu/TiebaShelf.git
cd tieba-spider
pip install -r requirements.txt
python main.py
```

### 打包为 exe

```bash
pyinstaller TiebaShelf.spec
```

生成文件在 `dist/` 目录。

---

## 使用教程

### 爬取单个帖子

1. 进入 **爬取** 页面
2. 粘贴贴吧帖子链接
3. 可选：开启 **只看楼主**
4. 点击 **开始爬取**

### 批量爬取

* 支持多行链接批量导入
* 自动去重，支持增量更新

### 管理已爬取帖子

* 单帖更新 / 重新爬取 / 删除
* 批量操作
* 搜索与筛选
* 右键菜单的使用本地默认md阅读器，编辑帖子，打开资源目录，标签和顶置功能等

### 导入与导出

* 在 **管理** 页面右键帖子或使用批量模式导出
* 导出包包含 JSON / Markdown / 图片，结构完整
* 在 **导入** 页面选择导出文件夹，自动校验完整性
* 支持增量导入，已存在帖子可对比楼层数后选择合并或跳过

---

## 配置说明

可在 `config.py` 调整延迟、重试、超时等策略，避免触发限制。

---

## 常见问题

* **Q：安全验证/拦截？**
  A：本项目基于 aiotieba 官方风格 API，拦截率已大幅降低。避免高频爬取即可。
* **Q：支持楼中楼吗？**
  A：当前版本暂不支持。
* **Q：图片下载失败？**
  A：链接过期、网络问题或反爬限制，可尝试重新爬取。
* **Q：可以多开吗？**
  A：不支持，单实例保护防止数据冲突。

---

## 许可证

MIT License

---

## 致谢

* 核心 API 支持：**[aiotieba](https://github.com/lumina37/aiotieba)** by lumina37
* AI 辅助开发：ChatGPT, Gemini, DeepSeek, Qwen, Doubao
* 开发者：xia-tian-wu

---

<div align="center">

如果这个项目对你有帮助，请给一个 ⭐ Star！

友情链接：[TiebaArchiver](https://github.com/Sorceresssis/TiebaArchiver)

</div>
