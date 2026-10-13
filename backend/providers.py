"""Provider interface for a future *authorized* API connection.

The included MVP cannot sign in to, automate, or spend credits on TobyFlow,
Google Flow, or any paid video service. This avoids presenting a mock as live.
"""
from dataclasses import dataclass
from typing import Protocol, Optional

@dataclass
class RenderRequest:
    shot_id: str
    image_path: str
    video_prompt: str
    seconds: int

@dataclass
class RenderResult:
    shot_id: str
    local_video_path: str
    credits_spent: Optional[float] = None

class VideoProvider(Protocol):
    def render(self, request: RenderRequest) -> RenderResult: ...

class TobyFlowProvider:
    """Live adapter not implemented: requires documented permissions and credentials."""
    def render(self, request: RenderRequest) -> RenderResult:
        raise NotImplementedError(
            'TobyFlow chỉ được mô tả dưới dạng blueprint trong MVP. '
            'Không có kết nối live hay lệnh tự tiêu credit.'
        )
