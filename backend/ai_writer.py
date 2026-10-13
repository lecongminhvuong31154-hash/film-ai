"""Optional, opt-in AI screenplay planner using a server-side API key.

Never runs when creating an ordinary project. Never logs API keys or raw responses.
Any provider failure leaves the previously saved storyboard untouched.
"""
from __future__ import annotations
import json
import math
import os
import re
from typing import Callable

import httpx

API_URL = 'https://api.openai.com/v1/chat/completions'
BATCH_SIZE = 8


class WriterError(Exception):
    pass


def available() -> bool:
    return bool(os.getenv('OPENAI_API_KEY', '').strip())


def config() -> dict:
    return {
        'available': available(),
        'provider': 'OpenAI API',
        'model': os.getenv('AI_WRITER_MODEL', 'gpt-4.1-mini'),
        'batch_size': BATCH_SIZE,
        'note': 'Chỉ gọi khi nhấn Tạo storyboard bằng AI. Dịch vụ có thể tính phí token. Không gửi API key vào giao diện hay GitHub.'
    }


def _call_json(messages: list[dict], max_tokens: int) -> dict:
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise WriterError('Chưa cấu hình OPENAI_API_KEY trên máy chủ Render.')
    data = {
        'model': os.getenv('AI_WRITER_MODEL', 'gpt-4.1-mini'),
        'messages': messages,
        'response_format': {'type': 'json_object'},
        'temperature': 0.65,
        'max_completion_tokens': max_tokens,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(95, connect=12)) as client:
            res = client.post(API_URL, json=data, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        if res.status_code >= 400:
            if res.status_code in (401, 403):
                raise WriterError('API key không hợp lệ hoặc không được cấp quyền sử dụng mô hình.')
            if res.status_code == 429:
                raise WriterError('API đang giới hạn yêu cầu hoặc đã hết hạn mức. Không thay đổi storyboard cũ.')
            raise WriterError(f'Nhà cung cấp AI trả về HTTP {res.status_code}; hãy kiểm tra model hoặc giới hạn tài khoản.')
        obj = res.json()
        content = obj['choices'][0]['message']['content']
        if not content:
            raise WriterError('AI trả về nội dung trống.')
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise WriterError('AI không trả JSON object.')
        return parsed
    except (httpx.RequestError, ValueError, KeyError, IndexError) as exc:
        raise WriterError('Kết nối AI hoặc JSON trả về không hợp lệ; storyboard cũ được giữ nguyên.') from exc


def _clean(value, maxlen=500, default=''):
    return str(value if value is not None else default).strip()[:maxlen]


def _slug(text, index):
    name = re.sub(r'[^A-Za-z0-9]+', '_', text.upper()).strip('_')
    return ('CAST_' + (name or str(index)))[:40]


def outline(story: str, minutes: int, *, call: Callable = _call_json) -> dict:
    prompt = f'''Viết một dàn ý phim NGUYÊN BẢN từ cốt truyện bên dưới, không sao chép phim có sẵn.
Ngôn ngữ: tiếng Việt. Thời lượng {minutes} phút, bố cục 9:16, phim người thật điện ảnh.
Đảm bảo nhân vật, mâu thuẫn, chi tiết gợi mở, cao trào và kết thúc hợp logic.
Trả duy nhất JSON object có các keys:
characters: mảng 2-6 object {{"name":"", "role":"", "costume":"", "voice":""}};
locations: mảng tên bối cảnh (2-6);
beats: mảng ĐÚNG 8 object {{"title":"", "summary":"", "twist_or_clue":""}}.
Cốt truyện: {story[:25000]}'''
    ans = call([
        {'role':'system','content':'Bạn là biên kịch phim ngắn tiếng Việt. Trả duy nhất JSON có cấu trúc chính xác.'},
        {'role':'user','content':prompt}
    ], 2800)
    rawchars = ans.get('characters')
    rawbeats = ans.get('beats')
    if not isinstance(rawchars, list) or not 1 <= len(rawchars) <= 12:
        raise WriterError('AI không trả danh sách nhân vật hợp lệ.')
    if not isinstance(rawbeats, list) or len(rawbeats) != 8:
        raise WriterError('AI không trả đủ 8 nhịp truyện; vui lòng thử lại.')
    chars=[];seen=set()
    for i,c in enumerate(rawchars):
        if not isinstance(c,dict):continue
        name=_clean(c.get('name'),80)
        if not name or name.casefold() in seen:continue
        seen.add(name.casefold())
        chars.append({'id':_slug(name,i+1), 'name':name, 'role':_clean(c.get('role'),160),
                      'costume':_clean(c.get('costume'),300), 'voice':_clean(c.get('voice'),240)})
    if not chars:raise WriterError('Thiếu nhân vật hợp lệ.')
    beats=[]
    for b in rawbeats:
        if not isinstance(b,dict):raise WriterError('Nhịp truyện không hợp lệ.')
        beats.append({'title':_clean(b.get('title'),120), 'summary':_clean(b.get('summary'),900), 'twist_or_clue':_clean(b.get('twist_or_clue'),400)})
    locs=[_clean(x,140) for x in ans.get('locations',[]) if isinstance(x,str)]
    return {'characters':chars,'locations':locs[:8], 'beats':beats}


def generate_shots(story: str, minutes: int, *, progress: Callable | None = None, call: Callable = _call_json) -> tuple[dict,list[dict]]:
    """Generate all shot descriptions without persisting partial results."""
    target=minutes*60
    count=math.ceil(target/8)
    batch_count=math.ceil(count/BATCH_SIZE)
    max_calls=int(os.getenv('AI_WRITER_MAX_CALLS','20'))
    if batch_count+1 > max_calls:
        raise WriterError(f'Dự án cần {batch_count+1} lượt API, vượt AI_WRITER_MAX_CALLS={max_calls}.')
    if progress:progress('outline',0,batch_count+1)
    plan=outline(story,minutes,call=call)
    cast={c['id']:c for c in plan['characters']}
    results=[]
    for index in range(0,count,BATCH_SIZE):
        end=min(index+BATCH_SIZE,count)
        stage=index//BATCH_SIZE+1
        if progress:progress(f'writing:{index+1}-{end}',stage,batch_count+1)
        previous=[{'title':s['title'],'action':s['action']} for s in results[-2:]]
        request=[{'id':f'SC{i+1:03d}','start_second':i*8,'duration_seconds':min(8,target-i*8),
                  'beat_index':min(7, (i*8*8)//target)} for i in range(index,end)]
        prompt='''Viết chi tiết CHÍNH XÁC từng shot yêu cầu. Dùng tiếng Việt cho lời thoại, hành động, bối cảnh.
Prompt tạo ảnh/video dùng tiếng Anh, mô tả rõ nhân vật, ánh sáng, hành động, camera, bảo toàn danh tính, không text, 9:16.
Mỗi shot 8 giây: tối đa ~18 từ lời thoại để đọc tự nhiên. Cảnh không thoại có speaker=null và dialogue="".
Không đặt các câu thoại cũ lặp lại; câu chuyện phải phát triển hợp lý. Không tạo cảnh nhảm để đủ thời gian.
Trả JSON object duy nhất với {"shots":[...]}. Mỗi phần tử cần có CHÍNH XÁC các key:
"id","title","action","location","camera","dialogue","speaker","characters","image_prompt","video_prompt".
"speaker" là ID trong dàn nhân vật hoặc null; "characters" là mảng ID hợp lệ; không tự chế ID.
Chỉ viết các shot được chỉ định, đúng thứ tự; không được thêm hoặc bỏ shot.
DỮ LIỆU:\n'''+json.dumps({'story':story[:12000], 'characters':list(cast.values()),'locations':plan['locations'],
                           'beats':plan['beats'],'previous_shots':previous,'requested_shots':request},ensure_ascii=False)
        resp=call([
            {'role':'system','content':'Bạn là đạo diễn kiêm biên kịch phim ngắn tiếng Việt, tạo shot list có cấu trúc JSON. Duy trì logic, nhân vật và tình tiết.'},
            {'role':'user','content':prompt}
        ], 6500)
        raw=resp.get('shots')
        if not isinstance(raw,list) or len(raw)!=len(request):
            raise WriterError(f'AI trả sai số shot trong nhóm {index+1}–{end}. Không thay đổi dự án.')
        for j,(item,meta) in enumerate(zip(raw,request)):
            if not isinstance(item,dict) or _clean(item.get('id'),10)!=meta['id']:
                raise WriterError(f'AI trả sai ID shot {meta["id"]}. Không thay đổi dự án.')
            chosen=item.get('characters',[])
            if not isinstance(chosen,list):chosen=[]
            chosen=[x for x in chosen if isinstance(x,str) and x in cast][:8]
            speaker=item.get('speaker')
            if speaker not in cast:speaker=None
            if speaker and speaker not in chosen: chosen.append(speaker)
            action=_clean(item.get('action'),1100)
            if not action:raise WriterError(f'{meta["id"]} không có hành động.')
            dialogue=_clean(item.get('dialogue'),600)
            results.append({
                'id':meta['id'], 'index':len(results)+1, 'start_second':meta['start_second'],
                'duration_seconds':meta['duration_seconds'],
                'title':_clean(item.get('title'),140,'Phân cảnh'), 'action':action,
                'location':_clean(item.get('location'),200,'Bối cảnh theo kịch bản'),
                'camera':_clean(item.get('camera'),150,'medium shot'),
                'dialogue':dialogue, 'speaker':speaker if dialogue else None,
                'characters':chosen,
                'image_prompt':_clean(item.get('image_prompt'),3500),
                'video_prompt':_clean(item.get('video_prompt'),3500),
                'status':'draft_ai', 'notes':'Được AI lập bản nháp. Cần người duyệt trước khi sản xuất.'
            })
    if len(results)!=count or sum(x['duration_seconds'] for x in results)!=target:
        raise WriterError('AI viết sai thời lượng tổng. Không thay đổi dự án.')
    if progress:progress('ready_for_review',batch_count+1,batch_count+1)
    return plan,results
