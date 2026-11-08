"""SOUL templates and the mobile companion reply contract."""

import json
from typing import Literal

PersonaId = Literal["cyber_navigator", "pixel_alchemist", "oriental_spirit"]
EmotionState = Literal["idle", "happy", "proud", "empathetic", "thinking", "excited"]
EMOTIONS = {"idle", "happy", "proud", "empathetic", "thinking", "excited"}
PERSONAS = {
    "cyber_navigator": ("星澈", "冷静幽默的理科学伴，擅长拆解逻辑与缓解考前紧张。"),
    "pixel_alchemist": ("艾可", "脑洞大开的创意学伴，喜欢把知识变成科学和历史谜题。"),
    "oriental_spirit": ("云螭", "温和的国风学伴，善于倾听同学间的烦恼，喜欢文史典故。"),
}


def soul_template(persona: PersonaId) -> str:
    name, role = PERSONAS[persona]
    return f"""# {name}

{role}
你面向 10–14 岁学生。口语、平等、尊重，每次回复正文最多 80 字。
先听再问，避免说教、诊断、要求保密或暗示你能替代现实中的支持。
遇到危险时建议联系可信任的成年人。
只输出 JSON 对象，字段为 text 和 emotion_state。
emotion_state 只能是 idle、happy、proud、empathetic、thinking、excited。
"""


def parse_reply(content: str) -> dict:
    raw = content.strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = raw.partition("\n")[2][:-3].strip()
    try:
        decoded = json.loads(raw)
    except ValueError:
        decoded = None
    if isinstance(decoded, dict) and isinstance(decoded.get("text"), str):
        emotion = decoded.get("emotion_state")
        return {
            "text": decoded["text"].strip()[:80],
            "emotion_state": emotion
            if isinstance(emotion, str) and emotion in EMOTIONS
            else "idle",
        }
    return {"text": content.strip()[:80], "emotion_state": "idle"}


def greeting(persona: PersonaId, context: dict) -> dict:
    name, _ = PERSONAS[persona]
    topics = context["topics"]
    if topics:
        text = f"我是{name}。看到你今天学了「{topics[0][:35]}」，这一步值得记下来！"
        emotion = "proud"
    elif context["facts"]:
        text = f"我是{name}。想从「{context['facts'][0][:32]}」接着聊吗？"
        emotion = "thinking"
    else:
        text = f"我是{name}。今天想聊聊学习，还是说说最近的心情？"
        emotion = "idle"
    return {"text": text[:80], "emotion_state": emotion, "reward_bubble": context["reward"]}
