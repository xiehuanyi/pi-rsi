#!/usr/bin/env python3
"""Build same-origin, CSP-compatible PocketPlay pages from a sanitized experiment archive."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
PREFIX = '/rsi/interactive/airline-20261004'
HOST = 'https://blog.pocketplay.win'
EN = {
    'pi-rsi · 航空满意度实验':'pi-rsi · airline satisfaction',
    '验证 AUC 的变化':'Validation AUC progression', '搜索分支':'Search branches',
    '历史最佳':'Best so far', '各节点评测':'Node measurements', '实验运行中':'Running',
    '× 失败　◇ 评测后仍在分析':'× Failed　◇ Processing',
    '★ 最高分节点　× 失败节点　◇ 处理中　连线表示从哪个节点继续实验':'★ Highest score　× Failed　◇ Processing · Edges show code ancestry',
    '研究 Wiki · 知识与证据':'Research Wiki · knowledge and evidence', '知识条目':'Knowledge entry',
    '证据关系':'Evidence relationships', '支持证据':'Supporting evidence', '反对证据':'Opposing evidence',
    '当前条目':'Selected entry', '实线：支持　虚线：反对 · 证据条目数不代表独立重复次数':'Solid: support · Dashed: opposition · Record counts are not independent replications',
    '适用范围、其他解释与下一步验证':'Scope, alternatives and next test', '知识版本与结论变化':'Published revisions and belief changes',
    '发布版本':'Published revision', '研究议程与尚未解决的问题':'Research agenda and open questions',
    '图表暂未加载':'Chart unavailable', '暂无有效评测':'No valid measurement', ' · 已分配 ':' · Allocated ',
    ' 个节点 · ':' nodes · ', ' 完成 / ':' done / ', ' 失败 / ':' failed / ', ' 处理中 · Wiki 待处理 ':' pending completion · Wiki pending ',
    ' · 相对基线 ':' · versus baseline ', '基线':'Baseline', '本地验证 AUC':'Local validation AUC',
    '研究节点编号':'Research node number', '节点位置 ':'Node position ', '历史最佳 ':'Best so far ',
    '相邻有效评测插值 ':'Interpolation between valid scores ', '最近节点 ':'Nearest node ',
    '观察':'Observation', '假设':'Hypothesis', '经验':'Experience', '获证据支持':'Supported',
    '待验证':'Untested', '证据混合':'Mixed evidence', '被反驳':'Refuted', '已被替代':'Superseded',
    ' 条知识 · ':' entries · ', ' 条证据记录 · ':' evidence records · ', ' 个发布版本 · ':' published revisions · ',
    '（沙特时间）':' (Riyadh time)', '知识版本与结论变化（':'Published revisions and belief changes (',
    ' 个版本）':' revisions)', '无':'None', '实验记录':'Experiment record', '文档记录':'Documentation record',
    ' 条 · ':' entries · ', ' 项更新':' changes', '（当前）':' (current)',
    '无有效分数':'No valid score', ' · 测量状态 ':' · Measurement ', '有效':'valid', '不可用':'unavailable', '失效':'invalid',
    '未记录':'not recorded', '打开原文来源':'Open original source', '记录身份与哈希':'Record identity and hashes',
    '原始记录 SHA-256：':'Raw packet SHA-256: ', '代码提交：':'Code commit: ', '来源文本 SHA-256：':'Source text SHA-256: ',
    '无记录':'No records', '文档 ':'Document ', '证据：':' evidence: ', '支持':'Support', '反对':'Opposition',
    ' · 支持 ':' · Supports ', ' / 反对 ':' / Opposes ', '适用范围':'Scope', '其他解释':'Alternative explanations',
    '下一步区分性验证':'Next discriminating test', '查看被替代的条目':'View predecessor entry', '新增':'New',
    '本版本没有记录条目状态更新。':'No recorded entry-status changes in this revision.',
    '研究动机':'Motivation', '方法与判断依据':'Method and interpretation', '开放问题':'Open questions', '下一步实验':'Next experiments',
    '已完成':'Done', '失败':'Failed', '实验中':'Running', '结果分析中':'Analyzing', '评测中':'Evaluating',
    '待运行':'Planned', '待恢复':'Completion pending',
    '基线到第 ':'Baseline through node ', ' 个节点的搜索分支；带星号的是最高分节点':' search branches; the star marks the highest score',
    '验证 AUC 从 ':'Validation AUC from ', ' 提高到 ':' to ',
    '。失败节点不计入历史最佳，未完成节点只显示暂定评测。':'. Failed nodes do not improve the incumbent; incomplete nodes display provisional measurements only.',
}
CLASSES = {'btn':'pp-chip', 'btn-ghost':'', 'card':'pp-card pp-card--pad',
           'text-small':'pp-small', 'text-muted':'pp-muted', 'tabular-nums':'pp-num',
           'form-select':'pp-select-native', 'form-label':'pp-label'}


def js_data(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')


def css_scope(css):
    """Scope the legacy explorer without changing its component rules or global Kit tokens."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out, start = [], 0
    while start < len(css):
        opening = css.find('{', start)
        if opening < 0: break
        head = css[start:opening].strip()
        depth, quote, escaped, end = 1, None, False, opening + 1
        while end < len(css) and depth:
            ch = css[end]
            if quote:
                if escaped: escaped = False
                elif ch == '\\': escaped = True
                elif ch == quote: quote = None
            elif ch in ('"', "'"): quote = ch
            elif ch == '{': depth += 1
            elif ch == '}': depth -= 1
            end += 1
        body = css[opening + 1:end - 1]
        if head.startswith('@media') or head.startswith('@supports'):
            nested = css_scope(body)
            if nested: out.append(head + '{' + nested + '}')
        elif not head.startswith('@'):
            selectors = []
            selectors_raw, position, nesting = [], 0, 0
            for i, ch in enumerate(head):
                if ch in '([': nesting += 1
                elif ch in ')]': nesting -= 1
                elif ch == ',' and not nesting:
                    selectors_raw.append(head[position:i]); position = i + 1
            selectors_raw.append(head[position:])
            for selector in selectors_raw:
                selector = selector.strip()
                if ':root' in selector or selector.startswith('html'): continue
                selectors.append('.rsi-native' if selector == 'body' else '.rsi-native ' + selector)
            if selectors: out.append(','.join(selectors) + '{' + body + '}')
        start = end
    return '\n'.join(out)


def convert_classes(value):
    return ' '.join(CLASSES.get(token, token) for token in value.split()).strip()


def ui_script(script, name):
    script = script.replace("JSON.parse(document.getElementById('rsi-data').textContent)", 'window.__RSI_BLOG_DATA__')
    script = script.replace("JSON.parse(document.getElementById('wk-data').textContent)", 'window.__RSI_BLOG_DATA__')
    script = script.replace("new Intl.DateTimeFormat('zh-CN'", "new Intl.DateTimeFormat(rsiLang==='zh'?'zh-CN':'en-GB'")
    missing = set()
    def literal(match):
        try: value = ast.literal_eval(match[0])
        except (SyntaxError, ValueError): return match[0]
        if any(t in CLASSES for t in value.split()):
            return json.dumps(convert_classes(value))
        if re.search(r'[\u4e00-\u9fff]', value):
            if value not in EN: missing.add(value)
            return 'tr(' + json.dumps(value, ensure_ascii=False) + ')'
        return match[0]
    script = re.sub(r"'(?:\\.|[^'\\])*'", literal, script)
    prefix = 'const rsiLang=document.documentElement.lang.startsWith("zh")?"zh":"en";\n'
    prefix += 'const rsiText=' + js_data(EN) + ';\nfunction tr(s){return rsiLang==="zh"?s:(rsiText[s]||s);}\n'
    if name == 'overview':
        script = script.replace('const h=390;', 'const h=Math.max(430,nodes.length*23);')
        prefix += '''if(rsiLang==='en'){
window.__RSI_BLOG_DATA__.nodes.forEach(n=>{n.label=n.title_en||n.label;n.state=tr(n.state);n.note=n.note_en||n.note;});
window.__RSI_BLOG_DATA__.status='Archived snapshot';
window.__RSI_BLOG_DATA__.timestamp=window.__RSI_BLOG_DATA__.timestamp.replace('（沙特时间）',' (Riyadh time)').replace(' 月 ','/').replace(' 日 ',' ');
}\n'''
    if missing: print('Untranslated UI strings:', sorted(missing), file=sys.stderr)
    return prefix + script


def build_widget(archive, output, name):
    filename = 'dashboard.fragment.html' if name == 'overview' else 'wiki.fragment.html'
    source = (archive / 'assets' / filename).read_text()
    styles = re.findall(r'<style>(.*?)</style>', source, re.S)
    blocks = re.findall(r'<script\b([^>]*)>(.*?)</script>', source, re.S)
    scripts = [text for attrs, text in blocks if 'application/json' not in attrs]
    if name == 'overview':
        (output / 'assets/d3.min.js').write_text(scripts[0])
    script = scripts[-1]
    body = re.sub(r'<style>.*?</style>|<script\b.*?</script>', '', source, flags=re.S).strip()
    body = re.sub(r'class="([^"]*)"', lambda m: 'class="' + convert_classes(m[1]) + '"', body)
    extra_css = []
    def inline_style(match):
        ident = 'rsi-style-' + str(len(extra_css))
        extra_css.append('.' + ident + '{' + match[1] + '}')
        return ' class="' + ident + '"'
    # Only the two legend swatches carry static inline styles; preserve their existing class.
    def swatch(match):
        ident = 'rsi-series-' + str(len(extra_css))
        extra_css.append('.' + ident + '{' + match[2] + '}')
        return match[1][:-1] + ' ' + ident + '"'
    body = re.sub(r'(<span class="rsi-swatch")\s+style="([^"]+)"', swatch, body)
    body = re.sub(r'\sstyle="([^"]+)"', inline_style, body)
    body = re.sub(r'(<select\b[^>]*>.*?</select>)', r'<div class="pp-select">\1</div>', body, flags=re.S)
    (output / ('assets/' + name + '.css')).write_text('\n'.join(styles + extra_css))
    (output / ('assets/' + name + '.js')).write_text(ui_script(script, name))
    return body


def build(archive, output, kit):
    sys.path.insert(0, str(kit))
    import shell
    output.mkdir(parents=True, exist_ok=True)
    (output / 'assets').mkdir(exist_ok=True)
    snapshot = json.loads((archive / 'snapshot.json').read_text())
    overview = json.loads((archive / 'dashboard-data.json').read_text())
    wiki = json.loads((archive / 'wiki-data.json').read_text())
    node_map = {n['id']: n for n in snapshot['nodes']}
    for n in overview['nodes']:
        n['title_en'] = node_map[n['id']]['title']
        n['note_en'] = node_map[n['id']].get('summary') or 'Recorded search-validation evidence; stable improvement is not independently established.'
        if n['id'] == snapshot['best']:
            best = node_map[n['id']]
            parent = node_map.get(best['parent'])
            contrast = best['score'] - parent['score'] if parent and parent.get('score') is not None else None
            n['note_en'] = ('Highest valid completed score in this snapshot. '
                            + (f'The exact sequential contrast with {parent["id"]} is {contrast:+.10f} AUC. ' if contrast is not None else '')
                            + 'This is adaptive search-validation evidence, not independent confirmation or established repeatability.')
        elif n['status'] == 'failed':
            n['note_en'] = 'Invalid or failed measurement; excluded from the incumbent curve. ' + str(node_map[n['id']].get('failure', ''))
    bodies = {name: build_widget(archive, output, name) for name in ('overview', 'wiki')}
    for name, data in [('overview', overview), ('wiki', wiki)]:
        (output / ('assets/' + name + '-data.js')).write_text('window.__RSI_BLOG_DATA__=' + js_data(data) + ';\n')
    tree_html = (archive / 'tree.html').read_text()
    tree_css = re.search(r'<style>(.*?)</style>', tree_html, re.S)[1]
    tree_script = re.findall(r'<script\b[^>]*>(.*?)</script>', tree_html, re.S)[-1]
    tree_body = re.search(r'<body[^>]*>(.*?)</body>', tree_html, re.S)[1]
    tree_body = re.sub(r'<script\b.*?</script>', '', tree_body, flags=re.S)
    tree_body = tree_body.replace('Embedded logs may contain private information; review before sharing.', '')
    tree_body = tree_body.replace('<h1 id="title"', '<h2 id="title"').replace('</h1>', '</h2>')
    (output / 'assets/tree.css').write_text(css_scope(tree_css))
    tree_script += '''\n(() => {
if(!document.documentElement.lang.startsWith('zh'))return;
const words={'Snapshot':'快照','Search tree':'搜索树','Best score path':'最佳分数路径','Selected ancestry':'选中节点的祖先',
'Improved':'提升','No change':'未确认变化','Worse':'下降','Failed':'失败','Running':'运行中','Planned':'待运行','Abandoned':'已放弃',
'Fit':'适应屏幕','Best':'最佳节点','Node':'节点','Overview':'概览','Handoff':'交接','Progress':'过程','Raw metrics':'原始指标',
'Failure':'失败','Research knowledge':'研究知识','Wiki & revisions':'Wiki 与版本','Insights':'观察记录','Dead ends':'无效方向',
'Completed experiments':'已完成实验','Wall time':'运行时间','Show references':'显示参考线','Experiment ledger':'实验台账',
'Any status':'全部状态','Parent':'父节点','Depth':'深度','Status':'状态','Score':'分数','Hypothesis':'假设'};
const root=document.querySelector('.rsi-native');
const translate=()=>{const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while((n=walk.nextNode())){
if(n.parentElement?.closest('pre,code,script'))continue;const k=n.nodeValue.trim();if(words[k])n.nodeValue=n.nodeValue.replace(k,words[k]);}};
new MutationObserver(translate).observe(root,{childList:true,subtree:true,characterData:true});translate();
})();\n'''
    (output / 'assets/tree.js').write_text(tree_script)
    (output / 'assets/tree-data.js').write_text('window.__RSI_DATA__=' + js_data(snapshot) + ';\n')
    bodies['tree'] = '<div class="rsi-native">' + tree_body + '</div>'
    css = (REPO / 'scripts/blog-visualizations.css').read_text()
    (output / 'assets/viz.css').write_text(css)
    shutil.copyfile(REPO / 'scripts/blog-visualizations.js', output / 'assets/state.js')
    shutil.copyfile(archive / 'assets/D3-LICENSE.txt', output / 'assets/D3-LICENSE.txt')
    for src, dest in [('SUMMARY.json','summary.json'),('results.json','results.json'),('wiki-data.json','wiki-data.json')]:
        shutil.copyfile(archive / src, output / dest)
    shutil.copyfile(REPO / 'pi_rsi/tasks/airline-s6e10-2080ti/docs/PROTOCOL.md', output / 'protocol.md')
    names = {'overview': ('Experiment overview','实验概览'), 'tree': ('Full search tree','完整搜索树'), 'wiki': ('Research Wiki','研究 Wiki')}
    urls = []
    for lang in ('en', 'zh'):
        for name in ('overview', 'tree', 'wiki'):
            path = PREFIX + '/' + lang + '/' + (name + '/' if name != 'overview' else '')
            alt = PREFIX + '/' + ('en' if lang == 'zh' else 'zh') + '/' + (name + '/' if name != 'overview' else '')
            title = names[name][lang == 'zh']
            labels = lambda en, zh: zh if lang == 'zh' else en
            nav = ''.join(f'<a class="pp-chip" href="{PREFIX}/{lang}/{n+"/" if n!="overview" else ""}"' + (' aria-current="page"' if n == name else '') + f'>{names[n][lang=="zh"]}</a>' for n in names)
            article = HOST + f'/{lang}/blog/pi-rsi-airline-20261004/'
            head = f'<header class="pp-container pp-pagehead"><nav class="pp-crumbs"><a href="{article}">{labels("Experiment notes","实验说明")}</a></nav><h1 class="pp-title">pi-rsi · {title}</h1><p class="pp-lede">{labels("Inspect recorded scores, code ancestry and the evidence behind research knowledge.","查看分数、代码分支，以及研究知识背后的证据。")}</p></header>'
            inner = f'<section class="pp-container pp-section--tight"><nav class="pp-chips rsi-tabs">{nav}</nav><div class="rsi-viz">{bodies[name]}</div><details class="rsi-method"><summary>{labels("Snapshot and interpretation","快照与解释边界")}</summary><p>{labels("Archived data; the page does not poll the running experiment. Search-validation scores and Wiki statuses are not independent confirmation. Original experimental records remain in their source language.","这是保存时的快照，不会自动读取正在运行的实验。搜索验证分数和 Wiki 状态不等于独立确认；原始实验记录保留原文。")}</p><a href="{PREFIX}/summary.json">{labels("Experiment metadata","实验元数据")}</a> · <a href="{PREFIX}/wiki-data.json">{labels("Wiki metadata","Wiki 元数据")}</a> · <a href="{PREFIX}/protocol.md">{labels("Frozen protocol","冻结协议")}</a></details></section>'
            assets = PREFIX + '/assets/'
            extra = f'<link rel="stylesheet" href="{assets}viz.css"><link rel="stylesheet" href="{assets}{name}.css">'
            if name == 'overview': extra += f'<script src="{assets}d3.min.js" defer></script>'
            extra += f'<script src="{assets}{name}-data.js" defer></script><script src="{assets}state.js" defer></script><script src="{assets}{name}.js" defer></script>'
            page = shell.document('blog', lang, 'pi-rsi · ' + title, head + inner,
                                  labels('Interactive airline experiment and research knowledge snapshots.','航空满意度实验与研究知识的交互快照。'),
                                  HOST + path, [('en', HOST + path.replace('/zh/', '/en/')), ('zh-CN', HOST + path.replace('/en/', '/zh/'))],
                                  'blog', HOST + alt, extra_head=extra, body_class='rsi-site')
            # Populate widget selectors before Kit enhancement runs.
            pp_script = re.search(r'<script src="/_kit/v2/pp.js[^>]+></script>', page)[0]
            page = page.replace(pp_script, '').replace('</head>', pp_script + '</head>')
            if lang == 'en':
                page = re.sub(r'>([^<>]+)<', lambda m: '>' + EN.get(html.unescape(m[1]), m[1]) + '<', page)
            dest = output / lang / (name if name != 'overview' else '') / 'index.html'
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(page)
            urls.append(HOST + path)
    # Stable default entrance; language-specific pages have their own canonicals.
    (output / 'index.html').write_text('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=zh/"><title>pi-rsi</title></head><body><a href="zh/">中文</a> · <a href="en/">English</a></body></html>')
    ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', ns)
    site_map = ET.Element('{'+ns+'}urlset')
    for url in urls:
        item = ET.SubElement(site_map, '{'+ns+'}url')
        ET.SubElement(item, '{'+ns+'}loc').text = url
        ET.SubElement(item, '{'+ns+'}lastmod').text = datetime.now(timezone.utc).isoformat(timespec='seconds')
    (output / 'sitemap.xml').write_bytes(ET.tostring(site_map, encoding='utf-8', xml_declaration=True))
    print(json.dumps({'output':str(output), 'pages':urls, 'wiki_entries':len(wiki['claims'])}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, default=REPO/'examples/airline-s6e10-2080ti-20261004')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--kit', type=Path, required=True, help='PocketPlay platform kit/v2 directory')
    args = p.parse_args()
    build(args.archive.resolve(), args.output.resolve(), args.kit.resolve())


if __name__ == '__main__':
    main()
