from pathlib import Path
import copy,json,re,shutil,colorsys,xml.etree.ElementTree as E
import cairosvg,fitz
from PIL import ImageFont
R=Path(__file__).resolve().parents[3];O=Path(__file__).resolve().parents[1];V=O/'variants';V.mkdir(exist_ok=True);B=R/'outputs/visual_review_20261115/backups'
NS='http://www.w3.org/2000/svg';E.register_namespace('',NS)
def el(p,tag,**attrs):return E.SubElement(p,'{'+NS+'}'+tag,{k.replace('_','-'):str(v) for k,v in attrs.items()})
def prefix(root,pre):
 ids={n.get('id'):pre+n.get('id') for n in root.iter() if n.get('id')}
 for n in root.iter():
  for k,v in list(n.attrib.items()):
   if k=='id':n.set(k,ids[v])
   elif v.startswith('#') and v[1:] in ids:n.set(k,'#'+ids[v[1:]])
   else:
    for old,new in ids.items():v=v.replace('url(#'+old+')','url(#'+new+')')
    n.set(k,v)
 return root

def base_co():
 old=E.parse(B/'03_multimodal_dllm/figures/architecture.svg').getroot();top=copy.deepcopy(old)
 for i,n in reversed(list(enumerate(list(top)))):
  if (216<=i<414) or i in [30,31] or 138<=i<=148 or 160<=i<=170:
   top.remove(n);continue
  dy=0
  if 7<=i<=15:dy=-16
  if 16<=i<=24:dy=-40
  if 25<=i<=35 or 45<=i<=79 or 86<=i<=87 or 90<=i<=91 or 120<=i<=130 or 171<=i<=215:dy=-54
  if 149<=i<=159:dy=-27
  if i in [2,3,131]:n.set('height','458')
  if i==36:n.set('height','174')
  if i==436:n.set('height','36')
  if 102<=i<=119:
   row=0 if i<=105 else 1 if i<=109 else 2 if i<=114 else 3
   if n.tag.endswith('rect'):
    n.set('y',str(172+35*row));n.set('height','30')
   else:dy=-5-13*row
  if i==437:n.set('y','245')
  if i==40:n.set('y','134')
  if i==41:n.set('y','142')
  if i==42:n.set('y','160')
  if i in [43,44]:dy=-42
  if dy:n.set('transform',f'translate(0 {dy}) '+n.get('transform',''))
  if i==80:n.set('d','M184 309 H207 Q215 309 215 297 V156 Q215 148 222 148')
  if i==82:n.set('d','M184 375 H208 Q218 375 218 364 V206 Q218 198 226 198')
  if i==84:n.set('d','M184 113 H193 Q198 113 198 124 V330 Q198 338 207 338 H222')
  if i==85:n.set('transform','translate(0 -54)')
 # All modalities can be observed. V is inside the illustrative convex hull.
 for n in list(top):
  if n.tag.endswith('text') and n.get('x')=='696' and n.text=='0':
   cy=float(n.get('y'))-6;idx=int(round((cy-121)/27));pos=list(top).index(n);top.remove(n);c=E.Element('{'+NS+'}circle',cx='696',cy=str(cy),r=str([4.2,3.8,5,4.5][max(0,min(3,idx))]),fill='#477EAA');c.set('transform',n.get('transform',''));top.insert(pos,c)
  if n.tag.endswith('text') and n.text=='Available modalities':n.text='Observed modalities'
  if n.tag.endswith('text') and n.text=='V' and n.get('x')=='157':n.set('fill','#477EAA')
 el(top,'path',d='M589 345 L578 321',stroke='#477EAA',stroke_width='1.5',fill='none')
 el(top,'circle',cx=578,cy=321,r=4.5,fill='#477EAA')
 t=el(top,'text',x=561,y=309,font_family='Comic Sans MS',font_size=15,fill='#477EAA');t.text='V'
 top.set('viewBox','0 0 960 520');top.set('width','1100');top.set('height',str(520*1100/960));top.set('overflow','hidden');top.set('x','0');top.set('y','0')
 e=prefix(E.parse(R/'outputs/visual_review_20261115/variants/CO-E1.svg').getroot(),'compact_')
 r=E.Element('{'+NS+'}svg',width='172mm',height=f'{172*757/1100}mm',viewBox='0 0 1100 757')
 el(r,'rect',x=0,y=0,width=1100,height=757,fill='white',id='canvas');r.append(top)
 lower=el(r,'svg',x=0,y=608,width=1100,height=149,viewBox='0 505 1100 149',overflow='hidden')
 lower.append(copy.deepcopy(e.find('{'+NS+'}defs')))
 nodes=list(e);start=max(i for i,n in enumerate(nodes) if n.tag.endswith('line') and n.get('y1')=='505')
 for n in nodes[start:]:
  if n.tag.endswith('path') and n.get('d','').startswith('M979 574'):continue
  nn=copy.deepcopy(n)
  if nn.tag.endswith('text') and nn.text=='Train only':nn.text='Offline supervision'
  lower.append(nn)
 el(r,'path',d='M979 677 H1090 V598 H835 V585',stroke='#7563AA',stroke_width=1.6,stroke_dasharray='4 4',fill='none',marker_end='url(#compact_a7563AA)')
 return r

PALETTES={
 'original':None,
 'pink_iris':{'teal':'#9774AF','purple':'#BD6F94','blue':'#7D8EB9','rose':'#D67791','ink':'#342F49','gray':'#777187','pale':'#FAF6FC'},
 'sea_coral':{'teal':'#428C94','purple':'#CF806F','blue':'#68AEBE','rose':'#D89688','ink':'#284A53','gray':'#687E83','pale':'#F3FAF8'},
 'sky_rose':{'teal':'#669FCB','purple':'#B67EAE','blue':'#6F9FC0','rose':'#D77C9F','ink':'#31465F','gray':'#74829A','pale':'#F8F8FD'}
}
def rgb(h):return tuple(int(h[i:i+2],16)/255 for i in (1,3,5))
def hx(v):return '#'+''.join(f'{max(0,min(255,round(x*255))):02X}' for x in v)
def blend(h,a):return hx(tuple(1-a+a*x for x in rgb(h)))
def role(h):
 rr,gg,bb=rgb(h);H,L,S=colorsys.rgb_to_hls(rr,gg,bb);H*=360
 if S<.12:return 'gray'
 if 140<=H<195:return 'teal'
 if 195<=H<235:return 'blue'
 if 235<=H<295:return 'purple'
 return 'rose'
def vector_geometry(r):
 # Rebuild only candidate geometry as native vectors so every plane follows its palette.
 for parent in r.iter():
  for child in list(parent):
   if not child.tag.endswith('svg'):continue
   if child.get('x')=='35' and child.get('y')=='455':
    g=E.Element('{'+NS+'}g');defs=el(g,'defs')
    for k,col in [('left','#665AA8'),('right','#12887E')]:
     grad=el(defs,'radialGradient',id='sphere_'+k,cx='.35',cy='.25',r='.8')
     for off,c,op in [('0%','#FFFFFF','1'),('55%',col,'.25'),('100%',col,'.65')]:el(grad,'stop',offset=off,stop_color=c,stop_opacity=op)
     grad=el(defs,'linearGradient',id='drop_'+k,x1=0,y1=0,x2=0,y2=1)
     el(grad,'stop',offset='0%',stop_color=col,stop_opacity='.22');el(grad,'stop',offset='100%',stop_color=col,stop_opacity='0')
    el(g,'polygon',points='37,550 444,550 410,516 70,516',fill='#DDECF2',fill_opacity='.65',stroke='#A4C2D4',stroke_width='.7')
    for cx,col,k in [(157.72266,'#665AA8','left'),(322.73957,'#12887E','right')]:
     cy=527.80158;rr=67.94814
     el(g,'rect',x=cx-rr,y=cy,width=2*rr,height=118,fill='url(#drop_'+k+')')
     el(g,'circle',cx=cx,cy=cy,r=rr,fill='url(#sphere_'+k+')',stroke=col,stroke_width='.9')
     for scale in [.28,.62]:el(g,'ellipse',cx=cx,cy=cy,rx=rr*scale,ry=rr,fill='none',stroke=col,stroke_width='.6',stroke_opacity='.6')
     for yy,rx in [(cy-34,rr*.86),(cy,rr),(cy+34,rr*.86)]:el(g,'ellipse',cx=cx,cy=yy,rx=rx,ry=rr*.19,fill='none',stroke=col,stroke_width='.6',stroke_opacity='.6')
    pos=list(parent).index(child);parent.remove(child);parent.insert(pos,g)
   elif child.get('x')=='875':
    g=E.Element('{'+NS+'}g');defs=el(g,'defs')
    for k,col in [('teal','#12887E'),('iris','#665AA8')]:
     gr=el(defs,'linearGradient',id='sheet_'+k,x1=0,y1=0,x2=1,y2=1)
     el(gr,'stop',offset='0%',stop_color=col,stop_opacity='.1');el(gr,'stop',offset='100%',stop_color=col,stop_opacity='.45')
    el(g,'polygon',points='890,710 1028,480 1142,692',fill='url(#sheet_teal)',stroke='#12887E',stroke_width='.65')
    el(g,'polygon',points='941,738 1058,508 1169,718',fill='url(#sheet_iris)',stroke='#665AA8',stroke_width='.65')
    el(g,'path',d='M906 705 L1033 502 L1128 686 M957 733 L1060 528 L1153 713',fill='none',stroke='#FFFFFF',stroke_width='1',stroke_opacity='.55')
    el(g,'circle',cx=1052.6087,cy=595.913,r=6,fill='#12887E',stroke='#FFFFFF',stroke_width='1.1')
    el(g,'circle',cx=1039.1304,cy=649.3913,r=6,fill='#665AA8',stroke='#FFFFFF',stroke_width='1.1')
    pos=list(parent).index(child);parent.remove(child);parent.insert(pos,g)
 return r

def theme(root,palette,bg):
 r=copy.deepcopy(root);pal=PALETTES[palette]
 if pal:r=vector_geometry(r)
 for n in r.iter():
  tag=n.tag.split('}')[-1]
  if tag in ['text','tspan']:
   n.set('font-family','Comic Sans MS')
   if n.text=='Complete SID candidates':n.text='Complete candidates'
   if n.text=='fixed candidate list':n.text='fixed candidates'
   if n.text=='768-D fixed space':n.set('font-size','18')
  if not pal:continue
  for key,val in list(n.attrib.items()):
   if key not in ['fill','stroke','stop-color','style']:continue
   def sub(m):
    h=m.group();H,L,S=colorsys.rgb_to_hls(*rgb(h));rr=role(h)
    if L<.16 or (L<.25 and S<.75):return pal['ink']
    if tag=='text':return pal['gray'] if S<.16 else pal[rr]
    if L>.83:
     a=(.06 if bg=='white' else .15) if key!='stroke' else .32
     return blend(pal[rr],a)
    if L>.65:return blend(pal[rr],.35 if key in ['fill','stop-color'] else .55)
    return pal[rr]
   n.set(key,re.sub(r'#[0-9a-fA-F]{6}\b',sub,val))
 # Root/background white; only very light page tint in the alternate view.
 back='white' if bg=='white' or pal is None else pal['pale']
 for n in r.iter():
  if n.tag.endswith('rect') and n.get('x')=='0' and n.get('y')=='0' and float(n.get('width','0'))>=960:n.set('fill',back)
 return r

def render(r,id):
 p=V/(id+'.svg');E.ElementTree(r).write(p,encoding='unicode',xml_declaration=True)
 cairosvg.svg2pdf(url=str(p),write_to=str(p.with_suffix('.pdf')))
 d=fitz.open(p.with_suffix('.pdf'));d[0].get_pixmap(matrix=fitz.Matrix(2.7,2.7)).save(p.with_suffix('.png'))
 (V/(id+'.json')).write_text(json.dumps({'id':id,'status':'illustrative','font':'Comic Sans MS; math retains dedicated vector math glyphs','claim':'Omni preserves provider geometry through quantization; CONCORD allocates bounded modality corrections with offline utility supervision.','sources':['prior approved architecture SVG','CO-E1 compact offline strip'],'palette_reference':'paper/画图模板/论文配色','installed':id.endswith('original')},indent=2,ensure_ascii=False))

for paper in ['02_omni_sid','03_multimodal_dllm']:
 dest=O/'backups'/paper;dest.mkdir(parents=True,exist_ok=True)
 for file in ['main.tex','main.pdf','figures/architecture.svg','figures/architecture.pdf','figures/architecture.png','sections/01_introduction.tex' if paper.startswith('02') else 'sections/01_positioning.tex']:
  p=R/paper/file;q=dest/file;q.parent.mkdir(parents=True,exist_ok=True)
  if not q.exists():shutil.copy2(p,q)
base_om=E.parse(B/'02_omni_sid/figures/architecture.svg').getroot();baseco=base_co()
for pre,base in [('OM',base_om),('CO',baseco)]:
 for pal in PALETTES:
  for bg in (['white'] if pal=='original' else ['white','tint']):
   id=f'{pre}-F-{pal}'+('' if pal=='original' else '-'+bg);render(theme(base,pal,bg),id)
# Keep the user's old composition in the paper; new palettes remain review variants.
for pre,paper in [('OM','02_omni_sid'),('CO','03_multimodal_dllm')]:
 id=f'{pre}-F-original'
 for ext in ['svg','pdf','png','json']:shutil.copy2(V/(id+'.'+ext),R/paper/'figures'/('architecture.'+ext))
print('Rendered 14 Comic Sans MS variants; installed restored Omni and hybrid CONCORD.')
