#!/usr/bin/env python3
"""Original pi-rsi architecture artwork; stage/feedback/inset presentation inspired by Dream-RSI."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets'
LABELS = {
    'en': {
        'title': 'pi-rsi', 'subtitle': 'A research loop grounded in code, measurements and evidence',
        'task': 'Frozen task pack', 'task_sub': 'Task · data · starter · evaluator',
        'baseline': 'Root baseline', 'baseline_sub': 'Record score + provenance',
        'tree': 'Persistent search tree', 'tree_sub': 'Code ancestry · valid scores · branch history',
        'control': 'Controller', 'control_sub': 'Budgets · protocol · stop / resume',
        'plan': 'Choose', 'plan_sub': 'Select a parent and hypothesis',
        'build': 'Experiment', 'build_sub': 'Build one bounded hypothesis',
        'learn': 'Review', 'learn_sub': 'Analyze results and keep evidence',
        'proposal': 'Parent · hypothesis · budget', 'p1': 'Question', 'p2': 'Controls', 'p3': 'Budget',
        'code': 'Worktree', 'eval': 'Frozen eval', 'measure': 'Verified measurement',
        'monitor': 'Monitor', 'monitor_sub': 'wait / timeout / resume',
        'raw': 'Evidence', 'wiki': 'Wiki', 'index': 'Index',
        'learn_footer': 'Audit · handoff · scoped knowledge', 'wiki_note': 'Wiki: development research mode',
        'feedback': 'Results, handoffs and updated context guide the next decision',
        'detail': 'Inside one research node', 'agent': 'Coding agent', 'work': 'Worktree + trials',
        'quick': 'Quick trials', 'job': 'Official evaluation', 'analysis': 'Result analysis', 'handoff': 'Audit + handoff',
        'agent_sub': 'Selected implementation plan', 'work_sub': 'Bounded quick development',
        'quick_sub': 'Bounded development budget', 'job_sub': 'Frozen protocol + monitor',
        'analysis_sub': 'Interpret the verified result', 'handoff_sub': 'Audit + evidence + proposals',
        'finish': 'Analysis + handoff',
        'foot': 'The controller enforces limits and recovery. Model interpretation stays separate from official measurement.',
    },
    'zh': {
        'title': 'pi-rsi', 'subtitle': '围绕代码、正式测量与证据展开的研究循环',
        'task': '冻结的任务包', 'task_sub': '任务 · 数据 · 基线代码 · 评测器',
        'baseline': '根节点基线', 'baseline_sub': '正式测量与来源记录',
        'tree': '持久化搜索树', 'tree_sub': '代码继承 · 有效分数 · 分支历史',
        'control': '控制器', 'control_sub': '预算 · 协议 · 停止／恢复',
        'plan': '选择', 'plan_sub': '比较假设，选定父节点与方案',
        'build': '实验', 'build_sub': '围绕一个假设进行有预算的实现',
        'learn': '复盘', 'learn_sub': '分析结果，保留支持与反对证据',
        'proposal': '父节点 · 假设 · 预算', 'p1': '研究问题', 'p2': '对照方案', 'p3': '预算约束',
        'code': '工作树', 'eval': '冻结评测器', 'measure': '已校验的测量',
        'monitor': '任务监控', 'monitor_sub': '等待 · 超时 · 恢复',
        'raw': '原始证据', 'wiki': '知识页', 'index': '索引',
        'learn_footer': '审计 · 交接 · 有范围的知识', 'wiki_note': 'Wiki：开发版研究模式',
        'feedback': '正式结果、交接记录与更新后的知识，反馈到下一次研究决策',
        'detail': '展开一个研究节点', 'agent': '编码 Agent', 'work': '工作树与试验',
        'quick': '开发集试验', 'job': '正式评测', 'analysis': '结果分析', 'handoff': '审计与交接',
        'agent_sub': '实现选定方案', 'work_sub': '隔离代码与有限次开发试验',
        'quick_sub': '限制尝试与用时', 'job_sub': '冻结协议 + 任务监控',
        'analysis_sub': '解释已校验结果', 'handoff_sub': '记录证据与后续提案',
        'finish': '分析与交接',
        'foot': '控制器执行资源约束与恢复；模型给出的解释，不替代评测器产生的正式测量。',
    },
}


def render(lang, dark):
    label = LABELS[lang]
    p = ({'bg':'#101820','ink':'#e6eef6','muted':'#a6b5c4','line':'#415260','paper':'#17232e',
          'blue':'#91b7ea','blue_soft':'#172b43','teal':'#75c6bd','teal_soft':'#133132',
          'violet':'#c1a6e8','violet_soft':'#2b223c','panel':'#14212c'} if dark else
         {'bg':'#ffffff','ink':'#223246','muted':'#63758a','line':'#cfdae5','paper':'#ffffff',
          'blue':'#4776b8','blue_soft':'#eef5fd','teal':'#2e857c','teal_soft':'#eef8f5',
          'violet':'#8661ad','violet_soft':'#f5f0fb','panel':'#f7f9fc'})
    svg = []
    def rect(x,y,w,h,fill,stroke=None,r=14,dash=None):
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"'+
                   (f' stroke="{stroke}" stroke-width="1.6"' if stroke else '')+
                   (f' stroke-dasharray="{dash}"' if dash else '')+'/>' )
    def text(x,y,value,size=22,color=None,weight=400,anchor='start'):
        svg.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color or p["ink"]}" text-anchor="{anchor}">{escape(value)}</text>')
    def line(d,color=None,width=2,arrow=False,dash=None):
        svg.append(f'<path d="{d}" fill="none" stroke="{color or p["ink"]}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"'+
                   (' marker-end="url(#arrow)"' if arrow else '')+(f' stroke-dasharray="{dash}"' if dash else '')+'/>' )
    def circle(x,y,r,fill,stroke=None):
        svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"'+(f' stroke="{stroke}" stroke-width="1.7"' if stroke else '')+'/>' )
    def sheet(x,y,w,h,color,fill,rows=3):
        rect(x,y,w,h,fill,color,8)
        for i in range(rows):
            line(f'M{x+14} {y+34+i*13} H{x+w-18-(i%2)*11}',p['line'],2)
    def robot(x,y,color):
        line(f'M{x+30} {y-6} V{y}',color)
        circle(x+30,y-9,3.5,color)
        rect(x,y,60,46,p['paper'],color,13)
        circle(x+20,y+20,4,color);circle(x+40,y+20,4,color)
        line(f'M{x+20} {y+33} H{x+40}',color,2)
        rect(x+8,y+53,44,23,p['paper'],color,8)
        line(f'M{x-7} {y+11} V{y+32} M{x+67} {y+11} V{y+32}',color)
    # Header and immutable setup.
    text(40,52,label['title'],37,weight=700)
    text(183,51,label['subtitle'],23,p['muted'])
    for x,w,title,sub in [(40,360,'task','task_sub'),(442,294,'baseline','baseline_sub'),(778,462,'tree','tree_sub')]:
        rect(x,87,w,91,p['panel'],p['line'],14)
        text(x+22,120,label[title],24,weight=600)
        text(x+22,153,label[sub],20,p['muted'])
    line('M409 132 H432',arrow=True);line('M744 132 H768',arrow=True)
    # Setup enters the first experiment; the controller owns the loop limits.
    line('M589 180 V202 H209 V232',p['muted'],1.8,True)
    text(1240,211,label['control']+'  /  '+label['control_sub'],20,p['muted'],anchor='end')
    starts=[40,450,860]
    for i,(x,color,fill,title,sub) in enumerate(zip(starts,['blue','teal','violet'],['blue_soft','teal_soft','violet_soft'],['plan','build','learn'],['plan_sub','build_sub','learn_sub']),1):
        rect(x,238,380,245,p[fill],p[color],18)
        circle(x+31,270,17,p[color])
        text(x+31,277,str(i),20,p['bg'],700,'middle')
        text(x+62,279,label[title],29,weight=650)
        text(x+23,311,label[sub],20,p['muted'])
    line('M426 366 H440',arrow=True);line('M836 366 H850',arrow=True)
    # Step 1: a researcher chooses a branch and a bounded question.
    robot(66,338,p['blue'])
    line('M138 359 H169',p['blue'],1.8,True)
    circle(208,348,12,p['paper'],p['blue'])
    line('M208 360 V374 M208 374 H184 V390 M208 374 H261 V390',p['blue'],1.8)
    circle(184,401,11,p['paper'],p['blue']);circle(261,401,11,p['blue_soft'],p['blue'])
    line('M261 412 V422 H293 V425',p['blue'],1.8)
    circle(293,433,8,p['blue'])
    sheet(308,336,88,86,p['blue'],p['paper'],3)
    text(352,362,'?',25,p['blue'],500,'middle')
    text(230,464,label['proposal'],20,p['blue'],500,'middle')
    # Step 2: code changes and real evaluation, not LLM-authored scores.
    sheet(479,339,113,82,p['teal'],p['paper'],0)
    text(535,373,'{ code }',22,p['teal'],500,'middle')
    text(535,401,label['code'],18,p['muted'],anchor='middle')
    line('M603 374 H646',p['teal'],1.8,True)
    sheet(657,339,137,82,p['teal'],p['paper'],0)
    text(725,373,label['eval'],20,p['teal'],500,'middle')
    line('M698 394 L706 402 L718 386',p['teal'],2.4)
    text(744,401,'score',17,p['muted'],anchor='middle')
    text(640,461,label['monitor']+' · '+label['monitor_sub'],19,p['teal'],500,'middle')
    # Step 3: evidence → scoped knowledge → navigation.
    for x,w,title in [(885,94,'raw'),(1016,89,'wiki'),(1132,83,'index')]:
        sheet(x,346,w,74,p['violet'],p['paper'],2)
        text(x+w/2,443,label[title],19,p['violet'],500,'middle')
    line('M985 383 H1006',p['violet'],1.7,True)
    line('M1110 383 H1122',p['violet'],1.7,True)
    text(1050,464,label['learn_footer'],19,p['muted'],anchor='middle')
    # Feedback is explicit and visually separate from the execution inset.
    line('M1050 488 V522 H230 V488',p['blue'],2.2,True)
    rect(320,500,640,40,p['bg'],None,0)
    text(640,527,label['feedback'],20,p['blue'],500,'middle')
    text(1240,551,label['wiki_note'],19,p['muted'],anchor='end')
    # A dashed close-up expands what actually happens within each selected node.
    rect(40,565,1200,158,p['panel'],p['line'],18,'6 5')
    rect(64,550,320,31,p['bg'],None,0)
    text(78,575,label['detail'],23,weight=600)
    line('M640 485 V543',p['muted'],1.4,False,'4 5')
    detail=[('agent','agent_sub'),('work','work_sub'),('job','job_sub'),('finish','handoff_sub')]
    for i,(title,sub) in enumerate(detail):
        x=63+i*294
        rect(x,605,250,57,p['paper'],p['line'],10)
        text(x+125,640,label[title],22,weight=550,anchor='middle')
        text(x+125,690,label[sub],19,p['muted'],anchor='middle')
        if i<3:line(f'M{x+260} 635 H{x+284}',p['muted'],1.6,True)
    text(640,759,label['foot'],19,p['muted'],anchor='middle')
    title=label['subtitle']
    desc='Frozen task and root baseline feed an iterative research loop: choose a hypothesis, implement and officially evaluate it, analyze the result and retain evidence. Search tree, handoffs and the development research Wiki inform the next decision. A node inset shows coding, quick trials, official evaluation and audit. Budgets and recovery are controller responsibilities.'
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="784" viewBox="0 0 1280 784" role="img" aria-labelledby="title desc">'
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc>'
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M1 1 L9 5 L1 9" fill="none" stroke="'+p['ink']+'" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>'
            f'<rect width="1280" height="784" rx="20" fill="{p["bg"]}"/>'
            '<g font-family="Inter, Noto Sans CJK SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif">'
            + ''.join(svg) + '</g></svg>\n')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for lang in ('en','zh'):
        for dark in (False,True):
            path=OUT/f'pi-rsi-overview-{lang}-{"dark" if dark else "light"}.svg'
            path.write_text(render(lang,dark),encoding='utf-8')
            print(path)


if __name__=='__main__':
    main()
