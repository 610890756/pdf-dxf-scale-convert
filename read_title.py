# 渲染 PDF 每页标题栏区域为 PNG + 提取文本，供视觉读取图号/名称/比例/纸张
# 用法: python read_title.py <PDF文件夹> <输出目录>
import os
import sys


def render_page(page, out_png, dpi=200):
    """优先 PyMuPDF，回退 pdfplumber。渲染整页（标题栏通常在右下角）。"""
    try:
        import fitz  # PyMuPDF
        pix = page.get_pixmap(dpi=dpi)
        pix.save(out_png)
        return True
    except ImportError:
        return False


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)

    try:
        import fitz
        backend = 'fitz'
    except ImportError:
        import pdfplumber
        backend = 'pdfplumber'

    for f in sorted(os.listdir(src)):
        if not f.lower().endswith('.pdf'):
            continue
        p = os.path.join(src, f)
        stem = os.path.splitext(f)[0]
        if backend == 'fitz':
            doc = fitz.open(p)
            print('== %s | 页数=%d' % (f, doc.page_count))
            for i, page in enumerate(doc):
                png = os.path.join(out, '%s_p%d.png' % (stem, i + 1))
                render_page(page, png)
                text = page.get_text()
                # 打印含关键字的行，辅助定位比例/名称
                for line in text.splitlines():
                    if any(k in line for k in ['比例', '名称', '图号', '共', '张', 'A1', 'A2', 'A3', 'A4']):
                        print('  p%d: %s' % (i + 1, line.strip()))
            doc.close()
        else:
            with pdfplumber.open(p) as pdf:
                print('== %s | 页数=%d' % (f, len(pdf.pages)))
                for i, page in enumerate(pdf.pages):
                    png = os.path.join(out, '%s_p%d.png' % (stem, i + 1))
                    try:
                        page.to_image(resolution=200).save(png)
                    except Exception as e:
                        print('  渲染失败 p%d: %s' % (i + 1, e))
                    text = page.extract_text() or ''
                    for line in text.splitlines():
                        if any(k in line for k in ['比例', '名称', '图号', '共', '张', 'A1', 'A2', 'A3', 'A4']):
                            print('  p%d: %s' % (i + 1, line.strip()))
    print('RENDER DONE ->', out)


if __name__ == '__main__':
    main()
