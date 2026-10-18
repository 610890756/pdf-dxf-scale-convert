---
name: pdf-dxf-scale-convert
description: 批量将工程PDF图纸经AutoCAD accoreconsole的PDFIMPORT转为DXF，并按图纸比例缩放到1:1毫米真实尺寸，同时修复标注样式。用于用户请求 PDF转CAD、PDF转DXF、图纸按比例缩放 时；不适用于 DWG 编辑或纯扫描件OCR矢量化。
---

# PDF 图纸批量转 DXF（比例还原）

将机械图纸 PDF 批量转换为可编辑 DXF：矢量导入、无填充、按各页图纸比例还原为真实毫米尺寸、标注样式对齐。全程后台执行，不占用屏幕。

## 前置条件

- AutoCAD 2022（accoreconsole 路径默认 `D:\Autocad2022\AutoCAD 2022\accoreconsole.exe`，可在 manifest 中覆盖）
- Python 3 + ezdxf + pdfplumber（或 PyMuPDF/fitz 用于渲染标题栏）
- 目标文件夹中的 DXF 必须**未在 AutoCAD 中打开**，否则保存会报 PermissionError

## 流程

1. 列出文件夹中的 PDF。若与历史批次文件名/大小相同，可用 MD5 哈希判断是否同一套图纸，直接沿用已读取的比例信息。

2. 读取每页标题栏的名称与比例：

   ```
   python scripts/read_title.py <PDF文件夹> <输出图片目录>
   ```

   生成每页 PNG（标题栏区域）与文本提取结果。用视觉读取 PNG 中的 图号、名称、比例（如 1:16）、纸张（A4/A3/A2）、共几张。多页 PDF 每页比例可能不同（总装图常为 1:1），必须逐页记录。

3. 生成任务清单 `jobs.json`：

   ```json
   {
     "src": "C:\\path\\to\\pdf文件夹",
     "acad": "D:\\Autocad2022\\AutoCAD 2022\\accoreconsole.exe",
     "jobs": [
       {"pdf": "xxx_A.pdf", "page": 1, "denom": 16, "name": "xxx_A_箱沿_1-16"},
       {"pdf": "yyy_A.pdf", "page": 2, "denom": 1,  "name": "yyy_A_装配_1-1"}
     ]
   }
   ```

   `denom` 为比例分母（1:16 填 16；1:1 填 1）。多页 PDF 每页一条任务、独立输出文件。

4. 执行转换（导入 + 缩放 + 标注样式修复 + 尺寸验证）：

   ```
   python scripts/pdf2dxf.py jobs.json
   ```

5. 核对输出的图框范围 = 纸张尺寸 × 比例分母（如 A4×16 → 3360×4752mm），实体类型应只有 LWPOLYLINE/CIRCLE/ARC/ELLIPSE/MTEXT（无 HATCH）。向用户汇报每个文件的比例、范围、实体数、大小。

## 关键参数与已验证事实

- `PDFIMPORTFILTER=12`：矢量几何 + TrueType 文字，**排除实体填充与光栅图像**。填充（HATCH）是文件体积膨胀的主因（本管线实测 279MB→23MB，缩小 92%）。filter=8 会带填充；该变量无法只导线条不导填充，必须用 12。
- 缩放因子 = **25.4 × 比例分母**。accoreconsole 的 PDFIMPORT 按英寸导入（A3 图框 ≈ 16.54×11.69），乘 25.4 转毫米，再乘分母还原实物 1:1 尺寸，结果 CAD 中 1 单位 = 1mm。
- 标注样式必须**同时**改样式表条目和**文件头变量**（$DIMLFAC/$DIMTXT/$DIMASZ/$DIMBLK/$DIMTSZ/$DIMSTYLE）。只改其一，AutoCAD 会显示"Standard\<样式代替\>"，新建标注仍用旧值（如线性比例 100、建筑标记箭头）。pdf2dxf.py 已内置对齐。
- 空底稿用 `ezdxf.new('R2018', setup=True)`（已验证可用）。setup=True 会注入 11 个 EZ_ 内部样式和污染的文件头标注变量（DIMLFAC=100、DIMBLK=ARCHTICK），由 pdf2dxf.py 的 fix_dimstyles 步骤统一清理与对齐，不可省略该修复。
- PDF 中的尺寸文字是填充路径，filter=12 下不会导入（只保留线条几何与 TrueType 签名文字）；这是预期行为，图纸尺寸以实物几何为准。
- `DIMLINEAR` 等标注命令无法在 accoreconsole 脚本中执行（会崩溃），不要在管线里尝试创建标注。
- .scr 脚本文件用 GBK（Default）编码以支持中文路径；PowerShell 脚本含中文时需 UTF-8 BOM。
- **.scr 行分隔必须是单个 `\r\n`**：Python 文本模式写 `'\r\n'` 会翻译成 `\r\r\n`，行间距多出空行会打乱 AutoCAD 命令提示序列（症状：`*错误* 命令 "12"`、SYSVARMONITOR 内部错误、无输出）。用 `open(scr, 'w', encoding='gbk', newline='')` 禁用翻译。
- 不要在 .scr 中设置 `FILEDIA`：accoreconsole 非交互无需该变量；异常退出的会话可能把 FILEDIA=0 持久化进配置文件（修复：注册表 `HKCU\Software\Autodesk\AutoCAD\R24.1\ACAD-xxxx\FixedProfile\General Configuration\FileDialog` 改回 1）。
- 工作目录（底稿/scr/日志）放源文件夹内的 `_pdf2dxf_*` 临时子目录，成功后自动清理，失败时保留日志供排查。
- accoreconsole 会话中修改的系统变量（如 PDFIMPORTFILTER）会写回用户 AutoCAD 配置文件；filter=12 即无填充导入，与手动对话框取消"实体填充"等效，无需还原。

## 脚本

- `scripts/read_title.py`：渲染每页标题栏区域为 PNG + 提取文本，供视觉读取比例信息
- `scripts/pdf2dxf.py`：按 jobs.json 批量执行 PDFIMPORT → SCALE → DXFOUT → 标注样式/文件头修复 → 范围验证
