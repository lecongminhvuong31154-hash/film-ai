"""Deterministic offline story planner (NOT an LLM). Swap with licensed AI API later."""
import re
import math

CHARACTER_DEFAULTS = [
    {"id": "MAI", "name": "Mai", "role": "Nhân viên lao công", "costume": "Đồng phục xanh nhạt, cổ trắng", "voice": "Giọng nữ miền Nam trầm, điềm tĩnh"},
    {"id": "TUAN", "name": "Tuấn", "role": "Phó giám đốc", "costume": "Vest xanh đen, sơ mi trắng, cà vạt xanh", "voice": "Giọng nam miền Nam, cứng rắn"},
]

STORY_DEMO = (
    "Một cô lao công tên Mai phát hiện hợp đồng 50 tỷ có điều khoản bí mật. "
    "Phó giám đốc Tuấn coi thường và trách mắng cô. "
    "Mai nhận thấy trang 17 có điều khoản khiến công ty có thể mất quyền kiểm soát. "
    "Mai cảnh báo giám đốc và đề nghị dừng ký để kiểm tra lại. "
    "Linh tìm được bản hợp đồng cũ. "
    "Cuối cùng, Mai tiết lộ từng làm chuyên viên kiểm soát rủi ro ở công ty đối tác."
)

DEMO_BEATS = [
    ("Ly nước đổ", "Một ly nước đổ gần bản hợp đồng trên bàn họp", "NONE", "close-up, slow push-in", "Tiếng nước đổ gần tập hồ sơ."),
    ("Tuấn nổi giận", "Tuấn đứng dậy chỉ về phía Mai, tức giận", "TUAN", "medium shot", "Cô có biết hợp đồng này trị giá năm mươi tỷ không?"),
    ("Mai phát hiện", "Mai nhìn hợp đồng, dừng ở trang 17", "MAI", "medium close-up", "Khoan đã... Trang mười bảy có vấn đề."),
    ("Mai cảnh báo", "Mai đứng thẳng, bình tĩnh cảnh báo giám đốc", "MAI", "slow push-in", "Nếu ông ký, công ty này có thể không còn thuộc về ông."),
]


def sentences(text: str):
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+", text.strip()) if s.strip()] or [text.strip()]


def build_shots(story: str, minutes: int, sec_per_shot: int = 8):
    """Always create complete duration manifest; render engine may only preview first N seconds."""
    text = story.strip()
    if not text:
        raise ValueError("Cốt truyện không được để trống")
    if minutes < 1 or minutes > 15:
        raise ValueError("Thời lượng phải từ 1 tới 15 phút")
    target = minutes * 60
    count = math.ceil(target / sec_per_shot)
    texts = sentences(text)
    is_demo = "lao công" in text.lower() and ("hợp đồng" in text.lower() or "50 tỷ" in text.lower())
    out = []
    t = 0
    for i in range(count):
        duration = min(sec_per_shot, target - t)
        if is_demo and i < len(DEMO_BEATS):
            title, action, who, camera, dialogue = DEMO_BEATS[i]
            characters = [] if who == "NONE" else [who]
        else:
            line = texts[min(len(texts)-1, i * len(texts) // count)]
            who = ["MAI", "TUAN", "MAI", "NONE"][i % 4]
            title = "Phân đoạn %02d" % (i+1)
            action = line
            characters = [] if who == "NONE" else [who]
            camera = ["medium shot", "close-up", "over-shoulder", "wide shot"][i % 4]
            dialogue = line[:155] if who != "NONE" else ""
        notes = "Đây là mô phỏng storyboard, cần biên tập nội dung và thời lượng trước khi sản xuất thật."
        out.append({
            "id": f"SC{i+1:03d}", "index": i+1, "title": title,
            "start_second": t, "duration_seconds": duration,
            "characters": characters, "location": "Phòng họp công ty An Phát" if is_demo else "Bối cảnh theo cốt truyện",
            "action": action, "camera": camera,
            "dialogue": dialogue, "speaker": characters[0] if characters else None,
            "image_prompt": f"Photorealistic Vietnamese drama, {action}. {camera}. Preserve character references. Vertical 9:16, no text, no watermark.",
            "video_prompt": f"Animate reference frame: {action}. Natural breathing, subtle motion, stable identity, {camera}. Continuous shot, no subtitles.",
            "status": "planned", "notes": notes,
        })
        t += duration
    assert t == target
    return out


def make_workflow_plan(project_id, shots, characters):
    """Human-readable TobyFlow plan. NOT a native TobyFlow import schema or live integration."""
    nodes = [
        {"id": "STORY", "type": "external", "name": "Story planner (Python)", "mode": "mock"},
    ]
    edges = []
    for char in characters:
        nodes.append({"id": f"REF_{char['id']}", "type": "Image", "name": f"Ảnh gốc {char['name']}", "asset": char.get("image_url", "")})
    for shot in shots:
        aid = f"PROMPT_{shot['id']}"
        iid = f"IMAGE_{shot['id']}"
        vid = f"VIDEO_{shot['id']}"
        did = f"SAVE_{shot['id']}"
        nodes.extend([
            {"id": aid, "type": "AI Agent", "name": f"Chuẩn hóa prompt {shot['id']}", "prompt": shot["image_prompt"]},
            {"id": iid, "type": "Generate", "output": "image", "name": f"Ảnh {shot['id']}", "prompt": shot["image_prompt"]},
            {"id": vid, "type": "Generate", "output": "video", "name": f"Video {shot['id']}", "prompt": shot["video_prompt"]},
            {"id": did, "type": "Download", "name": f"Tải {shot['id']}"},
        ])
        edges += [[aid, iid], [iid, vid], [vid, did]]
        for c in shot["characters"]:
            edges.append([f"REF_{c}", iid])
    return {
        "format": "ai-film-factory-proposal-v1", "project_id": project_id,
        "notice": "BẢN THIẾT KẾ THAM KHẢO, KHÔNG PHẢI FILE IMPORT TOBYFLOW. Chưa kết nối dịch vụ, chưa tiêu credit.",
        "supported_tobyflow_types": ["Image", "AI Agent", "Generate", "Download", "Delay", "Note"],
        "external_required": ["Story parser", "Shot manifest", "Queue", "Voice/TTS", "Lip-sync", "FFmpeg editor", "Quality check"],
        "nodes": nodes, "edges": edges,
    }
