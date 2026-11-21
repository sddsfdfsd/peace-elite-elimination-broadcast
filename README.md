# 和平精英淘汰播报截图工具

一个在本地离线处理游戏录屏、自动截取淘汰播报画面的 Windows 桌面工具。

程序通过 PaddleOCR 检测用户框选的播报区域，并结合文本相似度与感知哈希去重，
将结果集中显示在截图画廊中。所有处理都在本机完成。

> 本项目是个人录屏后处理工具，与腾讯或和平精英官方无关。工具不读取游戏进程、
> 不进行实时监控，也不提供点击、操控游戏或自动答题等功能。

## 功能

- 从本地视频中逐帧采样并识别播报区域
- 图形化框选播报区域，无需手动填写坐标
- PaddleOCR 中文文字检测
- 文本、画面和感知哈希多重去重
- 截图统一显示在程序内的画廊中
- OCR 文本仅生成内存中的哈希，不展示、不保存识别内容
- 支持 CPU；安装兼容的 PaddlePaddle GPU 版本后可使用显卡加速

## 环境要求

- Windows 10/11
- Python 3.11
- 建议将项目放在纯英文路径下
- GPU 模式需要兼容的 NVIDIA 显卡与 CUDA 环境

## 安装

克隆仓库后进入项目目录：

```powershell
git clone https://github.com/sddsfdfsd/peace-elite-elimination-broadcast.git
cd peace-elite-elimination-broadcast
```

CPU 安装：

```bat
install.bat
```

GPU 安装：

```bat
install.bat --gpu
```

默认脚本已配置国内 PyPI 镜像。需要修改镜像或 PaddlePaddle 版本时，可直接编辑
`install.bat`，也可以手动安装 `requirements.txt` 中的依赖。

## 使用

1. 双击 `run.bat`。
2. 选择录屏文件，或把视频拖入左侧预览区。
3. 使用前后帧按钮或底部滑块找到能看到播报的画面。
4. 按住鼠标左键框选播报区域。
5. 点击“开始分析”，完成后在结果画廊中查看截图。

也可以使用命令行：

```powershell
.venv\Scripts\python.exe metro_announcement_capture.py "D:\Videos\录屏.mp4"
```

## OCR 模型

仓库不包含体积较大的 OCR 模型。首次运行时，PaddleOCR 会按官方规则下载所需模型。

如需离线运行，可以将官方 PP-OCRv6 模型放到项目内的 `models` 目录，或通过环境变量
指定模型目录：

```powershell
$env:PEACE_ELITE_MODEL_DIR = "D:\models\peace-elite-ocr"
.\run.bat
```

模型仍受其原始许可证约束。当前使用的 PP-OCRv6 模型采用 Apache-2.0 许可证。

## 隐私说明

- 程序只读取用户主动选择的本地录屏。
- 程序不读取游戏进程，不注入游戏，也不进行网络上传。
- OCR 文本仅用于计算内存中的比较签名，不显示、保存或分析具体文字。
- 截图保留在程序当前运行的内存中；关闭程序后释放。

## 已知限制

- OCR 可能受录屏分辨率、画面缩放、背景动画和字体样式影响。
- 同一播报连续出现多次时，程序会尽量去重，但极端情况下仍可能漏截或重复。
- 不同录屏布局需要重新框选播报区域。
- 目前仅在 Windows 上测试。

## 许可证与声明

本项目原创代码采用 [MIT License](LICENSE)。

“和平精英”及相关商标、游戏素材的权利归其权利人所有。本项目不包含游戏本体、
游戏素材或腾讯官方资源。请在遵守游戏服务条款和当地法律的前提下，仅处理你拥有
合法使用权的录屏内容。
