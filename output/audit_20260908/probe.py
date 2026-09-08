"""Read-only project review probes; no online LLM calls or index rebuilds."""
import ast
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
os.environ.update(LLM_API_KEY='', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                  ANONYMIZED_TELEMETRY='False', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')

def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def timed(fn, n=5):
    samples = []
    result = None
    for _ in range(n):
        start = time.perf_counter()
        result = fn()
        samples.append(round((time.perf_counter() - start) * 1000, 3))
    return {'samples_ms': samples, 'median_ms': statistics.median(samples), 'max_ms': max(samples)}, result

def inventory():
    tracked = subprocess.check_output(['git','ls-files','-z'], cwd=ROOT).decode('utf-8').split('\0')
    files = []
    for rel in tracked:
        if not rel or not rel.startswith(('scripts/','tests/','web/src/','miniprogram/','deploy/')):
            continue
        path = ROOT / rel
        if path.suffix not in ('.py','.js','.ts','.tsx','.css','.wxss','.wxml','.md'):
            continue
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        row = {'path': rel, 'lines': len(text.splitlines()), 'sha256': hashlib.sha256(raw).hexdigest()}
        if path.suffix == '.py':
            tree = ast.parse(text)
            row['definitions'] = [{'name': n.name, 'line': n.lineno} for n in tree.body
                                  if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]
        files.append(row)
    save('inventory.json',files)
    reports = {}
    for name in ['final_reviewed','pipeline_result','answer_result','graph_result','eval_manifest']:
        data = json.loads((ROOT / 'output/eval' / (name+'.json')).read_text(encoding='utf-8'))
        reports[name] = {k:data[k] for k in ['summary','metadata','manifest_id','sets','generated_at'] if k in data}
    save('existing_evaluations.json', reports)
    snapshots = []
    for path in ROOT.glob('*.html'):
        text = path.read_text(encoding='utf-8')
        snapshots.append({'file':path.name, 'script_src':re.findall(r'<script[^>]+src=["\']([^"\']+)',text),
                          'stylesheet':re.findall(r'<link[^>]+href=["\']([^"\']+\.css[^"\']*)',text),
                          'markers': {word:len(re.findall(re.escape(word),text,re.I)) for word in
                                      ['canvas','video','gsap','swiper','webgl','three','clip-path','transform']}})
    save('official_snapshot.json',snapshots)

def graph_probe():
    from graph_search import GraphRetriever
    database = ROOT/'output/knowledge_graph/graph.db'
    con = sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    counts = {t:con.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['entities','relations','aliases']}
    indexes = con.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name='relations'").fetchall()
    con.close()
    cases = [json.loads(x) for x in (ROOT/'output/eval/graph_eval_set.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    rows=[]
    for case in cases:
        query = case['query']
        def once():
            start=time.perf_counter()
            r=GraphRetriever(str(database))
            load=(time.perf_counter()-start)*1000
            sql=[]
            r.con.set_trace_callback(sql.append)
            try:
                start=time.perf_counter()
                result=r.search(query)
                return {'load_ms':round(load,3),'search_ms':round((time.perf_counter()-start)*1000,3),
                        'sql_count':len(sql),'paths':len(result['paths']),
                        'entities':result['entities'], 'sources':result['hits'][:1]}
            finally:
                r.con.close()
        timing,result=timed(once)
        rows.append({'query':query,**timing,**result})
    save('graph_probe.json',{'counts':counts,'indexes':indexes,'cases':rows})

def rag_probe():
    import rag_ask
    rag_ask.llm.api_key = ''
    from unittest.mock import patch
    # Forbid all LLM calls even if a future implementation changes configuration lookup.
    with patch.object(rag_ask.llm,'chat',side_effect=AssertionError('online LLM disabled')), patch.object(rag_ask.llm,'chat_json',side_effect=AssertionError('online LLM disabled')):
        warm,_=timed(rag_ask.warm_index,n=1)
        retriever=rag_ask._get_retriever()
        rows=[]
        for query in ['重息壤是什么','莱万汀喜欢吃什么','陈千语和诀的关系']:
            channels={}
            for name,fn in [('bm25',lambda:retriever.bm25_search(query,20)),('vector',lambda:retriever.vector_search(query,20)),('name',lambda:retriever.name_search(query,10))]:
                channels[name],_=timed(fn,n=3)
            calls=[]
            real=retriever.search
            def record(q,**kw):
                calls.append(q)
                return real(q,**kw)
            with patch.object(retriever,'search',side_effect=record):
                total,result=timed(lambda:rag_ask.ask(query,gen_answer_=False),n=1)
            rows.append({'query':query,'channels':channels,'offline_pipeline':total,
                         'retrieval_calls':calls,'route':result.get('route_used'),
                         'hit_count':len(result.get('hits',[]))})
        save('rag_probe.json',{'warm':warm,'note':'Offline fallback planner; timings are not production LLM/TTFT measurements. Channel order fixed, n=3.','cases':rows})

def tests():
    tasks=[('backend',['-m','unittest','discover','-s','tests','-v']),
           ('security_stream_trace',['-m','unittest','scripts.test_query_routes','scripts.test_api_security','scripts.test_rag_trace','scripts.test_ask_stream','-v']),
           ('quality_gate',['scripts/quality_gate.py'])]
    rows=[]
    for name,args in tasks:
        started=time.perf_counter()
        with (OUT/(name+'.log')).open('w',encoding='utf-8') as log:
            p=subprocess.run([sys.executable,*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy())
        rows.append({'name':name,'returncode':p.returncode,'seconds':round(time.perf_counter()-started,2)})
        save('test_status.json',rows)

def correctness():
    from unittest.mock import MagicMock, patch
    import rag_ask
    from llm_client import LLMClient
    import httpx
    from scripts import api_server
    from fastapi.testclient import TestClient
    rows = {'entity_resolution': []}
    for q in ['重息壤是什么','诀的信物是什么','陈千语和诀的关系']:
        rows['entity_resolution'].append({'query':q,'entity':rag_ask.extract_kb_entity(q)[0]})
    client=LLMClient()
    client.api_key='offline-test-placeholder'
    response=MagicMock()
    response.status_code=200
    response.iter_lines.return_value=iter(['data: '+json.dumps({'choices':[{'delta':{'content':'partial answer'}}]})])
    mock_client=MagicMock()
    mock_client.__enter__.return_value.stream.return_value.__enter__.return_value=response
    with patch('llm_client.httpx.Client',return_value=mock_client):
        rows['stream_without_finish']={'returned':' '.join(client.chat_stream('offline fixture')), 'raised':False}
    from contextlib import contextmanager
    @contextmanager
    def fake_media(*args,**kwargs):
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,
                headers={'content-type':'image/svg+xml'},stream=httpx.ByteStream(b'<svg xmlns="http://www.w3.org/2000/svg"><title>benign fixture</title></svg>')))) as upstream:
            with upstream.stream('GET','https://bbs.hycdn.cn/image/audit-fixture.svg') as response:
                yield response
    with patch('httpx.stream',fake_media), TestClient(api_server.app) as local:
        r=local.get('/api/media',params={'url':'https://bbs.hycdn.cn/image/audit-fixture.svg'})
        rows['svg_media_policy']={'status':r.status_code,'content_type':r.headers.get('content-type'),
                                  'csp':r.headers.get('content-security-policy'),
                                  'content_disposition':r.headers.get('content-disposition'),
                                  'note':'Benign mocked upstream; demonstrates policy only, no live CDN exploit.'}
        r=local.get('/api/synthesis',params={'item':'not-an-item','max_depth':100000})
        rows['unbounded_depth']={'http_status':r.status_code,'note':'Validation accepts 100000; no expensive tree requested.'}
    save('correctness_probe.json',rows)

if __name__=='__main__':
    mode=sys.argv[1]
    {'inventory':inventory,'graph':graph_probe,'rag':rag_probe,'tests':tests,'correctness':correctness}[mode]()
