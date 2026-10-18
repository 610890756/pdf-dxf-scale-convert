# PDF -> DXF 批量转换管线：PDFIMPORT(filter=12) -> SCALE(25.4*denom) -> DXFOUT -> 标注样式/文件头修复 -> 验证
# 用法: python pdf2dxf.py jobs.json
# jobs.json: {"src": "PDF文件夹", "acad": "accoreconsole路径(可选)",
#             "jobs": [{"pdf": "文件名", "page": 1, "denom": 16, "name": "输出文件名词干"}]}
import json
import os
import shutil
import subprocess
import sys
import tempfile

import ezdxf

DEFAULT_ACAD = r'D:\Autocad2022\AutoCAD 2022\accoreconsole.exe'


def make_empty(tmp):
    """空底稿。必须 setup=True——accoreconsole 加载无 setup 的最小 DXF 会触发内部错误崩溃。
    setup=True 注入的 EZ_ 样式与污染的文件头标注变量由 fix_dimstyles 统一清理。"""
    p = os.path.join(tmp, 'empty.dxf')
    ezdxf.new('R2018', setup=True).saveas(p)
    return p


def import_and_scale(acad, empty, pdf, page, factor, dxf, tmp, tag):
    if os.path.exists(dxf):
        os.remove(dxf)
    scr = os.path.join(tmp, tag + '.scr')
    # 不设 FILEDIA：accoreconsole 本身非交互；FILEDIA 受 SYSVARMONITOR 监控，
    # 在会话中修改可能触发内部错误导致引擎崩溃
    lines = ['PDFIMPORTFILTER', '12',
             '-PDFIMPORT', 'F', '"%s"' % pdf, str(page), '', '', '',
             'SCALE', 'ALL', '', '0,0', repr(factor),
             'DXFOUT', '"%s"' % dxf, '']
    # newline='' 禁用 Python 换行翻译：否则 '\r\n' 变成 '\r\r\n'，
    # scr 每行之间多出空行会打乱 AutoCAD 命令提示序列
    with open(scr, 'w', encoding='gbk', newline='') as fp:
        fp.write('\r\n'.join(lines) + '\r\n')
    out = os.path.join(tmp, tag + '_out.txt')
    with open(out, 'w') as fo:
        subprocess.run([acad, '/i', empty, '/s', scr, '/l', 'en-US'],
                       stdout=fo, stderr=subprocess.STDOUT, timeout=600)
    return os.path.exists(dxf)


def fix_dimstyles(dxf, denom):
    """样式表与文件头必须同时修改，否则 AutoCAD 显示 Standard<样式代替>。"""
    doc = ezdxf.readfile(dxf)
    for st in list(doc.dimstyles):
        if st.dxf.name.startswith('EZ'):
            doc.dimstyles.remove(st.dxf.name)
    if 'Standard' not in [s.dxf.name for s in doc.dimstyles]:
        doc.dimstyles.add('Standard')
    txt, asz = 3.5 * denom, 2.5 * denom
    st = doc.dimstyles.get('Standard')
    st.dxf.dimlfac = 1.0
    st.dxf.dimtxt = txt
    st.dxf.dimasz = asz
    st.dxf.dimtsz = 0.0
    st.dxf.dimblk = ''
    st.dxf.dimexe = 1.0 * denom
    st.dxf.dimexo = 2.0 * denom
    st.dxf.dimgap = 0.5 * denom
    st.dxf.dimscale = 1.0
    h = doc.header
    h['$DIMSTYLE'] = 'Standard'
    h['$DIMLFAC'] = 1.0
    h['$DIMTXT'] = txt
    h['$DIMASZ'] = asz
    h['$DIMTSZ'] = 0.0
    h['$DIMBLK'] = ''
    h['$DIMEXE'] = 1.0 * denom
    h['$DIMEXO'] = 2.0 * denom
    h['$DIMGAP'] = 0.5 * denom
    h['$DIMSCALE'] = 1.0
    h['$INSUNITS'] = 4
    h['$MEASUREMENT'] = 1
    doc.saveas(dxf)


def report(dxf):
    doc = ezdxf.readfile(dxf)
    msp = doc.modelspace()
    from collections import Counter
    c = Counter(e.dxftype() for e in msp)
    xs, ys = [], []
    for e in msp:
        t = e.dxftype()
        try:
            if t == 'LWPOLYLINE':
                for pt in e.get_points():
                    xs.append(pt[0]); ys.append(pt[1])
            elif t in ('CIRCLE', 'ARC', 'ELLIPSE'):
                xs.append(e.dxf.center.x); ys.append(e.dxf.center.y)
            elif t in ('MTEXT', 'TEXT', 'INSERT'):
                xs.append(e.dxf.insert.x); ys.append(e.dxf.insert.y)
        except Exception:
            pass
    ext = 'W=%.1f H=%.1f mm' % (max(xs) - min(xs), max(ys) - min(ys)) if xs else 'N/A'
    return sum(c.values()), dict(c), ext


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding='utf-8-sig') as fp:
        cfg = json.load(fp)
    src = cfg['src']
    acad = cfg.get('acad', DEFAULT_ACAD)
    # 工作目录放在源文件夹内（已验证可用；输出与底稿同目录也便于排查）
    tmp = tempfile.mkdtemp(prefix='_pdf2dxf_', dir=src)
    empty = make_empty(tmp)

    fails = []
    for j, job in enumerate(cfg['jobs']):
        pdf = os.path.join(src, job['pdf'])
        dxf = os.path.join(src, job['name'] + '.dxf')
        denom = job['denom']
        factor = 25.4 * denom
        tag = 'j%d' % j
        print('[%d/%d] %s p%s 1:%s -> %s' % (j + 1, len(cfg['jobs']), job['pdf'], job['page'], denom, job['name']))
        if not import_and_scale(acad, empty, pdf, job['page'], factor, dxf, tmp, tag):
            print('   FAIL: 导入失败，见 %s' % os.path.join(tmp, tag + '_out.txt'))
            fails.append(job['name'])
            continue
        try:
            fix_dimstyles(dxf, denom)
        except PermissionError:
            print('   WARN: 文件被占用，标注样式未修复（请在 AutoCAD 中关闭后重跑）')
            fails.append(job['name'])
            continue
        n, types, ext = report(dxf)
        size = os.path.getsize(dxf) / 1e6
        print('   OK: %d 实体 | %s | %.1f MB' % (n, ext, size))
        print('   类型: %s' % types)
    if fails:
        print('DONE. 失败=%s | 日志保留在 %s' % (fails, tmp))
    else:
        shutil.rmtree(tmp, ignore_errors=True)
        print('DONE. 全部成功，临时目录已清理')


if __name__ == '__main__':
    main()
