"""AI Film Factory V0.4: opt-in AI screenplay, per-project characters, safe mock render."""
import json
import os
import re
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from .db import DATA, ROOT, connect, init_db
from .story_engine import CHARACTER_DEFAULTS, STORY_DEMO, build_shots, make_workflow_plan
from .render import preview_card, render_clip, concat_clips, create_subtitles
from .workflows import default_graph, validate_graph, execution_order, CAPABILITIES
from .security import PasswordGate, router as security_router
from . import ai_writer

app = FastAPI(title="AI Film Factory — Web Studio", version="0.4.0", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(security_router)
app.add_middleware(PasswordGate)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_methods=["*"],allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="film-mock")
state_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def jd(value):
    return json.dumps(value, ensure_ascii=False)


def read_project(pid):
    with connect() as db:
        row=db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if row is None:
        raise HTTPException(404,"Không tìm thấy dự án")
    obj=dict(row)
    obj['characters']=project_character_records(pid)
    obj['shots']=json.loads(obj['shots'])
    return obj


def read_job(jid):
    with connect() as db:
        row=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
        logs=db.execute('SELECT created,level,message FROM logs WHERE job_id=? ORDER BY id DESC LIMIT 50',(jid,)).fetchall()
    if not row:
        raise HTTPException(404,"Không tìm thấy tác vụ")
    obj=dict(row)
    obj['logs']=[dict(x) for x in reversed(logs)]
    return obj


def log(jid, message, level='info'):
    with connect() as db:
        db.execute('INSERT INTO logs(job_id,created,level,message) VALUES(?,?,?,?)',(jid,now(),level,message))


def step(jid, stage, current=None, total=None, status=None, error=None):
    fields=['step=?','updated=?']; values=[stage,now()]
    if current is not None:fields.append('current=?');values.append(current)
    if total is not None:fields.append('total=?');values.append(total)
    if status is not None:fields.append('status=?');values.append(status)
    if error is not None:fields.append('error=?');values.append(error)
    values.append(jid)
    with connect() as db:
        db.execute('UPDATE jobs SET '+','.join(fields)+' WHERE id=?',values)


def project_dir(pid):
    path=DATA/'projects'/pid
    path.mkdir(parents=True,exist_ok=True)
    return path


def url_for_file(f:Path):
    return '/media/'+f.resolve().relative_to(DATA.resolve()).as_posix()


def project_character_records(pid:str, ensure=True):
    """Per-film characters. On first access, migrate old V0.3 snapshots."""
    if ensure:
        with connect() as db:
            count=db.execute('SELECT COUNT(*) AS n FROM project_characters WHERE project_id=?',(pid,)).fetchone()['n']
            p=db.execute('SELECT characters FROM projects WHERE id=?',(pid,)).fetchone()
        if not p:raise HTTPException(404,'Dự án không tồn tại')
        if not count:
            try:previous=json.loads(p['characters'])
            except (ValueError,TypeError):previous=[]
            for c in previous:
                if isinstance(c,dict) and c.get('id') and c.get('name'):
                    upsert_project_character(pid,c,copy_global=True)
    with connect() as db:
        rows=db.execute('SELECT * FROM project_characters WHERE project_id=? ORDER BY created,id',(pid,)).fetchall()
    chars=[]
    for raw in rows:
        c=dict(raw)
        filename=c.pop('image_filename')
        c.pop('project_id',None)
        dest=project_dir(pid)/'characters'/(filename or 'missing.png')
        c['image_url']=(url_for_file(dest)+'?v='+str(dest.stat().st_mtime_ns)) if filename and dest.is_file() else None
        chars.append(c)
    return chars


def sync_project_cast(pid):
    with connect() as db:
        db.execute('UPDATE projects SET characters=?,updated=? WHERE id=?',
                   (jd(project_character_records(pid,False)),now(),pid))


def upsert_project_character(pid,c,copy_global=False):
    """No cross-film shared mutations; images are copied into film-specific storage."""
    cid=str(c.get('id',''))[:64]
    if not cid or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',cid):
        raise HTTPException(400,'ID nhân vật không hợp lệ')
    targetdir=project_dir(pid)/'characters';targetdir.mkdir(exist_ok=True)
    filename=None
    with connect() as db:
        old=db.execute('SELECT image_filename FROM project_characters WHERE project_id=? AND id=?',(pid,cid)).fetchone()
        if old:filename=old['image_filename']
    if not filename and copy_global:
        source=DATA/'characters'/f'{cid}_REF.png'
        if source.is_file():
            filename=f'{cid}_REF.png'
            shutil.copy2(source,targetdir/filename)
    with connect() as db:
        db.execute("""INSERT INTO project_characters(project_id,id,name,role,costume,voice,image_filename,created)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(project_id,id) DO UPDATE SET
            name=excluded.name,role=excluded.role,costume=excluded.costume,voice=excluded.voice,image_filename=COALESCE(project_characters.image_filename,excluded.image_filename)""",
            (pid,cid,str(c.get('name',''))[:90],str(c.get('role',''))[:160],str(c.get('costume',''))[:300],str(c.get('voice',''))[:240],filename,now()))


def replace_ai_cast(pid,cast):
    """Preserve user-selected character portraits by name, without crossing project boundaries."""
    previous=project_character_records(pid)
    old_by_name={c['name'].casefold():c for c in previous}
    new_ids=set()
    for c in cast:
        new_ids.add(c['id'])
        matched=old_by_name.get(c['name'].casefold())
        upsert_project_character(pid,c)
        if matched and matched.get('image_url'):
            src=project_dir(pid)/'characters'/f"{matched['id']}_REF.png"
            # Also support any user-uploaded filename.
            with connect() as db:
                row=db.execute('SELECT image_filename FROM project_characters WHERE project_id=? AND id=?',(pid,matched['id'])).fetchone()
            if row and row['image_filename']:
                src=project_dir(pid)/'characters'/row['image_filename']
            dest=project_dir(pid)/'characters'/f"{c['id']}_REF.png"
            if src.is_file() and src.resolve()!=dest.resolve():shutil.copy2(src,dest)
            if dest.is_file():
                with connect() as db:
                    db.execute('UPDATE project_characters SET image_filename=? WHERE project_id=? AND id=?',(dest.name,pid,c['id']))
    with connect() as db:
        db.execute('DELETE FROM project_characters WHERE project_id=? AND id NOT IN ('+(','.join(['?']*len(new_ids)))+')', (pid,*new_ids))
    sync_project_cast(pid)


def seed_characters():
    folder=DATA/'characters';folder.mkdir(exist_ok=True)
    paths={'MAI':ROOT/'assets'/'MAI_REF.png','TUAN':ROOT/'assets'/'TUAN_REF.png'}
    for label,path in paths.items():
        target=folder/(label+'_REF.png')
        if path.exists() and not target.exists():shutil.copy2(path,target)
    return folder


@app.on_event('startup')
def setup():
    init_db()
    seed_characters()
    seed_character_library()


class NewProject(BaseModel):
    title:str=Field(default="Cô lao công và bản hợp đồng 50 tỷ",min_length=1,max_length=140)
    story:str=Field(default=STORY_DEMO,min_length=10,max_length=25000)
    minutes:int=Field(default=8,ge=1,le=15)


@app.get('/api/health')
def health():
    return {"ok":True,"mode":"mock-preview+optional-ai-writer","provider":"OpenAI (optional)","credits_used":None if ai_writer.available() else 0,"usage_note":"Chỉ đo mô phỏng; token phí API do nhà cung cấp tính","ffmpeg":"available on render","version":"0.4.0"}


@app.get('/api/demo-story')
def demo_story():
    return {'story':STORY_DEMO}


def seed_character_library():
    seed_characters()
    defaults = {c['id']:c for c in CHARACTER_DEFAULTS}
    with connect() as db:
        for cid,c in defaults.items():
            db.execute('INSERT OR IGNORE INTO character_library(id,name,role,costume,voice,image_filename,created) VALUES(?,?,?,?,?,?,?)',
                       (cid,c['name'],c['role'],c['costume'],c['voice'],cid+'_REF.png',now()))


def character_records():
    seed_character_library()
    with connect() as db:
        rows=db.execute('SELECT * FROM character_library ORDER BY CASE WHEN id="MAI" THEN 0 WHEN id="TUAN" THEN 1 ELSE 2 END,name').fetchall()
    ret=[]
    for row in rows:
        c=dict(row)
        filename=c.pop('image_filename')
        c['image_url']=url_for_file(DATA/'characters'/filename)+'?v='+str((DATA/'characters'/filename).stat().st_mtime_ns) if filename and (DATA/'characters'/filename).exists() else None
        ret.append(c)
    return ret


@app.get('/api/characters')
def characters():
    return character_records()


class CharacterCreate(BaseModel):
    name:str=Field(min_length=1,max_length=90)
    role:str=Field(default='Nhân vật',max_length=160)
    costume:str=Field(default='',max_length=300)
    voice:str=Field(default='',max_length=240)


@app.post('/api/characters',status_code=201)
def create_character(payload:CharacterCreate):
    cid='CHAR_'+uuid.uuid4().hex[:8].upper()
    with connect() as db:
        db.execute('INSERT INTO character_library(id,name,role,costume,voice,created) VALUES(?,?,?,?,?,?)',
                   (cid,payload.name.strip(),payload.role.strip(),payload.costume.strip(),payload.voice.strip(),now()))
    return next(c for c in character_records() if c['id']==cid)


@app.patch('/api/characters/{character_id}')
def edit_character(character_id:str,payload:CharacterCreate):
    with connect() as db:
        cur=db.execute('UPDATE character_library SET name=?,role=?,costume=?,voice=? WHERE id=?',
                       (payload.name.strip(),payload.role.strip(),payload.costume.strip(),payload.voice.strip(),character_id))
        if cur.rowcount==0: raise HTTPException(404,'Không thấy nhân vật')
    return next(c for c in character_records() if c['id']==character_id)


@app.post('/api/characters/{character_id}/image')
async def update_character_image(character_id:str,file:UploadFile=File(...)):
    with connect() as db:
        row=db.execute('SELECT id FROM character_library WHERE id=?',(character_id,)).fetchone()
    if not row:raise HTTPException(404,'Không tìm thấy nhân vật')
    if file.content_type not in ('image/png','image/jpeg','image/webp'):
        raise HTTPException(400,'Chỉ nhận PNG, JPEG hoặc WEBP')
    blob=await file.read(8*1024*1024+1)
    if len(blob)>8*1024*1024:raise HTTPException(413,'Giới hạn ảnh 8 MB')
    try:
        from PIL import Image, ImageOps
        from io import BytesIO
        img=Image.open(BytesIO(blob));img.verify()
        img=ImageOps.exif_transpose(Image.open(BytesIO(blob))).convert('RGB')
        if img.width*img.height > 30000000: raise ValueError('Ảnh quá lớn')
        dest=DATA/'characters'/f'{character_id}_REF.png'
        img.save(dest,'PNG')
        with connect() as db:
            db.execute('UPDATE character_library SET image_filename=? WHERE id=?',(dest.name,character_id))
    except Exception as exc:
        raise HTTPException(400,'Không đọc được ảnh hợp lệ') from exc
    return {'ok':True,'image_url':url_for_file(dest)}



@app.get('/api/projects/{project_id}/characters')
def get_project_characters(project_id:str):
    read_project(project_id)
    return project_character_records(project_id)


@app.post('/api/projects/{project_id}/characters',status_code=201)
def add_project_character(project_id:str,payload:CharacterCreate):
    read_project(project_id)
    cid='CHAR_'+uuid.uuid4().hex[:8].upper()
    upsert_project_character(project_id,{'id':cid,**payload.model_dump()})
    sync_project_cast(project_id)
    return next(c for c in project_character_records(project_id) if c['id']==cid)


@app.patch('/api/projects/{project_id}/characters/{character_id}')
def edit_project_character(project_id:str,character_id:str,payload:CharacterCreate):
    read_project(project_id)
    if not any(c['id']==character_id for c in project_character_records(project_id)):
        raise HTTPException(404,'Nhân vật không nằm trong dự án')
    upsert_project_character(project_id,{'id':character_id,**payload.model_dump()})
    sync_project_cast(project_id)
    return next(c for c in project_character_records(project_id) if c['id']==character_id)


@app.post('/api/projects/{project_id}/characters/{character_id}/image')
async def upload_project_character_image(project_id:str,character_id:str,file:UploadFile=File(...)):
    read_project(project_id)
    if not any(c['id']==character_id for c in project_character_records(project_id)):
        raise HTTPException(404,'Nhân vật không thuộc dự án')
    if file.content_type not in ('image/png','image/jpeg','image/webp'):
        raise HTTPException(400,'Chỉ cho phép PNG/JPEG/WEBP')
    blob=await file.read(8*1024*1024+1)
    if len(blob)>8*1024*1024:raise HTTPException(413,'Ảnh vượt quá 8 MB')
    try:
        from PIL import Image, ImageOps
        from io import BytesIO
        obj=Image.open(BytesIO(blob));obj.verify()
        obj=ImageOps.exif_transpose(Image.open(BytesIO(blob))).convert('RGB')
        if obj.width*obj.height>30000000:raise ValueError('Ảnh quá lớn')
        destdir=project_dir(project_id)/'characters';destdir.mkdir(exist_ok=True)
        dest=destdir/f'{character_id}_REF.png'
        obj.save(dest,'PNG')
    except Exception as exc:
        raise HTTPException(400,'Không đọc được ảnh hợp lệ') from exc
    with connect() as db:
        db.execute('UPDATE project_characters SET image_filename=? WHERE project_id=? AND id=?',
                   (dest.name,project_id,character_id))
    sync_project_cast(project_id)
    return {'ok':True,'image_url':url_for_file(dest)}


@app.get('/api/projects')
def projects():
    with connect() as db:
        rows=db.execute('SELECT id,title,minutes,created,status,final_video FROM projects ORDER BY created DESC LIMIT 60').fetchall()
    return [dict(r) for r in rows]


@app.post('/api/projects',status_code=201)
def create_project(payload:NewProject):
    pid='film_'+uuid.uuid4().hex[:12]
    shots=build_shots(payload.story,payload.minutes)
    is_demo=('lao công' in payload.story.lower() and ('hợp đồng' in payload.story.lower() or '50 tỷ' in payload.story.lower()))
    chars=character_records()[:2] if is_demo else []
    moment=now()
    with connect() as db:
        db.execute('INSERT INTO projects (id,title,story,minutes,created,updated,status,characters,shots) VALUES(?,?,?,?,?,?,?,?,?)',
                   (pid,payload.title.strip(),payload.story.strip(),payload.minutes,moment,moment,'planned',jd(chars),jd(shots)))
    pd=project_dir(pid)
    for character in chars:
        upsert_project_character(pid, character, copy_global=True)
    (pd/'shots.json').write_text(jd(shots),encoding='utf-8')
    (pd/'story.txt').write_text(payload.story,encoding='utf-8')
    return read_project(pid)


@app.get('/api/projects/{project_id}')
def get_project(project_id:str):
    return read_project(project_id)


@app.get('/api/projects/{project_id}/workflow')
def get_workflow(project_id:str):
    project=read_project(project_id)
    return make_workflow_plan(project_id,project['shots'],project['characters'])


@app.get('/api/projects/{project_id}/workflow/download')
def download_workflow(project_id:str):
    project=read_project(project_id)
    dest=project_dir(project_id)/'tobyflow_blueprint_NOT_IMPORTABLE.json'
    dest.write_text(json.dumps(make_workflow_plan(project_id,project['shots'],project['characters']),ensure_ascii=False,indent=2),encoding='utf-8')
    return FileResponse(dest,filename=dest.name,media_type='application/json')


@app.get('/api/projects/{project_id}/backup')
def backup_project(project_id:str):
    """Download a portable snapshot; important on ephemeral Render Free."""
    obj=read_project(project_id)
    basedir=project_dir(project_id)
    backupdir=DATA/'backups';backupdir.mkdir(exist_ok=True)
    dest=backupdir/(project_id+'_backup.zip')
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as archive:
        archive.writestr('project.json',json.dumps(obj,ensure_ascii=False,indent=2))
        for src in basedir.rglob('*'):
            if src.is_file() and src.resolve().is_relative_to(basedir.resolve()):
                archive.write(src,'files/'+src.relative_to(basedir).as_posix())
    return FileResponse(dest,filename=dest.name,media_type='application/zip')


@app.get('/api/projects/{project_id}/shots/download')
def download_shots(project_id:str):
    read_project(project_id)
    return FileResponse(project_dir(project_id)/'shots.json',filename='shots.json',media_type='application/json')


class ProjectUpdate(BaseModel):
    title:str=Field(min_length=1,max_length=140)
    story:str=Field(min_length=10,max_length=25000)
    minutes:int=Field(ge=1,le=15)
    regenerate:bool=False


@app.put('/api/projects/{project_id}')
def update_project(project_id:str,payload:ProjectUpdate):
    p=read_project(project_id)
    shots=build_shots(payload.story,payload.minutes) if payload.regenerate else p['shots']
    if not payload.regenerate and sum(sh['duration_seconds'] for sh in shots)!=payload.minutes*60:
        raise HTTPException(400,'Nếu thay đổi thời lượng, hãy chọn tạo lại storyboard')
    with connect() as db:
        db.execute('UPDATE projects SET title=?,story=?,minutes=?,shots=?,updated=?,status=?,script_status=? WHERE id=?',
                   (payload.title.strip(),payload.story.strip(),payload.minutes,jd(shots),now(),'planned','mock' if payload.regenerate else 'edited',project_id))
    (project_dir(project_id)/'story.txt').write_text(payload.story.strip(),encoding='utf-8')
    (project_dir(project_id)/'shots.json').write_text(jd(shots),encoding='utf-8')
    return read_project(project_id)


class ShotUpdate(BaseModel):
    title:str=Field(min_length=1,max_length=140)
    action:str=Field(min_length=1,max_length=1200)
    dialogue:str=Field(default='',max_length=1500)
    speaker:str|None=None
    camera:str=Field(default='medium shot',max_length=150)
    image_prompt:str=Field(default='',max_length=3500)
    video_prompt:str=Field(default='',max_length=3500)
    characters:list[str]=Field(default_factory=list,max_length=10)
    location:str=Field(default='',max_length=200)


@app.patch('/api/projects/{project_id}/shots/{shot_id}')
def update_shot(project_id:str,shot_id:str,payload:ShotUpdate):
    project=read_project(project_id)
    shots=project['shots']
    target=next((sh for sh in shots if sh['id']==shot_id),None)
    if target is None:raise HTTPException(404,'Không tìm thấy shot')
    available={c['id'] for c in project_character_records(project_id)}
    if any(cid not in available for cid in payload.characters):
        raise HTTPException(400,'Shot có nhân vật chưa tồn tại trong thư viện')
    if payload.speaker and payload.speaker not in available:
        raise HTTPException(400,'Người nói chưa tồn tại trong thư viện')
    target.update(payload.model_dump())
    with connect() as db:
        db.execute('UPDATE projects SET shots=?,status=?,updated=? WHERE id=?',(jd(shots),'planned',now(),project_id))
    (project_dir(project_id)/'shots.json').write_text(jd(shots),encoding='utf-8')
    return target


def get_graph(project_id):
    project=read_project(project_id)
    with connect() as db:
        row=db.execute('SELECT data FROM project_workflows WHERE project_id=?',(project_id,)).fetchone()
    return json.loads(row['data']) if row else default_graph(project)


@app.get('/api/projects/{project_id}/graph')
def read_graph(project_id:str):
    return get_graph(project_id)


@app.put('/api/projects/{project_id}/graph')
def save_graph(project_id:str,payload:dict):
    read_project(project_id)
    try: graph=validate_graph(payload)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    with connect() as db:
        db.execute('INSERT INTO project_workflows(project_id,data,updated) VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET data=excluded.data,updated=excluded.updated',
                   (project_id,jd(graph),now()))
    return {'ok':True,'graph':graph,'node_count':len(graph['nodes'])}


@app.post('/api/projects/{project_id}/graph/reset')
def reset_graph(project_id:str):
    graph=default_graph(read_project(project_id))
    with connect() as db:
        db.execute('DELETE FROM project_workflows WHERE project_id=?',(project_id,))
    return graph


@app.get('/api/projects/{project_id}/graph/export')
def export_graph(project_id:str):
    graph=get_graph(project_id)
    dest=project_dir(project_id)/'node_workflow_mock_NOT_TOBYFLOW.json'
    dest.write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
    return FileResponse(dest,filename=dest.name,media_type='application/json')


@app.get('/api/node-types')
def node_types():
    return [{'type':k,'description':v,'mock':True} for k,v in CAPABILITIES.items()]


@app.get('/api/projects/{project_id}/graph/check')
def check_graph(project_id:str):
    graph=get_graph(project_id)
    try: graph=validate_graph(graph)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    order=execution_order(graph)
    node_map={n['id']:n for n in graph['nodes']}
    return {'ok':True,'order':[{'id':nid,'type':node_map[nid]['type'],'label':node_map[nid]['data']['label']} for nid in order],
            'notice':'Kiểm tra DAG, không tạo ảnh/video AI hoặc gọi TobyFlow thật.'}


def demo_render_job(jid:str, pid:str, max_seconds:int):
    try:
        step(jid,'story',status='running')
        log(jid,'Bắt đầu pipeline giả lập, KHÔNG gọi AI trả phí. Credit tiêu thụ: 0.')
        graph=validate_graph(get_graph(pid))
        order=execution_order(graph)
        for nid in order:
            node=next(n for n in graph['nodes'] if n['id']==nid)
            log(jid,f"Node {nid} [{node['type']}]: {node['data']['label']} — mô phỏng DAG")
        project=read_project(pid)
        selected=[]
        remaining=max_seconds
        for shot in project['shots']:
            if remaining<=0:break
            take=min(shot['duration_seconds'],remaining)
            selected.append({**shot,'duration_seconds':take})
            remaining-=take
        folder=project_dir(pid)
        images=folder/'images';clips=folder/'clips'
        images.mkdir(exist_ok=True);clips.mkdir(exist_ok=True)
        with connect() as db:
            rows=db.execute('SELECT id,image_filename FROM project_characters WHERE project_id=?',(pid,)).fetchall()
        char_paths={c['id']: project_dir(pid)/'characters'/(c['image_filename'] or 'missing.png') for c in rows}
        step(jid,'characters',current=0,total=len(selected))
        log(jid,'Đã tải kho nhân vật vào tiến trình mô phỏng.')
        clip_files=[]
        for i,shot in enumerate(selected):
            step(jid,f'image:{shot["id"]}',current=i)
            jpg=images/(shot['id']+'.jpg')
            preview_card(shot,char_paths,jpg,project['title'])
            log(jid,f'{shot["id"]}: đã tạo ảnh storyboard mô phỏng.')
            step(jid,f'video:{shot["id"]}',current=i)
            mp4=clips/(shot['id']+'.mp4')
            render_clip(jpg,shot['duration_seconds'],mp4)
            clip_files.append(mp4)
            step(jid,'render',current=i+1)
            log(jid,f'{shot["id"]}: clip MP4 {shot["duration_seconds"]}s đã xuất bằng FFmpeg.')
        step(jid,'voice_mock')
        log(jid,'VOICE MOCK: tạo phụ đề SRT, âm thanh là track im lặng; KHÔNG phải giọng AI Việt thật.')
        create_subtitles(selected,folder/'preview_subtitles.srt')
        step(jid,'concat')
        dest=folder/'preview.mp4'
        concat_clips(clip_files,dest,sum(s['duration_seconds'] for s in selected))
        if not dest.is_file() or dest.stat().st_size < 2000:raise RuntimeError('Video xuất ra rỗng')
        with connect() as db:
            db.execute('UPDATE projects SET final_video=?,status=?,updated=? WHERE id=?',
                       (url_for_file(dest),'preview_ready',now(),pid))
        step(jid,'complete',current=len(selected),status='complete')
        log(jid,f'Đã tạo MP4 preview {sum(s["duration_seconds"] for s in selected)}s và SRT. Credit: 0.','success')
    except Exception as exc:
        step(jid,'failed',status='failed',error=str(exc)[:1000])
        log(jid,'Lỗi: '+str(exc)[:500],'error')



@app.get('/api/ai-writer/status')
def writer_status():
    return ai_writer.config()


def ai_write_job(jid:str,pid:str):
    """Background optional paid call. Save results only when every generated shot validates."""
    try:
        step(jid,'ai_outline',status='running')
        project=read_project(pid)
        log(jid,'Đang lập kịch bản qua API đã cấu hình; chỉ lưu sau khi hoàn tất mọi shot.')
        def on_progress(stage,done,total):
            step(jid,'ai_'+stage,current=done,total=total)
            log(jid,f'AI biên kịch: {stage} ({done}/{total})')
        plan,shots=ai_writer.generate_shots(project['story'],project['minutes'],progress=on_progress)
        # Do not replace newer user edits made during this background operation.
        with connect() as db:
            current=db.execute('SELECT story,minutes FROM projects WHERE id=?',(pid,)).fetchone()
        if not current or current['story'] != project['story'] or current['minutes'] != project['minutes']:
            raise ai_writer.WriterError('Cốt truyện đã thay đổi khi AI đang viết. Kết quả cũ không được ghi đè.')
        # Commit once the generated plan has passed validation.
        replace_ai_cast(pid,plan['characters'])
        with connect() as db:
            db.execute('UPDATE projects SET shots=?,script_status=?,status=?,updated=?,final_video=NULL WHERE id=?',
                       (jd(shots),'ai_draft','script_review',now(),pid))
        folder=project_dir(pid)
        (folder/'shots.json').write_text(jd(shots),encoding='utf-8')
        (folder/'script_outline.json').write_text(jd(plan),encoding='utf-8')
        step(jid,'review',current=len(shots),total=len(shots),status='complete')
        log(jid,f'AI đã viết đủ {len(shots)} shot. Cần duyệt kịch bản trước khi sản xuất.','success')
    except Exception as exc:
        step(jid,'failed',status='failed',error=str(exc)[:500])
        log(jid,'AI biên kịch thất bại. Storyboard cũ vẫn được giữ: '+str(exc)[:400],'error')


@app.post('/api/projects/{project_id}/ai-script',status_code=202)
def start_ai_script(project_id:str):
    read_project(project_id)
    if not ai_writer.available():
        raise HTTPException(503,'Chưa cấu hình OPENAI_API_KEY trong Environment của Render. Không chạy AI trả phí.')
    with state_lock:
        with connect() as db:
            active=db.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running')",(project_id,)).fetchone()
            if active:raise HTTPException(409,'Một tác vụ khác đang chạy trong dự án này')
            jid='writer_'+uuid.uuid4().hex[:12]
            moment=now()
            db.execute('INSERT INTO jobs(id,project_id,status,step,preview_seconds,created,updated,kind) VALUES(?,?,?,?,?,?,?,?)',
                       (jid,project_id,'queued','ai_queued',0,moment,moment,'writer'))
        executor.submit(ai_write_job,jid,project_id)
    return read_job(jid)


@app.get('/api/projects/{project_id}/ai-job')
def read_ai_job(project_id:str):
    read_project(project_id)
    with connect() as db:
        row=db.execute("SELECT id FROM jobs WHERE project_id=? AND kind='writer' ORDER BY created DESC LIMIT 1",(project_id,)).fetchone()
    return read_job(row['id']) if row else None


@app.post('/api/projects/{project_id}/approve-script')
def approve_ai_script(project_id:str):
    project=read_project(project_id)
    if project.get('script_status') not in ('ai_draft','approved'):
        raise HTTPException(409,'Chỉ duyệt storyboard do AI viết thành công. Storyboard mô phỏng chưa đủ nội dung.')
    shots=project['shots']
    if not shots or any(not sh.get('action') or not sh.get('image_prompt') or not sh.get('video_prompt') for sh in shots):
        raise HTTPException(422,'Còn shot thiếu nội dung, chưa thể duyệt')
    with connect() as db:
        db.execute('UPDATE projects SET script_status=?,status=?,updated=? WHERE id=?',('approved','script_approved',now(),project_id))
    return {'ok':True,'script_status':'approved','shot_count':len(shots)}


class RenderRequest(BaseModel):
    preview_seconds:int=Field(default=30,ge=4,le=60)


@app.post('/api/projects/{project_id}/run',status_code=202)
def run_project(project_id:str, req:RenderRequest):
    project=read_project(project_id)
    with state_lock:
        with connect() as db:
            active=db.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running')",(project_id,)).fetchone()
            if active:raise HTTPException(409,'Dự án này đang có tác vụ chạy')
            jid='job_'+uuid.uuid4().hex[:12]
            moment=now()
            db.execute('INSERT INTO jobs(id,project_id,status,step,preview_seconds,created,updated,kind) VALUES(?,?,?,?,?,?,?,?)',
                       (jid,project_id,'queued','queued',req.preview_seconds,moment,moment,'render'))
        executor.submit(demo_render_job,jid,project_id,req.preview_seconds)
    return read_job(jid)


@app.get('/api/projects/{project_id}/jobs')
def latest_job(project_id:str):
    read_project(project_id)
    with connect() as db:
        row=db.execute("SELECT id FROM jobs WHERE project_id=? AND kind='render' ORDER BY created DESC LIMIT 1",(project_id,)).fetchone()
    return read_job(row['id']) if row else None


@app.get('/api/jobs/{job_id}')
def get_job(job_id:str):
    return read_job(job_id)


@app.get('/api/projects/{project_id}/artifacts')
def project_artifacts(project_id:str):
    p=read_project(project_id)
    d=project_dir(project_id)
    arts=[]
    for name in ['script_outline.json','preview.mp4','preview_subtitles.srt','shots.json','story.txt','node_workflow_mock_NOT_TOBYFLOW.json','tobyflow_blueprint_NOT_IMPORTABLE.json']:
        f=d/name
        if f.is_file():arts.append({'name':name,'url':url_for_file(f),'size_bytes':f.stat().st_size})
    for f in sorted((d/'clips').glob('*.mp4')) if (d/'clips').exists() else []:
        arts.append({'name':f.name,'url':url_for_file(f),'size_bytes':f.stat().st_size})
    return arts


@app.get('/media/{resource_path:path}')
def serve_media(resource_path:str):
    path=(DATA / resource_path).resolve()
    if not path.is_relative_to(DATA.resolve()) or not path.is_file() or path.suffix.lower() not in ('.png','.jpeg','.jpg','.webp','.mp4','.srt','.json','.txt'):
        raise HTTPException(404,'Không tìm thấy file')
    return FileResponse(path)


DIST=ROOT/'frontend'/'dist'
if DIST.is_dir():
    # Mounted after API so /api always wins
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='front-assets')
    @app.get('/')
    def home(): return FileResponse(DIST/'index.html')
    @app.get('/{path:path}')
    def spa_fallback(path:str):
        if path.startswith(('api/','media/','docs','openapi.json')):
            raise HTTPException(404)
        return FileResponse(DIST/'index.html')
else:
    @app.get('/')
    def home():
        return {'message':'Giao diện chưa build. Chạy npm install và npm run build trong frontend/.'}
