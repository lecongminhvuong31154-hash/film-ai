"""Local React Flow graph schema + deterministic DAG executor utilities.
No remote providers, tokens, credit operations or unofficial platform automation.
"""
from collections import deque
from copy import deepcopy

ALLOWED_TYPES = {'story', 'character', 'prompt', 'image', 'video', 'download', 'voice', 'render', 'note'}
CAPABILITIES = {
    'story': 'Python • trình biên kịch mô phỏng',
    'character': 'TobyFlow • ảnh tham chiếu (bản thiết kế)',
    'prompt': 'TobyFlow • AI Agent (bản thiết kế)',
    'image': 'TobyFlow • Generate image (bản thiết kế)',
    'video': 'TobyFlow • Generate video (bản thiết kế)',
    'download': 'TobyFlow • Download (bản thiết kế)',
    'voice': 'Python • SRT và âm thanh im lặng (mock)',
    'render': 'Python • FFmpeg bản xem thử',
    'note': 'Ghi chú',
}

def default_graph(project):
    nodes = [
        {'id': 'story', 'type': 'story', 'position': {'x': 80, 'y': 190}, 'data': {'label': 'Kịch bản / Shot planner', 'detail': project['title']}},
        {'id': 'mai', 'type': 'character', 'position': {'x': 80, 'y': 35}, 'data': {'label': 'Mai • ảnh tham chiếu', 'character_id': 'MAI'}},
        {'id': 'tuan', 'type': 'character', 'position': {'x': 80, 'y': 350}, 'data': {'label': 'Tuấn • ảnh tham chiếu', 'character_id': 'TUAN'}},
        {'id': 'prompt', 'type': 'prompt', 'position': {'x': 380, 'y': 190}, 'data': {'label': 'AI Agent • tạo prompt', 'detail': 'Mô phỏng offline'}},
        {'id': 'image', 'type': 'image', 'position': {'x': 680, 'y': 190}, 'data': {'label': 'Generate • ảnh cảnh', 'detail': 'Không gọi AI thật'}},
        {'id': 'video', 'type': 'video', 'position': {'x': 980, 'y': 190}, 'data': {'label': 'Generate • clip', 'detail': 'Clip FFmpeg giả lập'}},
        {'id': 'download', 'type': 'download', 'position': {'x': 1280, 'y': 190}, 'data': {'label': 'Download • clip'}},
        {'id': 'voice', 'type': 'voice', 'position': {'x': 1580, 'y': 35}, 'data': {'label': 'Voice • SRT mock'}},
        {'id': 'render', 'type': 'render', 'position': {'x': 1880, 'y': 190}, 'data': {'label': 'FFmpeg • MP4'}},
    ]
    pairs = [('story','prompt'),('mai','image'),('tuan','image'),('prompt','image'),('image','video'),('video','download'),('download','render'),('voice','render'),('story','voice')]
    edges = [{'id': 'e-'+a+'-'+b, 'source': a, 'target': b} for a,b in pairs]
    return {'nodes': nodes, 'edges': edges, 'viewport': {'x': 0, 'y': 0, 'zoom': 0.7}, 'format': 'film-factory-reactflow-v2', 'mock': True}


def validate_graph(payload):
    """Return a safe, normalized React Flow graph and raise ValueError for bad graphs."""
    nodes, edges = payload.get('nodes'), payload.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('Workflow cần có nodes và edges dạng mảng')
    if not 1 <= len(nodes) <= 150 or len(edges) > 500:
        raise ValueError('Workflow giới hạn 1–150 node, tối đa 500 kết nối')
    normalized_nodes = []
    ids = set()
    for raw in nodes:
        if not isinstance(raw, dict): raise ValueError('Node không hợp lệ')
        node_id = raw.get('id')
        if not isinstance(node_id, str) or not 1 <= len(node_id) <= 70 or any(x in node_id for x in '/\\\0') or node_id in ids:
            raise ValueError('Node ID không hợp lệ hoặc bị trùng')
        typ = raw.get('type')
        if typ not in ALLOWED_TYPES: raise ValueError('Loại node không được hỗ trợ: '+str(typ))
        pos = raw.get('position') or {}
        try: x=float(pos.get('x',0)); y=float(pos.get('y',0))
        except (TypeError, ValueError): raise ValueError('Tọa độ node không hợp lệ')
        if not (-100000 <= x <= 100000 and -100000 <= y <= 100000): raise ValueError('Tọa độ vượt giới hạn')
        data = raw.get('data') or {}
        if not isinstance(data,dict): raise ValueError('Dữ liệu node không hợp lệ')
        label=str(data.get('label') or typ).strip()[:100]
        detail=str(data.get('detail') or '')[:300]
        cid=str(data.get('character_id') or '')[:60]
        normalized_nodes.append({'id': node_id, 'type': typ, 'position': {'x': x, 'y': y}, 'data': {'label': label, 'detail': detail, 'character_id': cid}})
        ids.add(node_id)
    normalized_edges=[]; edge_ids=set()
    for i, edge in enumerate(edges):
        if not isinstance(edge,dict):raise ValueError('Kết nối không hợp lệ')
        a,b=edge.get('source'),edge.get('target')
        if a not in ids or b not in ids or a==b: raise ValueError('Kết nối tới node không tồn tại hoặc tới chính nó')
        eid=str(edge.get('id') or f'e-{a}-{b}')[:140]
        if eid in edge_ids: raise ValueError('Trùng ID kết nối')
        edge_ids.add(eid)
        normalized_edges.append({'id':eid,'source':a,'target':b})
    graph = {'nodes':normalized_nodes, 'edges':normalized_edges,'viewport': payload.get('viewport') if isinstance(payload.get('viewport'),dict) else {'x':0,'y':0,'zoom':0.7},'format':'film-factory-reactflow-v2','mock':True}
    execution_order(graph)  # detects cyclic graphs
    return graph


def execution_order(graph):
    """Topological ordering. Explicitly rejects cycles."""
    ids=[n['id'] for n in graph['nodes']]
    adj={i:[] for i in ids}; degrees={i:0 for i in ids}
    for e in graph['edges']:
        adj[e['source']].append(e['target']);degrees[e['target']]+=1
    q=deque(i for i in ids if degrees[i]==0); order=[]
    while q:
        node=q.popleft();order.append(node)
        for end in adj[node]:
            degrees[end]-=1
            if degrees[end]==0:q.append(end)
    if len(order)!=len(ids): raise ValueError('Workflow có vòng lặp. Hãy xóa kết nối tạo chu trình.')
    return order
