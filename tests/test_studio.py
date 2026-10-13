import sys,time, tempfile,os,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
datadir=Path(tempfile.mkdtemp(prefix='ai-film-factory-test-'))
os.environ['AI_FILM_DATA']=str(datadir)
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app) as t:
 def need(r):
  assert r.status_code<300,(r.status_code,r.text[:500]);return r.json()
 health=need(t.get('/api/health')); assert health['credits_used']==0
 chars=need(t.get('/api/characters'));assert len(chars)>=2
 extra=need(t.post('/api/characters',json={'name':'Khải','role':'CEO','costume':'Vest xám','voice':'Nam trung niên'}))
 assert extra['id'].startswith('CHAR_')
 edited=need(t.patch('/api/characters/'+extra['id'],json={'name':'Khải','role':'CEO','costume':'Vest xám đậm','voice':'Nam trầm'}));assert edited['costume']=='Vest xám đậm'
 project=need(t.post('/api/projects',json={'title':'Test 8 min','story':'Một cô lao công tên Mai phát hiện điều khoản bí mật trong hợp đồng 50 tỷ. Cô cứu công ty khỏi một vụ lừa đảo hợp đồng.','minutes':8}))
 pid=project['id'];assert len(project['shots'])==60;assert sum(s['duration_seconds'] for s in project['shots'])==480
 sh=project['shots'][0];sh_edit={k:sh[k] for k in ['title','action','dialogue','speaker','camera','image_prompt','video_prompt','characters','location']};sh_edit['title']='Cảnh mở đầu đã chỉnh';need(t.patch(f'/api/projects/{pid}/shots/{sh["id"]}',json=sh_edit));assert need(t.get(f'/api/projects/{pid}'))['shots'][0]['title']=='Cảnh mở đầu đã chỉnh'
 graph=need(t.get(f'/api/projects/{pid}/graph'));assert len(graph['nodes'])==9
 need(t.put(f'/api/projects/{pid}/graph',json=graph)); order=need(t.get(f'/api/projects/{pid}/graph/check'))['order'];assert len(order)==9
 # cycle is forbidden
 bad=dict(graph);bad['edges']=graph['edges']+[{'id':'bad-edge','source':'render','target':'story'}]
 r=t.put(f'/api/projects/{pid}/graph',json=bad);assert r.status_code==422,r.text
 assert [n['id'] for n in need(t.get(f'/api/projects/{pid}/graph'))['nodes']]==[n['id'] for n in graph['nodes']]
 need(t.put(f'/api/projects/{pid}',json={'title':'Test renamed','story':project['story']+' Thêm tình tiết.','minutes':8,'regenerate':False}))
 need(t.put(f'/api/projects/{pid}',json={'title':'Test renamed','story':project['story'],'minutes':8,'regenerate':True}))
 r=t.get(f'/api/projects/{pid}/graph/export');assert r.status_code==200
 job=need(t.post(f'/api/projects/{pid}/run',json={'preview_seconds':16}));jid=job['id']
 for i in range(180):
  job=need(t.get('/api/jobs/'+jid))
  if job['status'] in ('complete','failed'):break
  time.sleep(.2)
 assert job['status']=='complete',job
 arts=need(t.get(f'/api/projects/{pid}/artifacts'))
 assert any(x['name']=='preview.mp4' for x in arts)
 mp4=datadir/'projects'/pid/'preview.mp4';assert mp4.exists() and mp4.stat().st_size>4000
 print('TEST PASSED: chars, CRUD, 60 shots / 480s, shot edit, workflow CRUD, DAG cycle rejection, mock rendering',mp4.stat().st_size,'bytes',len(arts),'files',len(job['logs']),'logs')
