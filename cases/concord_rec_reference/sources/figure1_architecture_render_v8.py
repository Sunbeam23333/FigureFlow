"""Editable SVG figures: native text, exact math paths, source-bound geometry."""
from pathlib import Path
import base64, copy, hashlib, io, json, math, re, shutil
import xml.etree.ElementTree as ET
import cairosvg
import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from matplotlib import mathtext, rcParams
from matplotlib.font_manager import FontProperties

HERE=Path(__file__).resolve().parent
PAPER=HERE.parent
PROJECT=PAPER.parent
OUT=HERE/'rendered'
OUT.mkdir(exist_ok=True)
NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
rcParams['svg.fonttype']='path'
rcParams['mathtext.fontset']='dejavusans'
INK='#17334D'; NAVY='#2D5578'; TEAL='#07877F'; VIOLET='#7B5AA6'
AMBER='#B87819'; CORAL='#BA5B53'; GRAY='#647586'; LINE='#D5DFE4'
PALE='#EAF7F4'; LAV='#F4F0FA'; WARM='#FFF7E7'

def prepare_display_photo():
    """Derive print-appropriate display media without changing source evidence."""
    source=HERE/'assets/originals/tent.jpg'
    dest=HERE/'assets/tent.jpg'
    with Image.open(source) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((640,640),Image.Resampling.LANCZOS)
        im.save(dest,format='JPEG',quality=90,optimize=True)
        dimensions=list(im.size)
    manifest=HERE/'assets/photo_manifest.json'
    data=json.loads(manifest.read_text())
    photo=next(x for x in data if x['id']=='tent')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==photo['original_sha256']
    photo['operations']=['EXIF orientation normalization if present','proportional downsample <=640 px','JPEG quality 90, optimized']
    photo['prepared_dimensions']=dimensions
    photo['prepared_sha256']=hashlib.sha256(dest.read_bytes()).hexdigest()
    photo['display_resolution_note']='640-pixel long edge; smallest effective print resolution exceeds 450 dpi in current panels.'
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def tag(parent,name,**a):
    return ET.SubElement(parent,'{'+NS+'}'+name,{k.replace('_','-'):str(v) for k,v in a.items()})

class Canvas:
    def __init__(self,name,height,claim,status):
        self.name=name;self.h=height;self.formulas=[];self.text_sizes=[]
        self.meta={'revision':'v8','claim':claim,'canonical_status':status,'target_width_cm':17.2,
                   'native_text':True,'formula_source':self.formulas,'editable_source':'redesign_v8/render.py'}
        self.root=ET.Element('{'+NS+'}svg',{'width':'17.2cm','height':f'{17.2*height/960}cm',
                            'viewBox':f'0 0 960 {height}','version':'1.1'})
        desc=tag(self.root,'desc');desc.text=claim
        self.rect(0,0,960,height,'white')
    def rect(self,x,y,w,h,fill='white',stroke='none',sw=1,rx=0):
        return tag(self.root,'rect',x=x,y=y,width=w,height=h,fill=fill,stroke=stroke,stroke_width=sw,rx=rx)
    def text(self,x,y,s,size=16,fill=INK,weight='normal',anchor='start'):
        self.text_sizes.append(size)
        t=tag(self.root,'text',x=x,y=y,font_family='DejaVu Sans',font_size=size,fill=fill,
              font_weight=weight,text_anchor=anchor);t.text=s;return t
    def lines(self,x,y,lines,size=16,step=22,**kw):
        for k,s in enumerate(lines):self.text(x,y+k*step,s,size=size,**kw)
    def line(self,x1,y1,x2,y2,color=LINE,sw=1.2,dash=None):
        a=dict(x1=x1,y1=y1,x2=x2,y2=y2,stroke=color,stroke_width=sw)
        if dash:a['stroke_dasharray']=dash
        return tag(self.root,'line',**a)
    def arrow(self,points,color=NAVY,sw=2,dash=None):
        a=dict(points=' '.join(f'{x},{y}' for x,y in points),fill='none',stroke=color,
               stroke_width=sw,stroke_linejoin='round')
        if dash:a['stroke_dasharray']=dash
        tag(self.root,'polyline',**a)
        x,y=points[-1];x0,y0=points[-2];ang=math.atan2(y-y0,x-x0);r=7
        ps=[(x,y),(x-r*math.cos(ang)+3.8*math.sin(ang),y-r*math.sin(ang)-3.8*math.cos(ang)),
             (x-r*math.cos(ang)-3.8*math.sin(ang),y-r*math.sin(ang)+3.8*math.cos(ang))]
        tag(self.root,'polygon',points=' '.join(f'{a},{b}' for a,b in ps),fill=color)
    def math(self,x,y,source,size=20,color=INK,maxwidth=None):
        b=io.BytesIO();mathtext.math_to_image('$'+source+'$',b,prop=FontProperties(size=size),format='svg',color=color)
        node=ET.fromstring(b.getvalue());v=[float(n) for n in node.attrib['viewBox'].split()];w,h=v[2:]
        for parent in node.iter():
            for child in list(parent):
                if child.attrib.get('id')=='patch_1':parent.remove(child)
        scale=min(1,maxwidth/w) if maxwidth else 1
        self.formulas.append({'latex':source,'x':x,'y':y,'font_size_source':size,'scale':scale})
        g=tag(self.root,'g',transform=f'translate({x},{y}) scale({scale})')
        d=tag(g,'desc');d.text='LaTeX: '+source
        prefix=f'{self.name}_m{len(self.formulas)}_'
        raw=''.join(ET.tostring(c,encoding='unicode') for c in node if c.tag.rsplit('}',1)[-1]!='metadata')
        ids=re.findall(r'id="([^"]+)"',raw)
        for identifier in sorted(ids,key=len,reverse=True):
            raw=raw.replace('id="'+identifier+'"','id="'+prefix+identifier+'"').replace('#'+identifier+'"','#'+prefix+identifier+'"').replace('#'+identifier+')','#'+prefix+identifier+')')
        wrapper=ET.fromstring('<g xmlns="'+NS+'">'+raw+'</g>')
        for child in wrapper:g.append(child)
        return w*scale,h*scale
    def photo(self,x,y,w,h,name='tent'):
        data=base64.b64encode((HERE/'assets'/f'{name}.jpg').read_bytes()).decode()
        tag(self.root,'image',x=x,y=y,width=w,height=h,preserveAspectRatio='xMidYMid slice',
            href='data:image/jpeg;base64,'+data)
    def icon(self,x,y,kind,color=VIOLET):
        if kind=='text':
            tag(self.root,'path',d=f'M{x+6},{y+2} H{x+23} L{x+30},{y+9} V{y+31} H{x+6} Z',fill='white',stroke=color,stroke_width=1.6)
            for yy in [13,19,25]:self.line(x+11,y+yy,x+25,y+yy,color,1.5)
        elif kind=='image':
            self.rect(x+2,y+5,31,25,'white',color,1.6,2)
            tag(self.root,'circle',cx=x+24,cy=y+12,r=3,fill=color)
            tag(self.root,'polyline',points=f'{x+5},{y+26} {x+13},{y+16} {x+21},{y+25} {x+28},{y+19}',fill='none',stroke=color,stroke_width=1.8)
        elif kind=='audio':
            for k,h in enumerate([9,19,28,16,8]):self.line(x+5+k*6,y+17-h/2,x+5+k*6,y+17+h/2,color,2.5)
        elif kind=='video':
            self.rect(x+2,y+5,31,25,'white',color,1.6,2)
            tag(self.root,'polygon',points=f'{x+14},{y+11} {x+14},{y+25} {x+25},{y+18}',fill=color)
    def tokens(self,x,y,values,width=35,height=30,gap=5,visible=None,color=NAVY):
        for j,value in enumerate(values):
            known=value not in ('?','M','MASK') if visible is None else visible[j]
            self.rect(x+j*(width+gap),y,width,height,color if known else '#F4F6F8',color if known else LINE,1.1,3)
            self.text(x+j*(width+gap)+width/2,y+height*.7,str(value),size=16,fill='white' if known else GRAY,anchor='middle')
    def title(self,title,status):
        self.text(20,29,title,22,weight='bold');self.text(940,28,status,15.5,fill=GRAY,anchor='end')
        self.line(20,43,940,43)
    def save(self,extra=None):
        if extra:self.meta.update(extra)
        self.meta['minimum_native_text_points']=min(self.text_sizes)*487.56/960
        self.meta['minimum_formula_points']=min((x['font_size_source']*x['scale']*487.56/960 for x in self.formulas),default=None)
        svg=OUT/(self.name+'.svg');ET.ElementTree(self.root).write(svg,encoding='utf-8',xml_declaration=True)
        pdf=OUT/(self.name+'.pdf');cairosvg.svg2pdf(url=str(svg),write_to=str(pdf))
        doc=fitz.open(pdf);assert len(doc)==1
        doc[0].get_pixmap(matrix=fitz.Matrix(240/72,240/72)).save(OUT/(self.name+'.png'))
        self.meta['outputs']={ext:{'path':'figures/'+self.name+'.'+ext,'sha256':hashlib.sha256((OUT/(self.name+'.'+ext)).read_bytes()).hexdigest()} for ext in ['svg','pdf','png']}
        (OUT/(self.name+'.json')).write_text(json.dumps(self.meta,ensure_ascii=False,indent=2)+'\n')
        return self.meta

def mechanism_core(c,x=434,y=40):
    c.rect(x,y,310,298,PALE,TEAL,2,12)
    c.text(x+18,y+27,'Tokenwise allocation',22,TEAL,'bold')
    c.text(x+18,y+50,'SID position × modality slot',15.5,TEAL)
    cols=['Base','T','I','A','V'];colx=x+80;cellw=41;rowh=24
    for m,label in enumerate(cols):c.text(colx+m*cellw+cellw/2,y+74,label,16,TEAL,'bold',anchor='middle')
    for j in range(4):
        c.text(x+18,y+99+j*rowh,f'j = {j+1}',16,INK)
        for m in range(5):
            fill='#D5EDE8' if m==0 else ('#C2E5DF' if (j+m)%3 else '#8ACBC1')
            if m==4:fill='#EBEFEE'
            c.rect(colx+m*cellw,y+81+j*rowh,cellw-2,rowh-2,fill,'white',.6)
            if m==4:c.text(colx+m*cellw+cellw/2,y+100+j*rowh,'0',16,GRAY,anchor='middle')
            else:c.math(colx+m*cellw+7,y+87+j*rowh,rf'w_{{{j+1},{m}}}',16,color=TEAL)
    c.math(x+17,y+177,r'w_{j,m}\propto\bar a_m e^{g_{j,m}},\quad\bar a_0=1',18,color=TEAL,maxwidth=280)
    c.math(x+17,y+207,r'r_{j,m,v}=B\tanh(d_{j,m,v}/B)',19,color=INK,maxwidth=280)
    c.math(x+17,y+235,r'\ell_{j,v}=b_{j,v}+\sum_{m=1}^{M}w_{j,m}r_{j,m,v}',19,color=INK,maxwidth=280)

def architecture():
    c=Canvas('architecture',500,'Observed behavior and content feed tokenwise bounded residual allocation; detached out-of-fold utility targets supervise the gate.','implemented')
    c.text(18,26,'Observed history',20,INK,'bold')
    c.photo(18,42,166,102)
    c.lines(18,166,['Author caption:','White tent below','snowy peaks.'],size=15.5,step=20)
    c.text(18,239,'Historical SID events',15.5,INK,'bold')
    c.tokens(18,249,['2','1','5','7'],width=34,height=28,gap=5)
    c.text(18,302,'Masked target state',15.5,INK,'bold')
    c.tokens(18,312,['2','M','5','M'],width=34,height=28,gap=5)
    c.line(203,38,203,348)
    c.text(223,26,'Parallel condition paths',18,INK,'bold')
    c.text(223,63,'Behavior Transformer',17,NAVY,'bold')
    for k in range(3):
        c.rect(227+k*3,77+k*21,167,19,'#E5EEF5',NAVY,1,3)
    c.text(310,114,'prefix-masked blocks',15.5,NAVY,anchor='middle')
    c.math(224,146,r'h_j\in\mathbb{R}^{d}',18,color=NAVY)
    c.math(224,171,r'b_j\in\mathbb{R}^{V_j}',18,color=NAVY)
    c.arrow([(185,263),(212,263),(212,101),(223,101)],NAVY)
    c.arrow([(185,326),(215,326),(215,128),(227,128)],NAVY,1.5)
    c.arrow([(400,121),(418,121),(418,115),(434,115)],NAVY)
    c.text(223,209,'Frozen media encoders',17,VIOLET,'bold')
    for k,label in enumerate(['text','image','audio','video']):c.icon(223+k*44,220,label)
    c.lines(223,279,['Trainable projections','and history pools'],size=16,step=22,fill=VIOLET)
    c.math(224,316,r'h_m,\ \xi\ \longrightarrow\ d_{j,m}',18,color=VIOLET)
    c.arrow([(185,93),(198,93),(198,236),(224,236)],VIOLET,1.6)
    c.arrow([(402,283),(417,283),(417,253),(434,253)],VIOLET)
    mechanism_core(c)
    c.text(775,26,'Feasible catalog',19,INK,'bold')
    c.text(775,53,'Visible SID levels 1, 3',15.5,GRAY)
    c.tokens(775,65,['2','M','5','M'],width=34,height=27,gap=5)
    c.text(779,118,'ID       Complete tuple',15.5,INK,'bold')
    tuples=[('A',[2,1,5,7],True),('B',[2,4,5,3],True),('C',[2,1,6,7],False),('D',[4,1,5,7],False)]
    for k,(name,code,keep) in enumerate(tuples):
        y=130+k*31;c.rect(773,y,173,28,PALE if keep else '#F4F5F6')
        c.text(782,y+20,name,16,TEAL if keep else GRAY,'bold')
        c.text(811,y+20,','.join(map(str,code)),16,TEAL if keep else GRAY)
        if keep:tag(c.root,'polyline',points=f'930,{y+15} 934,{y+20} 942,{y+10}',fill='none',stroke=TEAL,stroke_width=1.8)
        else:
            c.line(930,y+11,940,y+21,CORAL,1.6);c.line(930,y+21,940,y+11,CORAL,1.6)
    c.arrow([(744,281),(771,281)],TEAL,2.3)
    c.math(778,264,r'\pi(i)\propto e^{S(i)}',19,color=TEAL,maxwidth=166)
    c.lines(775,308,['Joint SID update','from a feasible item'],size=15.5,step=21)
    c.text(18,361,'Exact base: all absent or explicit all-base override.',15.5,INK)
    c.line(18,377,944,377,LINE,1.5)
    c.text(18,401,'OFFLINE SUPERVISION',16,AMBER,'bold')
    c.lines(18,428,['Cross-fitted, frozen teacher','Same state and catalog support'],size=15.5,step=22,fill=AMBER)
    c.math(282,392,r'S',19,color=AMBER);c.math(278,430,r'S\cup\{m\}',18,color=AMBER)
    for y in [394,432]:
        c.rect(365,y,90,28,WARM,AMBER,1.1,3);c.text(410,y+20,'teacher',16,AMBER,anchor='middle')
    c.arrow([(343,408),(365,408)],AMBER,1.5);c.arrow([(351,446),(365,446)],AMBER,1.5)
    c.line(455,408,470,408,AMBER);c.line(455,446,470,446,AMBER);c.line(470,408,470,446,AMBER)
    c.math(488,397,r'u_{j,m}=\mathbb{E}_S[L_j^{-f}(S)-L_j^{-f}(S\cup\{m\})]',18,color=AMBER,maxwidth=450)
    c.math(490,437,r'\mathrm{sg}(w_j^*)\ \longrightarrow\ \mathrm{KL}(w_j^*\Vert w_j)',19,color=AMBER,maxwidth=400)
    c.arrow([(712,435),(751,435),(751,352),(690,352),(690,339)],AMBER,1.8,'6 4')
    c.text(18,486,'Implemented topology · photo: adore chang, CC0 · matrix shading is illustrative; V participates when observed',15.5,GRAY)
    return c.save({'ai_layout':'main_figure_revision_v8/p03/generated/layout_A2.png','sources':['sections/02_method.tex','../code/concordrec/concordrec/model.py','../code/concordrec/concordrec/objectives.py'],'photo_manifest':'redesign_v8/assets/photo_manifest.json','corrections_to_ai':['base is zero residual, not a media encoder','symbolic gate cells, no invented weights','SID indices are positions, not modalities','arbitrary S coalition','tanh bound and detached utility are exact']})

def utility():
    c=Canvas('utility',388,'The same frozen out-of-fold teacher compares two evidence coalitions on identical feasible support; the partition-loss reduction supplies detached gate targets.','implemented')
    c.title('Catalog-conditioned modality utility','OFFLINE TRAINING')
    c.photo(20,69,144,91)
    c.lines(20,182,['White tent below','snowy peaks.','Author caption'],size=15.5,step=21)
    c.text(20,262,'Fixed masked state',16,INK,'bold');c.tokens(20,276,['7','M','M'],width=40)
    c.text(215,77,'Paired evidence coalitions',18,AMBER,'bold')
    c.rect(215,94,147,67,LAV);c.text(232,119,'S = {text}',17,VIOLET,'bold')
    c.text(232,145,'observed caption',15.5,VIOLET)
    c.rect(215,192,147,67,LAV);c.math(232,199,r'S\cup\{\mathrm{image}\}',17,color=VIOLET,maxwidth=128)
    c.text(232,243,'caption + photo',15.5,VIOLET)
    for y in [107,205]:
        c.rect(404,y,129,43,WARM,AMBER,1.3,5);c.math(413,y+9,r'\mathrm{teacher}\ \theta^{-f}',18,color=AMBER,maxwidth=112)
    c.line(468,152,468,202,AMBER,1.2,'3 3');c.text(486,183,'shared',15.5,AMBER)
    c.arrow([(363,127),(404,127)],VIOLET);c.arrow([(363,225),(404,225)],VIOLET)
    c.math(568,107,r'L_j^{-f}(S)',22,color=AMBER);c.math(568,206,r'L_j^{-f}(S\cup\{m\})',22,color=AMBER)
    c.arrow([(534,128),(558,128)],AMBER);c.arrow([(534,226),(558,226)],AMBER)
    c.line(757,128,776,128,AMBER,2);c.line(757,226,776,226,AMBER,2);c.line(776,128,776,226,AMBER,2)
    c.rect(802,122,139,105,PALE,TEAL,1.5,7);c.text(871,147,'Loss reduction',16,TEAL,'bold',anchor='middle')
    c.math(820,167,r'\Delta L_j(S,m)',19,color=TEAL)
    c.text(872,211,'average over S',15.5,TEAL,anchor='middle');c.arrow([(776,177),(801,177)],AMBER)
    c.rect(211,283,575,63,'#F5F8FA')
    c.math(228,290,r'L_j^{-f}(S)=-\log\!\sum_{i\in\mathcal{C}:\,z_j(i)=y_j}\pi^{-f}(i\mid S)',21,maxwidth=545)
    c.rect(802,283,139,63,PALE,TEAL,1,4);c.math(830,289,r'\mathrm{sg}(w_j^*)',21,color=TEAL)
    c.text(871,335,'gate target',15.5,TEAL,anchor='middle')
    c.arrow([(871,229),(871,281)],TEAL,1.7,'5 4')
    c.text(20,370,'Same state, eligible catalog, and teacher snapshot in both arms · training labels enter the loss only',15.5,GRAY)
    return c.save({'sources':['sections/02_method.tex','../code/concordrec/concordrec/objectives.py'],'photo_manifest':'redesign_v8/assets/photo_manifest.json'})

def support():
    c=Canvas('support',366,'Posting-list intersection matches every visible SID position and preserves a complete-item hypothesis for simultaneous commitments.','illustrative')
    c.title('Catalog support under arbitrary visible positions','ILLUSTRATIVE CATALOG')
    c.text(22,80,'Partial SID',17,INK,'bold');c.tokens(22,96,['2','M','5','M'],width=42,height=35,gap=7)
    c.rect(23,161,262,51,'#EEF4FA');c.math(36,171,r'P_{1,2}=\{A,B,C\}',22,color=NAVY)
    c.rect(23,229,262,51,PALE);c.math(36,239,r'P_{3,5}=\{A,B,D\}',22,color=TEAL)
    c.arrow([(286,186),(316,186),(316,219),(337,219)],NAVY)
    c.arrow([(286,254),(316,254),(316,219),(337,219)],TEAL)
    c.math(342,203,r'\cap',38,color=TEAL)
    c.arrow([(385,220),(417,220)],TEAL)
    c.text(442,78,'Item',16,INK,'bold')
    for j in range(4):c.text(512+j*57,78,f'j = {j+1}',15.5,INK,'bold',anchor='middle')
    c.text(801,78,'All visible positions match',15.5,INK,'bold',anchor='middle')
    rows=[('A',[2,1,5,7],True),('B',[2,4,5,3],True),('C',[2,1,6,7],False),('D',[4,1,5,7],False)]
    for k,(name,code,keep) in enumerate(rows):
        y=94+44*k;c.rect(427,y,510,39,PALE if keep else '#F6F7F8')
        c.text(446,y+26,name,18,TEAL if keep else GRAY,'bold')
        for j,value in enumerate(code):
            wrong=(j==0 and value!=2) or (j==2 and value!=5)
            c.rect(489+j*57,y+5,43,29,CORAL if wrong else (NAVY if j in [0,2] else 'white'),LINE,.7,2)
            c.text(511+j*57,y+26,str(value),17,'white' if wrong or j in [0,2] else INK,anchor='middle')
        c.text(822,y+26,'retain' if keep else 'exclude',17,TEAL if keep else CORAL,anchor='middle')
    c.line(20,293,940,293)
    c.text(22,325,'Choose feasible B',17,TEAL,'bold');c.arrow([(210,319),(248,319)],TEAL)
    c.tokens(267,302,['2','4','5','3'],width=43,height=34,gap=6,color=TEAL)
    c.lines(506,315,['Commit unresolved levels 2 and 4 from this same item.','The resulting tuple remains in the feasible catalog.'],size=15.5,step=23)
    return c.save({'data':json.loads((HERE/'sources/figure_data.json').read_text())['support'],'sources':['sections/02_method.tex','../code/concordrec/concordrec/catalog.py','../code/concordrec/concordrec/decode.py']})

def sensitivity():
    c=Canvas('sensitivity',344,'The sufficient top-K boundary gap grows linearly with equal per-position gate error and unresolved SID length.','simulation')
    c.title('Analytical sensitivity of the ranking boundary','DETERMINISTIC CALCULATION')
    x0,x1,y0,y1=77,630,271,76
    for value in [0,.5,1,1.5,2,2.5]:
        y=y0-value/2.5*(y0-y1);c.line(x0,y,x1,y);c.text(x0-13,y+5,f'{value:g}',15.5,GRAY,anchor='end')
    for value in [0,.05,.1,.15,.2,.25,.3]:
        x=x0+value/.3*(x1-x0);c.line(x,y0,x,y0+5,GRAY);c.text(x,y0+25,f'{value:.2f}',15.5,GRAY,anchor='middle')
    c.line(x0,y1,x0,y0,INK,1.4);c.line(x0,y0,x1,y0,INK,1.4)
    for length,color,dash in [(1,NAVY,None),(2,TEAL,'8 3'),(4,VIOLET,'2 4')]:
        endpoint=2*length*.3;y=y0-endpoint/2.5*(y0-y1)
        c.line(x0,y0,x1,y,color,2.6,dash);tag(c.root,'circle',cx=x1,cy=y,r=4,fill=color)
        c.text(x1+12,y+5,f'L = {length}',16,color,'bold')
    c.text(355,330,'Per-position gate error ε',17,INK,anchor='middle')
    t=c.text(22,184,'Required boundary gap',17,INK,anchor='middle');t.set('transform','rotate(-90 22 184)')
    c.rect(739,71,202,218,'#F5F8FA',LINE,1,7)
    c.text(754,99,'Sufficient condition',17,INK,'bold')
    c.math(757,122,r'\mathrm{gap}>4BL\epsilon',22,maxwidth=171)
    c.math(757,166,r'B=0.5',21)
    c.lines(754,207,['L: unresolved positions','ε: common L₁ gate error','Fixed-state bound'],size=15.5,step=26)
    return c.save({'data':{'formula':'4*B*L*epsilon','B':.5,'L':[1,2,4],'epsilon_domain':[0,.3],'endpoints':[.6,1.2,2.4]},'sources':['sections/03_analysis.tex','sections/07_appendix.tex'],'source_status':'analytical, not experimental'})

def reported_scores():
    c=Canvas('reported_scores',368,'Published BM3 and DiffMM NDCG@20 values are compared within each dataset using a common zero-based scale.','measured')
    c.title('Published NDCG@20 within each dataset','SOURCE-REPORTED · R')
    colors={'BM3':NAVY,'DiffMM':TEAL}
    for k,name in enumerate(colors):
        x=594+k*150;c.line(x,66,x+28,66,colors[name],3)
        if name=='BM3':tag(c.root,'circle',cx=x+14,cy=66,r=5,fill='white',stroke=colors[name],stroke_width=2)
        else:tag(c.root,'polygon',points=f'{x+14},60 {x+20},66 {x+14},72 {x+8},66',fill=TEAL)
        c.text(x+38,72,name,16,colors[name],'bold')
    data=json.loads((HERE/'sources/figure_data.json').read_text())['reported_scores']
    x0,x1=260,865;yrows=[119,193,267]
    for k,(dataset,y) in enumerate(zip(data['datasets'],yrows)):
        if k%2==0:c.rect(20,y-30,922,64,'#F7F9FA')
        c.text(24,y+4,dataset,17,INK,'bold')
        for j,name in enumerate(['BM3','DiffMM']):
            yy=y+(j-.5)*24;value=data['series'][name][k];x=x0+value/.05*(x1-x0)
            c.line(x0,yy,x,yy,colors[name],2)
            if j==0:tag(c.root,'circle',cx=x,cy=yy,r=5.2,fill='white',stroke=colors[name],stroke_width=2)
            else:tag(c.root,'polygon',points=f'{x},{yy-6} {x+6},{yy} {x},{yy+6} {x-6},{yy}',fill=TEAL)
            c.text(x+12,yy+5,f'{value:.4f}',16,colors[name])
    c.line(x0,306,x1,306,INK,1.3)
    for value in [0,.01,.02,.03,.04,.05]:
        x=x0+value/.05*(x1-x0);c.line(x,302,x,310,INK);c.text(x,332,f'{value:.2f}',15.5,GRAY,anchor='middle')
    c.text(20,355,'DiffMM Table 1, p. 6 · published protocols retained',15.5,GRAY)
    c.text(742,355,'NDCG@20 (higher is better)',15.5,INK,anchor='middle')
    return c.save({'data':data,'source_reported_not_local':True,'source_url':'https://arxiv.org/abs/2406.11781v1','source_table':1,'source_page':6})

def waveform(c,x,y,w,color=TEAL):
    pts=[]
    for k in range(101):
        amp=math.sin(k*.47)*math.sin(k*.093)**2*12
        pts.append((x+w*k/100,y+amp))
    tag(c.root,'polyline',points=' '.join(f'{a:.2f},{b:.2f}' for a,b in pts),fill='none',stroke=color,stroke_width=1.7)

def interventions():
    c=Canvas('interventions',413,'Missingness, visual degradation, and text conflict change exactly one input field while preserving the historical item identity.','illustrative')
    c.title('Controlled observation interventions','ILLUSTRATIVE INPUTS')
    cols=[154,352,550,748];w=182
    names=['Reference','Missing audio','Degraded visual','Conflicting text']
    for x,name,color in zip(cols,names,[INK,NAVY,AMBER,CORAL]):
        c.text(x+w/2,78,name,17,color,'bold',anchor='middle')
    c.lines(20,133,['Visual','observation'],size=16,step=22,fill=GRAY)
    c.text(20,236,'Audio',16,GRAY);c.text(20,301,'Caption',16,GRAY)
    for k,x in enumerate(cols):
        if k==2:
            # An explicit low-resolution corruption example, not new image content.
            im=ImageOps.fit(Image.open(HERE/'assets/tent.jpg').convert('RGB'),(1820,1010)).resize((18,10))
            for yy in range(10):
                for xx in range(18):
                    pixel=im.getpixel((xx,yy));color='#%02x%02x%02x'%pixel
                    c.rect(x+xx*w/18,94+yy*101/10,w/18+.2,101/10+.2,color)
            c.rect(x-2,92,w+4,105,'none',AMBER,2)
        else:c.photo(x,94,w,101)
        if k==1:
            c.rect(x,215,w,38,'#EEF4FA',NAVY,1.3,3);c.text(x+w/2,240,'unavailable',16,NAVY,anchor='middle')
        else:waveform(c,x,234,w)
        c.rect(x,276,w,65,'#FAEEEE' if k==3 else '#F5F7FA',CORAL if k==3 else LINE,1,3)
        c.lines(x+12,301,['Red cardigan','with buttons.'] if k==3 else ['White tent below','snowy peaks.'],size=15.5,step=21,fill=CORAL if k==3 else INK)
        c.text(x+w/2,365,['original inputs','a_audio = 0','reduced resolution','authored donor caption'][k],15.5,[GRAY,NAVY,AMBER,CORAL][k],anchor='middle')
    c.line(20,383,940,383)
    c.text(20,405,'Same item and SID in every column · identical unchanged fields · photo: adore chang, CC0; waveform illustrative',15.5,GRAY)
    return c.save({'photo_manifest':'redesign_v8/assets/photo_manifest.json','photo_caption':'author-written descriptive caption','degradation':'deterministic 18x10 RGB downsample displayed as vector pixels','audio':'hand-constructed waveform illustration, not a recording','sources':['sections/07_appendix.tex'],'invariant':'historical item ID, SID, unmodified modalities'})

def catalog_partition_case():
    d=json.loads((PAPER/'data/catalog_partition_case_v5.json').read_text())
    assert abs(d['single_coalition_loss_difference']-math.log(18/7))<1e-12
    c=Canvas('catalog_partition_case',432,'A fixed raw token probability can yield a different catalog-conditioned target-partition mass.','illustrative')
    c.title('Catalog-conditioned loss: exact worked calculation','SPECIFIED TOY PROBABILITIES')
    c.text(20,76,'A   Observed historical item',17,INK,'bold')
    c.photo(20,92,184,112)
    c.lines(20,226,['Author caption:','White tent below','snowy peaks.'],size=15.5,step=21)
    c.math(20,299,r'S=\{\mathrm{text}\}',19,color=VIOLET)
    c.math(20,334,r'S^+=S\cup\{\mathrm{image}\}',18,color=VIOLET,maxwidth=195)
    c.line(222,65,222,362)
    c.text(242,76,'B   Same four-item support',17,TEAL,'bold')
    c.math(242,96,r'\tilde z=(7,\mathrm{MASK},\mathrm{MASK}),\quad y=A',18,color=INK,maxwidth=376)
    c.text(247,143,'Item',16,INK,'bold');c.text(310,143,'SID',16,INK,'bold')
    c.math(425,126,r'\pi(i;S)',18);c.math(520,126,r'\pi(i;S^+)',18)
    fractions=[('A','7,2,4','1/6','2/7'),('B','7,2,8','1/12','5/14'),('C','7,5,4','1/6','2/7'),('D','7,5,9','7/12','1/14')]
    for k,(name,code,a,b) in enumerate(fractions):
        yy=154+k*34;c.rect(240,yy,373,31,PALE if k<2 else '#F6F7F8')
        c.text(251,yy+22,name,17,TEAL if k<2 else INK,'bold');c.text(310,yy+22,code,17,INK)
        c.text(449,yy+22,a,17,INK,anchor='middle');c.text(556,yy+22,b,17,INK,anchor='middle')
    c.math(242,303,r'p_2(2)=p_2(5)=0.5\quad\mathrm{in\ both\ arms}',17,color=INK,maxwidth=376)
    c.math(242,336,r'p_3:(.2,.1,.7)\ \longrightarrow\ (.4,.5,.1)',18,color=INK,maxwidth=376)
    c.line(634,65,634,362)
    c.text(654,76,'C   Target-code partition',17,TEAL,'bold')
    c.text(654,110,'A and B share z₂ = 2',16,TEAL)
    c.math(654,133,r'P(z_2=2\mid S)=\frac{1}{4}',21,color=TEAL,maxwidth=280)
    c.math(654,179,r'P(z_2=2\mid S^+)=\frac{9}{14}',21,color=TEAL,maxwidth=280)
    c.rect(652,228,288,69,PALE,TEAL,1.2,6)
    c.math(665,242,r'\Delta L_2=\log\frac{18}{7}\approx0.9445',21,color=TEAL,maxwidth=262)
    c.text(654,327,'Raw-token CE difference = 0',16,INK)
    c.line(20,375,940,375)
    c.text(20,402,'D   Offline target',16,AMBER,'bold')
    c.math(192,387,r'\Delta L_j\ \longrightarrow\ u_{j,m}\ \longrightarrow\ \mathrm{sg}(w_j^*)',19,color=AMBER,maxwidth=410)
    c.text(619,401,'Toy probabilities are independent of photo.',15.5,GRAY)
    c.text(20,424,'Photo: adore chang, CC0 · shaded rows define the target-code partition; candidate values are hand specified',15.5,GRAY)
    return c.save({'data':d,'source_data':'data/catalog_partition_case_v5.json','photo_manifest':'redesign_v8/assets/photo_manifest.json','exact_calculation':{'raw_ce_difference':0,'partition_mass_before':.25,'partition_mass_after':9/14,'partition_loss_difference':math.log(18/7)}})

if __name__=='__main__':
    prepare_display_photo()
    manifests=[architecture(),utility(),support(),sensitivity(),reported_scores(),interventions(),catalog_partition_case()]
    (HERE/'figure_manifest.json').write_text(json.dumps(manifests,ensure_ascii=False,indent=2)+'\n')
    print('Rendered:',', '.join(x['outputs']['svg']['path'] for x in manifests))
