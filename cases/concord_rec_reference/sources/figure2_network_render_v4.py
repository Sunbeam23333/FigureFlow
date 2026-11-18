"""Native v4 network figure; inherited primitives from redesign_v3.
Only network_structure is mutated. Other approved exports are preserved.
"""
from pathlib import Path
import hashlib, json, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, Circle, Polygon, FancyArrowPatch, Ellipse
from matplotlib import font_manager as fm
from PIL import Image
P=Path(__file__).resolve().parents[1]; R=P/'novelty_v4'; F=P/'figures'; FONT=P/'redesign_v2/fonts'
for f in FONT.glob('*.ttf'): fm.fontManager.addfont(str(f))
SANS=fm.FontProperties(fname=str(FONT/'SourceSans3-Regular.ttf'))
BOLD=fm.FontProperties(fname=str(FONT/'SourceSans3-Semibold.ttf'))
# Use STIX for mathematical glyphs. The previous Source Sans/DejaVu fallback
# rendered arrows, set-membership, real-number and infinity symbols as empty
# boxes in Cairo's PDF/SVG output. STIX embeds those symbols reliably while
# leaving surrounding labels in the approved sans-serif family.
plt.rcParams.update({'font.family':SANS.get_name(),'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white','mathtext.fontset':'stix'})
C={'navy':'#183B60','ink':'#16324D','teal':'#087F87','violet':'#8060AB','amber':'#BC8320','muted':'#64778B','line':'#D5E0E9','navybg':'#F0F5FA','tealbg':'#EBF7F4','violetbg':'#F3EFF8','amberbg':'#FFF6E5','white':'#FFFFFF'}
W,H=1600,1260
fig,ax=plt.subplots(figsize=(W/120,H/120));fig.subplots_adjust(0,0,1,1);ax.set(xlim=(0,W),ylim=(H,0));ax.axis('off')
def color(c): return C.get(c,c)
def text(x,y,s,size=24,c='ink',ha='left',bold=False,va='center',**kw):
 return ax.text(x,y,s,fontsize=size*.6,fontproperties=BOLD if bold else SANS,color=color(c),ha=ha,va=va,**kw)
def rect(x,y,w,h,fill='white',edge='line',r=5,lw=1.5,z=2):
 p=FancyBboxPatch((x,y),w,h,boxstyle=f'round,pad=0,rounding_size={r}',fc=color(fill),ec=color(edge),lw=lw,zorder=z);ax.add_patch(p);return p
def line(a,b,c='navy',lw=1.8,ls='-',z=3): ax.plot([a[0],b[0]],[a[1],b[1]],color=color(c),lw=lw,ls=ls,zorder=z)
def arrow(a,b,c='navy',lw=2,ls='-',z=3):
 ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=13,lw=lw,color=color(c),linestyle=ls,zorder=z))
def elbow(points,c='navy',lw=1.8,ls='-'):
 for a,b in zip(points[:-2],points[1:-1]):line(a,b,c,lw,ls)
 arrow(points[-2],points[-1],c,lw,ls)
def poly(points,fill='tealbg',edge='teal',lw=1.5):
 p=Polygon(points,closed=True,fc=color(fill),ec=color(edge),lw=lw,zorder=2);ax.add_patch(p);return p
def hexagon(x,y,w,h,fill='tealbg',edge='teal'):
 return poly([(x+24,y),(x+w-24,y),(x+w,y+h/2),(x+w-24,y+h),(x+24,y+h),(x,y+h/2)],fill,edge)
def chip(x,y,w,h,label,c='navy',fill='white',size=24):
 rect(x,y,w,h,fill,c,r=5);text(x+w/2,y+h/2,label,size,c,'center',True)
def frozen(x,y,c='navy'):
 # Lock marks parameter freezing, not security or data restrictions.
 ax.add_patch(Circle((x,y-5),7,fill=False,ec=color(c),lw=1.4,zorder=3));rect(x-10,y-2,20,16,'white',c,r=2);ax.add_patch(Circle((x,y+5),1.8,fc=color(c),ec='none',zorder=3))
def sheets(x,y,w,h,label,c='navy'):
 for k in [2,1,0]:rect(x+k*7,y-k*7,w,h,'white',c,r=3,lw=1.3)
 text(x+w/2,y+h/2,label,25,c,'center',True)
def asset(crop,dst):
 im=Image.open(R/'assets/network_semantic_assets.png');iw,ih=im.size;sx,sy,sw,sh=crop;x,y,w,h=dst
 ex=(x-sx*w/sw,x+(iw-sx)*w/sw,y+(ih-sy)*h/sh,y-sy*h/sh)
 art=ax.imshow(im,extent=ex,zorder=2.1,aspect='auto');art.set_clip_path(Rectangle((x,y),w,h,transform=ax.transData))
text(34,45,'CONCORD-Rec network architecture',38,bold=True)
text(34,85,'Position-level modality allocation and catalog-conditioned offline utility supervision',24,'muted')
line((30,108),(1570,108),'line',1)
for x,w,fill in [(30,480,'navybg'),(530,580,'tealbg'),(1130,440,'amberbg')]:rect(x,130,w,855,fill,fill,r=12,lw=0,z=0)
text(50,160,'A  Behavioral denoiser',29,'navy',bold=True)
text(550,160,'B  Modality conditioning',29,'teal',bold=True)
text(1150,157,'C  Offline utility supervision',27,'amber',bold=True)
text(1150,190,'Detached targets; no teacher at inference',22,'muted')
# A. Historical tensors and target state are distinct inputs.
text(80,211,'Historical SID',24,'navy',bold=True);sheets(75,244,160,58,r'$z(i_1),\ldots,z(i_n)$')
text(285,211,'Target SID state',24,'violet',bold=True)
for j,v in enumerate(['2','?','?','5']):chip(280+j*48,244,40,53,v,'violet','white',25)
arrow((154,310),(154,337));arrow((374,306),(374,337),'violet')
poly([(70,340),(470,340),(450,405),(90,405)],'white','navy')
text(270,361,'Code + level + position + segment',23,'navy','center',True)
text(270,388,'Recency; noise time on target only',23,'muted','center')
arrow((270,406),(270,453),'navy')
# Stacked layers emphasize the repeated backbone, not repeated nested boxes.
for k in [3,2,1,0]:rect(88+k*10,479-k*12,350,209,'white','navy',r=4,lw=1.6,z=2)
rect(88,479,350,38,'navy','navy',r=4,lw=0)
text(105,499,'Pre-LN Transformer',25,'white',bold=True);text(419,499,r'$\times D$',24,'white','right',True)
text(263,542,'LN $\\rightarrow$ prefix MHA $\\rightarrow$ residual',24,'navy','center',True)
line((106,568),(420,568),'line',1)
text(263,590,'LN $\\rightarrow$ FFN $\\rightarrow$ residual',24,'navy','center',True)
text(263,626,r'FFN: $d\rightarrow4d\rightarrow d$',24,'navy','center')
text(263,665,'All layers trainable',22,'muted','center')
arrow((270,690),(270,737));rect(192,741,257,70,'white','navy',r=5)
text(320,761,'Final normalization',23,'navy','center',True)
text(320,791,r'$h_j\in\mathbb{R}^{d}$',26,'navy','center')
# Tiny mask inset: exact block relations, also given in the paper equation.
text(106,733,'Attention bias',22,'navy','center',True)
for i in range(2):
 for j in range(2):
  x,y=58+j*48,764+i*43;rect(x,y,43,38,'white','line',r=0,lw=1);text(x+21,y+19,'−∞' if (i,j)==(0,1) else '0',22,'violet' if (i,j)==(0,1) else 'navy','center')
text(106,864,'Rows / columns: H, Z',20,'muted','center')
arrow((320,813),(320,873));rect(192,877,257,66,'navy','navy',r=5)
text(320,898,'SID-level linear head',23,'white','center',True)
text(320,927,r'$b_j\in\mathbb{R}^{V_j}$',26,'white','center')
# B. Four genuine semantic icons cropped from the parent-generated no-text asset board.
for cx,label,cr in [(600,'Text',(1145,610,107,142)),(740,'Image',(1297,636,116,119)),(880,'Audio',(1451,623,111,132)),(1020,'Video',(1608,635,124,121))]:
 asset(cr,(cx-42,205,84,100));text(cx,320,label,23,'violet','center',True);arrow((cx,340),(cx,363),'violet',1.6)
rect(560,366,520,69,'white','navy',r=5);frozen(582,398)
text(830,388,'Frozen content encoders',25,'navy','center',True)
text(830,419,r'Separate parameters; output width $d_m$',23,'muted','center')
arrow((820,436),(820,461),'violet')
poly([(568,466),(1072,466),(1048,526),(592,526)],'violetbg','violet')
text(820,486,r'Trainable projection $P_m:d_m\rightarrow d$',25,'violet','center',True)
text(820,514,'Historical items only',22,'muted','center')
arrow((820,528),(820,556),'violet')
hexagon(564,560,512,91,'violetbg','violet')
text(820,587,'Availability-masked attention pool',25,'violet','center',True)
text(820,618,'Historical SID + recency in keys / values',23,'violet','center')
text(820,674,r'Cached modality summary $h_m\in\mathbb{R}^{d}$',25,'violet','center',True)
# State and summary fan out to both residual and position gate.
elbow([(820,690),(820,711),(674,711),(674,760)],'violet',1.7)
elbow([(820,711),(963,711),(963,760)],'violet',1.7)
elbow([(450,778),(504,778),(504,738),(621,738),(621,760)],'navy',1.6)
elbow([(504,738),(907,738),(907,760)],'navy',1.6)
text(535,720,r'$h_j$',23,'navy')
rect(552,764,248,83,'white','teal',r=6)
text(676,785,'Residual adapter',25,'teal','center',True)
text(676,817,r'$[h_j;h_m;E_m]\rightarrow d_{j,m}$',23,'teal','center')
rect(835,764,252,83,'teal','teal',r=6)
text(961,785,'Position gate MLP',25,'white','center',True)
text(961,817,r'$[h_j;h_m;E_m;E_j;\xi]$',23,'white','center')
arrow((676,848),(676,871),'teal');arrow((961,848),(961,871),'teal')
poly([(552,876),(800,876),(785,942),(567,942)],'white','teal')
text(676,902,r'$r_{j,m}=B\tanh(d_{j,m}/B)$',23,'teal','center')
text(676,930,'Elementwise bound',22,'muted','center')
rect(835,876,252,66,'white','teal',r=5)
text(961,896,'Masked softmax',24,'teal','center',True)
# Fit this long label inside the compact output box so it no longer touches
# the dashed supervision arrow at final-paper scale.
text(961,925,'Base + available modalities',18,'teal','center')

# C. Paired teacher branch; support is invariant across coalition calls.
sheets(1175,244,350,67,'','amber')
text(1350,261,'Shared masked state s',24,'amber','center',True)
text(1350,293,r'Coalitions $S$ and $S\cup\{m\}$',24,'amber','center')
arrow((1350,312),(1350,344),'amber')
rect(1185,349,330,62,'white','navy',r=5);frozen(1205,379)
text(1359,371,'Cross-fitted teacher',25,'navy','center',True)
text(1359,398,'Detached label preparation',22,'muted','center')
arrow((1350,412),(1350,451),'amber')
# Cylinder = catalog distribution. Bars are schematic, never experimental values.
rect(1184,470,332,106,'white','amber',r=0,lw=1.5)
ax.add_patch(Ellipse((1350,470),332,28,fc=C['amberbg'],ec=C['amber'],lw=1.5,zorder=2))
ax.add_patch(Ellipse((1350,576),332,25,fc='white',ec=C['amber'],lw=1.5,zorder=2))
text(1350,499,r'Common feasible support $\mathcal{C}_s$',24,'amber','center',True)
for i,h in enumerate([16,31,23,37,13]):rect(1215+i*32,553-h,19,h,'amber','amber',r=1,lw=0)
text(1460,527,r'$\pi_s^{-f}(i;S)$',24,'amber','center')
text(1458,555,'Item posterior',22,'muted','center')
arrow((1350,590),(1350,618),'amber')
hexagon(1168,624,364,90,'amberbg','amber')
text(1350,649,'Target SID partition loss',25,'amber','center',True)
text(1350,686,r'$L_j(S)=-\log\!\sum_{i\in\mathcal{B}_{s,j,z_j(y)}}\pi_s^{-f}(i;S)$',23,'amber','center')
arrow((1350,716),(1350,748),'amber')
hexagon(1168,754,364,81,'amberbg','amber')
text(1350,777,'Paired modality utility',25,'amber','center',True)
text(1350,814,r'$u_{j,m}=\mathbb{E}_S[L_j(S)-L_j(S\cup\{m\})]$',22,'amber','center')
arrow((1350,837),(1350,875),'amber')
rect(1198,881,304,66,'amber','amber',r=17,lw=0)
text(1350,901,r'Masked modality target $w_j^{*}$',23,'white','center',True)
text(1350,930,r'Utility loss: $\mathrm{KL}(w_j^{*}\Vert w_j)$',23,'white','center')
arrow((1197,914),(1089,914),'amber',2.2,'--')
text(1140,880,'supervises',20,'amber','center')
# Common output rail.
line((30,1004),(1570,1004),'line',1)
hexagon(700,1022,234,94,'tealbg','teal')
text(817,1048,'Modality fusion',25,'teal','center',True)
text(817,1088,r'$\sum_m w_{j,m}r_{j,m}$',28,'teal','center')
elbow([(676,943),(676,1068),(699,1068)],'teal',2)
elbow([(961,943),(961,1011),(902,1011),(902,1020)],'teal',2)
ax.add_patch(Circle((1005,1068),25,fc='white',ec=C['navy'],lw=1.8,zorder=3));text(1005,1068,'+',31,'navy','center',True)
arrow((936,1068),(977,1068),'teal',2)
elbow([(320,945),(320,1147),(1005,1147),(1005,1095)],'navy',2)
text(420,1121,r'Behavioral logits $b_j$',26,'navy',bold=True)
arrow((1032,1068),(1074,1068),'teal',2)
rect(1079,1027,185,82,'white','teal',r=5)
text(1171,1050,'Guided logits',25,'teal','center',True);text(1171,1085,r'$\ell_j\in\mathbb{R}^{V_j}$',26,'teal','center')
arrow((1266,1068),(1310,1068),'teal',2)
# Catalog output store, distinct from posterior teacher store above.
rect(1316,1036,229,65,'tealbg','teal',r=2)
ax.add_patch(Ellipse((1430,1036),229,25,fc=C['tealbg'],ec=C['teal'],lw=1.5,zorder=2))
text(1430,1065,'Catalog support',24,'teal','center',True);text(1430,1090,'Feasible SID decoding',22,'teal','center')
arrow((1171,1112),(1171,1130),'amber',1.7)
rect(1065,1135,220,49,'amberbg','amber',r=17);text(1175,1160,'Denoising loss',24,'amber','center',True)
text(1343,1151,'Fixed tokenizer',23,'navy',bold=True);frozen(1324,1150)
text(1343,1180,'No future content input',22,'muted')
# Legend and compact configuration: exact choices, not empirical outcomes.
line((30,1204),(1570,1204),'line',1)
for x,c,label in [(40,'navy','Inherited backbone'),(342,'teal','Conditioning interface'),(705,'violet','Observed conditions'),(1060,'amber','Offline supervision')]:
 rect(x,1226,14,14,c,c,r=2,lw=0);text(x+24,1234,label,21,c)
text(1567,1234,'Proposed architecture',21,'muted','right')
# Raster width = 3200; all labels, shapes, and arrows stay editable vector objects.
for ext in ['pdf','svg','png']:fig.savefig(F/f'network_structure.{ext}',dpi=240)
plt.close(fig)
meta={'revision':'v4','status':'illustrative','evidence_status':'illustrative','claim':'A position-level output gate receives paired catalog-partition utility supervision prepared offline.','editable_source':'novelty_v4/render_network.py','paper_evidence':['sections/02_method.tex: catalog-conditioned loss and utility equations','sections/02_network.tex: network architecture and parameterization'],'main_gate':'position-only; code-conditional architecture remains a registered comparison, not the displayed default','invariants':['same feasible support and masked state for paired coalition teacher calls','historical modality content only','frozen tokenizer and content encoders','cross-fitted teacher detached during label preparation','base residual is zero','utility loss supervises gate; no teacher at inference'],'generated_asset':{'path':'novelty_v4/assets/network_semantic_assets.png','sha256':hashlib.sha256((R/'assets/network_semantic_assets.png').read_bytes()).hexdigest(),'origin':'Parent-generated built-in ImageGen no-text semantic asset board, inspected 2026-11-08','generation_brief':'novelty_v4/assets/generation_provenance.json; reconstructed brief, not verbatim original prompt','model_identifier':'Not exposed by tool; no specific image-model version verified','used_regions':'text, image, audio, and video icons only','role':'illustrative semantic input icons; no model result or logo','text_arrows_topology':'native Matplotlib vector geometry'},'diagram_bars':'illustrative posterior glyphs with no quantitative scale','palette':C,'outputs':{e:hashlib.sha256((F/f'network_structure.{e}').read_bytes()).hexdigest() for e in ['pdf','svg','png']}}
(F/'network_structure.json').write_text(json.dumps(meta,indent=2))
(R/'figure_manifest.json').write_text(json.dumps(meta,indent=2))
print('P3 v4 network_structure rendered; all other figures preserved.')
