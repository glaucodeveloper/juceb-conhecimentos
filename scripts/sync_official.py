#!/usr/bin/env python3
"""Sync official legislative source files and compile source-faithful OKF units.

Requires an internet connection on the machine executing it.
Optional: pip install beautifulsoup4 pymupdf
As opposed to `build.py`, this script does not invent or reconstruct legal text.

Usage:
  python sync_official.py --verified-only
  python sync_official.py --all --limit 5
  python sync_official.py --ids BR.LC.123.2006 BR.BA.Decreto_BA.13780.2012
"""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, html, json, pathlib, re, subprocess, tempfile, time, urllib.request, urllib.parse, urllib.error, unicodedata, sys, os
ROOT=pathlib.Path(__file__).resolve().parents[1]
ALLOWED=('planalto.gov.br','receita.fazenda.gov.br','gov.br','ba.gov.br','sefaz.ba.gov.br','fazenda.gov.br')
MAX_BYTES=42*1024*1024

def jdump(obj,p):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def slug(value):
 v=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()
 return re.sub('[^a-z0-9]+','-',v).strip('-')

def download(url, retries=2):
 p=urllib.parse.urlsplit(url); hostname=(p.hostname or '').lower()
 if p.scheme!='https' or not any(hostname == d or hostname.endswith('.'+d) for d in ALLOWED):
  raise ValueError(f'Host/protocolo não permitido: {url}')
 err=None
 for attempt in range(retries+1):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; OKF-Legislacao-Crawler/0.1; +local-usage)','Accept':'text/html,application/pdf,application/octet-stream;q=0.8','Accept-Language':'pt-BR,pt;q=0.9'})
   with urllib.request.urlopen(req,timeout=40) as response:
    u=response.geturl(); h=urllib.parse.urlsplit(u).hostname or ''
    if not any(h == d or h.endswith('.'+d) for d in ALLOWED): raise ValueError('Redirecionamento para domínio não oficial')
    content=response.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES: raise ValueError('Arquivo excede limite de segurança')
    return content,response.headers.get('Content-Type',''),u
  except Exception as e: err=e;time.sleep(0.3*(attempt+1))
 raise RuntimeError(f'Falha de download: {err}')

def decode_html(body):
 # BeautifulSoup provides excellent preservation of paragraph boundaries when installed.
 if b'<html' not in body[:12000].lower() and b'<!doctype' not in body[:12000].lower():
  pass
 try:
  from bs4 import BeautifulSoup
  doc=BeautifulSoup(body,'html.parser')
  for tag in doc(['style','script','noscript','svg','iframe','nav','footer']): tag.decompose()
  text=doc.get_text('\n',strip=True)
  return text
 except ImportError:
  from html.parser import HTMLParser
  class Text(HTMLParser):
   def __init__(self): super().__init__();self.out=[];self.off=0
   def handle_starttag(self,tag,attrs):
    if tag in ('script','style','noscript'): self.off+=1
    if tag in ('p','div','tr','li','br','h1','h2','h3','h4','section'):self.out.append('\n')
   def handle_endtag(self,tag):
    if tag in ('script','style','noscript'):self.off=max(self.off-1,0)
    if tag in ('p','div','tr','li','br','h1','h2','h3','h4'):self.out.append('\n')
   def handle_data(self,data):
    if not self.off:self.out.append(data)
  
  try:
   decoded=body.decode('utf-8')
  except UnicodeDecodeError:
   decoded=body.decode('cp1252','replace')
  o=Text();o.feed(decoded); return html.unescape(' '.join(o.out))

def pdf_extract(data):
 try:
  import fitz
  pdf=fitz.open(stream=data,filetype='pdf');return [p.get_text('text') for p in pdf]
 except ImportError:
  with tempfile.TemporaryDirectory() as d:
   pf=pathlib.Path(d)/'doc.pdf';tf=pathlib.Path(d)/'doc.txt';pf.write_bytes(data)
   r=subprocess.run(['pdftotext','-layout',str(pf),str(tf)],capture_output=True)
   if r.returncode:raise RuntimeError('Instale pymupdf ou pdftotext para extrair PDF')
   return tf.read_text(errors='replace').split('\f')

def normalize(text):
 return re.sub(r'\n{4,}','\n\n\n',re.sub(r'[ \t]+',' ',text)).strip()+'\n'

# Regex deliberately matches the beginning of a physical line. Results marked automatic.
ART=re.compile(r'(?im)^\s*(?:Art(?:igo)?\.?\s*)(\d{1,4}(?:-[A-Z])?)(?:\s*[º°oª])?\s*(?:[.\-–])?\s*(?=\S)')
def split_articles(text,max_units=1500):
 matches=list(ART.finditer(text)); out=[]
 # Deduplicate overlapping repeated labels in PDF headers; preserve text as found.
 for i,m in enumerate(matches[:max_units]):
  end=matches[i+1].start() if i+1<len(matches) else len(text)
  chunk=text[m.start():end].strip()
  if len(chunk)<35 or len(chunk)>250000:continue
  label=m.group(1)
  out.append({'article':label,'raw':chunk,'char_start':m.start(),'char_end':end,'extraction':'regex_auto_not_legally_consolidated'})
 return out

def main():
 ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group()
 g.add_argument('--verified-only',action='store_true',help='Processa somente URLs consultadas na pesquisa inicial')
 g.add_argument('--all',action='store_true',help='Inclui URLs do catálogo ainda não conferidas')
 g.add_argument('--ids',nargs='+',help='IDs do catálogo, iguais aos do catálogo JSON')
 ap.add_argument('--limit',type=int,default=0,help='Número máximo de atos neste processamento')
 ap.add_argument('--overwrite',action='store_true',help='Rebaixar PDFs/HTML mesmo que já estejam no disco')
 ap.add_argument('--delay',type=float,default=0.5)
 args=ap.parse_args()
 registry=json.loads((ROOT/'catalogo_fontes.json').read_text(encoding='utf-8'))['acts']; records=[]
 if args.ids: registry=[a for a in registry if a['id'] in args.ids]
 elif not args.all:registry=[a for a in registry if a['source_verified']]
 if args.limit:registry=registry[:args.limit]
 for n,act in enumerate(registry,1):
  ident=act['id']; basename=slug(ident); url=act['official_url']
  print(f'[{n}/{len(registry)}] {ident}: {url}',flush=True)
  row={'id':ident,'source':url,'status':'not_attempted','timestamp':dt.datetime.now(dt.timezone.utc).isoformat()}
  try:
   folder=ROOT/'documentos_oficiais'/act['domain'];folder.mkdir(parents=True,exist_ok=True)
   body_file=folder/(basename+'.pdf' if urllib.parse.urlparse(url).path.lower().endswith('.pdf') else basename+'.html')
   typ='application/pdf' if body_file.suffix=='.pdf' else 'text/html'
   actual_url=url
   if args.overwrite or not body_file.exists():
    content,ctype,actual_url=download(url)
    if not content or len(content)<100: raise RuntimeError('Conteúdo vazio ou inesperadamente pequeno')
    if content.startswith(b'%PDF-'):typ='application/pdf'
    elif b'<html' in content[:10000].lower() or b'<!doctype' in content[:10000].lower():typ='text/html'
    else:raise RuntimeError('Resposta não parece PDF ou HTML (portal possivelmente dinâmico)')
    suffix='.pdf' if typ=='application/pdf' else '.html';body_file=folder/(basename+suffix)
    body_file.write_bytes(content)
   else:content=body_file.read_bytes();typ='application/pdf' if body_file.suffix=='.pdf' else 'text/html'
   hashval=hashlib.sha256(content).hexdigest()
   if typ=='application/pdf':
    pages=pdf_extract(content)
    text='\n\n'.join(f'\n[INICIO_PAGINA {i+1}]\n'+p+'\n[FIM_PAGINA {i+1}]\n' for i,p in enumerate(pages))
   else:pages=[];text=decode_html(content)
   text=normalize(text)
   if len(text)<450:raise RuntimeError('Extração insuficiente; verifique bloqueio/dinamismo ou digitalização')
   text_path=ROOT/'textos_extraidos'/act['domain']/(basename+'.txt');text_path.parent.mkdir(parents=True,exist_ok=True);text_path.write_text(text,encoding='utf-8')
   articles=split_articles(text)
   base={'schema':'okf.knowledge.v1','id':ident,'title':act['title'],'summary':'Documento oficial obtido integralmente em bytes e texto extraído automaticamente; revisão de consolidação e vigência jurídica pendente.',
    'elements':[{'id':ident+'#'+str(i),'type':'artigo_candidato','name':'Art. '+a['article'],'content':a['raw'],'attributes':{'automated_extraction':True,'char_start':a['char_start'],'char_end':a['char_end']}} for i,a in enumerate(articles,1)],
    'properties':[{'name':'jurisdiction','value':'BA' if act['domain']=='07_bahia' else 'BR'},{'name':'document_bytes_sha256','value':hashval}],
    'relations':[{'type':'subject','target':t} for t in act['subjects']], 'functions':[],
    'sources':[{'url':actual_url,'original_url':url,'authority':act['authority'],'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'sha256':hashval,'file':str(body_file.relative_to(ROOT)),'extracted_text':str(text_path.relative_to(ROOT)),'page_count':len(pages)}],
    'open_questions':['Validar vigência por artigo e efeitos diferidos; textos compilados podem conter redações revogadas ou programadas.','Conferir integridade da extração e limites dos artigos.'],
    'completeness':{'classification':'fonte_integral_capturada','full_source_bytes':True,'text_extracted':True,'article_count':len(articles),'legal_consolidation_verified':False},
    'compatibility':{'cognoscere_okf_version':'0.1','document_type':'source','status':'review'}}
   out=ROOT/'okf_compilados'/act['domain']/(basename+'.okf');jdump(base,out)
   row.update(status='extracted_automatic',sha256=hashval,bytes=len(content),text_chars=len(text),articles=len(articles),files=[str(body_file.relative_to(ROOT)),str(out.relative_to(ROOT))],url_final=actual_url)
  except Exception as e:row.update(status='failed',error=str(e));print('  ERRO:',e,flush=True)
  records.append(row);time.sleep(args.delay)
 report=ROOT/'relatorio_sincronizacao.json';previous=[]
 if report.exists():
  try:previous=json.loads(report.read_text(encoding='utf-8')).get('records',[])
  except Exception:pass
 byid={v['id']:v for v in previous};byid.update({v['id']:v for v in records});total=list(byid.values())
 counts=dict(collections.Counter(r['status'] for r in total))
 jdump({'run_at':dt.datetime.now(dt.timezone.utc).isoformat(),'attempted_this_run':len(records),'catalog_total':len(json.loads((ROOT/'catalogo_fontes.json').read_text())['acts']),'status_counts':counts,'records':total},report)
 print('Relatório:',report,' | estados:',counts,flush=True)
 if any(x['status']=='failed' for x in records):sys.exit(2)
if __name__=='__main__':main()
