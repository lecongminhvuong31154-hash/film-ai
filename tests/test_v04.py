"""V0.4 no-credit integration tests; no external HTTP or paid AI calls."""
import os,sys,time,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['AI_FILM_DATA']=tempfile.mkdtemp(prefix='film-v04-no-credit-')
os.environ.pop('OPENAI_API_KEY',None)
from fastapi.testclient import TestClient
from backend.main import app
from backend import ai_writer


def fake_call(messages,max_tokens):
    text=messages[-1]['content']
    if 'dàn ý phim' in text:
        return {'characters':[{'name':'Mai','role':'Lao công','costume':'Đồng phục xanh','voice':'Nữ miền Nam'}, {'name':'Tuấn','role':'Phó giám đốc','costume':'Vest xanh','voice':'Nam trung'}],
                'locations':['Phòng họp','Hành lang'],
                'beats':[{'title':'Nhịp '+str(i),'summary':'Tình tiết '+str(i),'twist_or_clue':'Manh mối '+str(i)} for i in range(8)]}
    import json
    requested=json.loads(text.split('DỮ LIỆU:\n',1)[-1])['requested_shots']
    return {'shots':[{'id':m['id'],'title':'Cảnh '+str(m['id']),'action':'Mai xem tài liệu, Tuấn bước vào và câu chuyện tiếp tục.',
                      'location':'Phòng họp','camera':'medium shot','dialogue':'Hãy kiểm tra lại hợp đồng!',
                      'speaker':'CAST_MAI','characters':['CAST_MAI','CAST_TU_N'],
                      'image_prompt':'Film frame: characters in boardroom, cinematic, 9:16, no text.',
                      'video_prompt':'Animate the boardroom image with a subtle dolly-in, same costumes.'} for m in requested]}

with TestClient(app) as c:
    demo=c.post('/api/projects',json={'title':'Lao công','story':'Mai là một cô lao công. Cô phát hiện hợp đồng 50 tỷ và đưa ra cảnh báo quan trọng.','minutes':8})
    assert demo.status_code==201,demo.text
    p1=demo.json()['id']
    assert len(c.get('/api/projects/'+p1+'/characters').json())==2
    other=c.post('/api/projects',json={'title':'Đồng hồ bí ẩn','story':'Một người trẻ bắt gặp chiếc đồng hồ có thể dự báo những tình huống kỳ lạ.','minutes':8})
    assert other.status_code==201,other.text
    p2=other.json()['id']
    assert c.get('/api/projects/'+p2+'/characters').json()==[]
    add=c.post('/api/projects/'+p2+'/characters',json={'name':'An','role':'Nhân vật chính','costume':'Áo khoác','voice':'Nữ trẻ'})
    assert add.status_code==201,add.text
    cid=add.json()['id']
    edited=c.patch('/api/projects/'+p2+'/characters/'+cid,json={'name':'An','role':'Thám tử','costume':'Áo đỏ','voice':'Nữ trẻ'})
    assert edited.status_code==200 and edited.json()['costume']=='Áo đỏ'
    assert all(x['name']!='An' for x in c.get('/api/projects/'+p1+'/characters').json())
    assert c.get('/api/ai-writer/status').json()['available'] is False
    r=c.post('/api/projects/'+p1+'/ai-script')
    assert r.status_code==503,r.text
    assert c.post('/api/projects/'+p1+'/approve-script').status_code==409
    plan,shots=ai_writer.generate_shots(demo.json()['story'],8,call=fake_call)
    assert len(shots)==60 and sum(x['duration_seconds'] for x in shots)==480
    assert all(x['title'].startswith('Cảnh') for x in shots)
    assert len(plan['beats'])==8
    # Fake provider for testing the full async job path and server-side approval.
    old=ai_writer.generate_shots
    old_available=ai_writer.available
    try:
        ai_writer.generate_shots=lambda story,minutes,progress=None:(plan,shots)
        ai_writer.available=lambda:True
        res=c.post('/api/projects/'+p1+'/ai-script')
        assert res.status_code==202,res.text
        for _ in range(50):
            j=c.get('/api/projects/'+p1+'/ai-job').json()
            if j['status'] in ('complete','failed'):break
            time.sleep(.08)
        assert j['status']=='complete',j
        proj=c.get('/api/projects/'+p1).json()
        assert proj['script_status']=='ai_draft',proj['script_status']
        assert len(proj['shots'])==60 and proj['shots'][-1]['id']=='SC060'
        assert len(proj['characters'])==2
        approved=c.post('/api/projects/'+p1+'/approve-script')
        assert approved.status_code==200 and approved.json()['script_status']=='approved'
        assert c.get('/api/projects/'+p2+'/characters').json()[0]['name']=='An'
        assert c.get('/api/projects/'+p1+'/jobs').json() is None
        from io import BytesIO
        from zipfile import ZipFile
        backup=c.get('/api/projects/'+p1+'/backup')
        assert backup.status_code==200
        with ZipFile(BytesIO(backup.content)) as z:
            assert 'project.json' in z.namelist()
            assert 'files/shots.json' in z.namelist()
            assert 'files/script_outline.json' in z.namelist()
    finally:
        ai_writer.generate_shots=old
        ai_writer.available=old_available
print('TEST PASSED: isolated per-project characters; 503 no-key; 60 detailed AI shots mock; background job; approval; no external calls')
