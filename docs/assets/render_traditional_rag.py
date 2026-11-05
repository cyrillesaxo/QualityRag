"""Render the README's representative traditional-RAG animation (Pillow)."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont
OUT = Path(__file__).with_name('traditional-rag.gif')
W, H = 508, 507
NAVY='#19283f'; BLUE='#1979bd'; INK='#14243d'; MUTED='#425b74'
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def font(size,bold=False): return ImageFont.truetype(BOLD if bold else FONT,size)
def center(d,xy,s,size=18,bold=False,fill=INK):
    d.multiline_text(xy,s,font=font(size,bold),fill=fill,anchor='mm',align='center',spacing=6)
def box(d,rect,title,subtitle='',fill='#ffffff',edge='#8db9d9'):
    d.rounded_rectangle(rect,16,fill=fill,outline=edge,width=2)
    x=(rect[0]+rect[2])/2;y=(rect[1]+rect[3])/2
    center(d,(x,y-10 if subtitle else y),title,19,True)
    if subtitle: center(d,(x,y+21),subtitle,13,fill=MUTED)
def arrow(d,a,b,t):
    d.line([a,b],fill=BLUE,width=4)
    dx=b[0]-a[0];dy=b[1]-a[1];l=math.hypot(dx,dy);ux=dx/l;uy=dy/l
    d.polygon([b,(b[0]-12*ux+6*uy,b[1]-12*uy-6*ux),(b[0]-12*ux-6*uy,b[1]-12*uy+6*ux)],fill=BLUE)
    p=(a[0]+dx*t,a[1]+dy*t);d.ellipse((p[0]-5,p[1]-5,p[0]+5,p[1]+5),fill='#55cbe6')
stages=[
 ('Ingest & Chunk','Sources become searchable passages.',('PDF','Web','Video'),'Text chunks','Split into passages'),
 ('Embed & Index','Store vectors that support similarity search.',('Chunk A','Chunk B','Chunk C'),'Vector index','Embeddings + passage IDs'),
 ('Retrieve Context','Find passages similar to the question.',('Question','Top-k','Matches'),'Retrieved context','Ranked relevant passages'),
 ('Assemble Prompt','Combine the question with retrieved context.',('Question','Context','Instructions'),'LLM prompt','Question + selected evidence'),
 ('Generate Answer','Generate an answer from the selected context.',('Prompt','Model','Answer'),'Answer + citations','Citations when configured'),
 ('Relevance vs. Coverage','Relevant passages can still omit an exception.',('Retrieved','Relevant','Partial'),'Missing exception?','No explicit completeness contract'),
]
frames=[]
for stage,(title,caption,labels,target,sub) in enumerate(stages):
 for j in range(18):
    im=Image.new('RGB',(W,H),'#f3f9fd');d=ImageDraw.Draw(im)
    for yy in range(90,405,24): d.line((18,yy,490,yy),fill='#eaf3fa')
    d.rounded_rectangle((12,18,496,76),18,fill=NAVY)
    d.ellipse((26,27,65,66),fill='#527694');center(d,(45,46),str(stage+1),24,True,'white')
    center(d,(278,47),title,22,True,'white')
    center(d,(254,108),'TRADITIONAL RAG',15,True,BLUE)
    for k,label in enumerate(labels):
      y=149+77*k
      box(d,(22,y,166,y+57),label,fill='#ffffff')
      arrow(d,(170,y+28),(214,254),((j/18+k/3)%1))
    box(d,(219,195,486,316),target,sub,fill='#e5f3ff')
    if stage==5:
      d.rounded_rectangle((217,340,486,390),12,fill='#fff3df',outline='#e5b15e',width=2)
      center(d,(352,365),'Coverage is not established',15,True,'#805719')
    else:
      center(d,(352,363),'Retrieve → Generate',17,True,BLUE)
    words=caption.split();lines=[];line=''
    for word in words:
      trial=(line+' '+word).strip()
      if d.textlength(trial,font=font(19,True))>466: lines.append(line);line=word
      else: line=trial
    lines.append(line)
    center(d,(254,437),'\n'.join(lines),19,True)
    center(d,(254,487),'Baseline shown without a completeness contract',11,fill=MUTED)
    frames.append(im)
frames[0].save(OUT,save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True,disposal=2)
for i in (0,54,107): frames[i].save(OUT.with_name(f'traditional-preview-{i}.png'))
print(f'{OUT}: {len(frames)} frames, {W}x{H}, 10.8 seconds')