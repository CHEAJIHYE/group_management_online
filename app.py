# -*- coding: utf-8 -*-
"""
온라인팀 통합관리시스템
- 대시보드 / 일정 관리 / 온라인팀(행사) / 온라인팀(관리) / 구성원 관리
데이터는 로컬 JSON 파일(online_team_data.json)에 저장되어 여러 사용자가
같은 서버에서 접속했을 때도 데이터가 공유됩니다.
시스템 시간 기준은 대한민국(서울, KST, UTC+9)입니다.
"""

import streamlit as st
import urllib.parse
import json
import os
import re
import io
import hashlib
import uuid
import base64
import calendar as cal
import requests
from datetime import date, datetime, timedelta, timezone
from PIL import Image

try:
    from streamlit_quill import st_quill
    QUILL_AVAILABLE = True
except ImportError:
    QUILL_AVAILABLE = False

# --------------------------------------------------------------------------
# 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(page_title="온라인팀 통합관리시스템", page_icon="🌐", layout="wide")

APP_VERSION = "v8.5"
COPYRIGHT_OWNER = "MOOAS TEAM ONLINE"

# 캘린더 등 여러 st.columns 행이 연달아 쌓이는 곳의 세로 여백을 전역으로 줄입니다.
# (컨테이너 key 기반 스코프 CSS는 이 환경에서 매칭되지 않아 전역 선택자로 적용합니다.)
st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlock"] { gap: 0.25rem !important; }
    div[data-testid="stHorizontalBlock"] { margin-top: 0rem !important; margin-bottom: 0rem !important; }
    div[data-testid="element-container"] { margin-bottom: 0rem !important; }
    table.pasted-excel-table { border-collapse: collapse; margin: 8px 0; }
    table.pasted-excel-table th, table.pasted-excel-table td {
        border: 1px solid #ccc; padding: 4px 10px; font-size: 13px;
    }
    table.pasted-excel-table th { background: #f5f5f5; }

    /* Quill 서식 편집기의 글자 크기 클래스는 편집기 내부에서만 스타일이 정의되어 있어,
       작성 후 게시글로 표시될 때는 크기가 반영되지 않는 문제가 있었습니다.
       (Quill 기본 테마와 동일한 값으로) 페이지 전체에 적용해 작성 시 보이는 크기가
       게시 후에도 그대로 유지되도록 합니다. */
    .ql-size-small { font-size: 0.75em; }
    .ql-size-large { font-size: 1.5em; }
    .ql-size-huge { font-size: 2.5em; }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "online_team_data.json")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")

KST = timezone(timedelta(hours=9))


def get_build_date():
    """이 app.py 파일이 마지막으로 수정(생성)된 날짜를 자동으로 가져옵니다.
    파일을 갱신해서 배포할 때마다 별도로 손볼 필요 없이 항상 최신 날짜가 표시됩니다."""
    try:
        mtime = os.path.getmtime(__file__)
        return datetime.fromtimestamp(mtime, tz=KST).strftime("%Y-%m-%d")
    except Exception:
        return "-"


APP_BUILD_DATE = get_build_date()


def kst_now():
    return datetime.now(KST)


def kst_today():
    return kst_now().date()


@st.cache_data(ttl=600)
def fetch_songpa_weather():
    """송파구 문정동(위도/경도 기준) 현재 날씨를 wttr.in에서 가져와 구조화된 값으로 반환합니다.
    (API 키가 필요 없는 무료 서비스라 별도 설정 없이 바로 사용 가능합니다.)"""
    try:
        resp = requests.get(
            "https://wttr.in/37.4853,127.1218",
            params={"format": "%C|%t|%f|%h|%w", "m": ""},
            headers={"User-Agent": "curl"},
            timeout=5,
        )
        if resp.status_code == 200:
            text = resp.text.strip()
            if text and "Unknown location" not in text and "|" in text:
                parts = [p.strip() for p in text.split("|")]
                if len(parts) == 5:
                    return {
                        "condition": parts[0], "temp": parts[1], "feels_like": parts[2],
                        "humidity": parts[3], "wind": parts[4],
                    }
    except Exception:
        pass
    return None


def weather_condition_to_emoji(condition_text):
    """날씨 상태 텍스트를 보고 어울리는 픽토그램(이모지)을 골라줍니다."""
    c = condition_text.lower()
    if "thunder" in c:
        return "⛈️"
    if "snow" in c or "sleet" in c or "ice" in c:
        return "❄️"
    if "rain" in c or "drizzle" in c or "shower" in c:
        return "🌧️"
    if "fog" in c or "mist" in c or "haze" in c:
        return "🌫️"
    if "overcast" in c:
        return "☁️"
    if "cloud" in c:
        return "⛅"
    if "clear" in c or "sunny" in c:
        return "☀️"
    return "🌡️"


FORTUNE_MESSAGES = [
    "오늘은 생각지도 못한 좋은 소식이 들려옵니다!",
    "차분히 준비한 일이 오늘 확실히 빛을 발해요.",
    "오늘 베푼 작은 친절이 큰 행운으로 돌아옵니다.",
    "오늘은 판단력과 감각이 최고조에 이르는 날이에요.",
    "미뤄왔던 일도 오늘은 술술 잘 풀립니다.",
    "동료와의 대화 속에서 반짝이는 아이디어를 얻게 돼요.",
    "오늘 하루는 시작부터 끝까지 순조롭게 흘러갑니다.",
    "작은 성취 하나가 오늘 자신감을 크게 키워줘요.",
    "생각지 못한 곳에서 든든한 도움을 받게 됩니다.",
    "오늘의 선택이 앞으로 좋은 결실로 이어집니다.",
    "오늘은 웃는 일이 유독 많이 생기는 하루예요.",
    "새롭게 시도하는 일마다 좋은 결과가 따라옵니다.",
    "짧은 휴식만으로도 오늘은 효율이 두 배가 돼요.",
    "오늘 건넨 말 한마디가 누군가에게 큰 힘이 됩니다.",
    "계획한 대로 모든 게 착착 순조롭게 진행돼요.",
    "오늘은 유난히 운이 좋게 따라주는 하루입니다.",
    "여유로운 한 잔의 시간이 좋은 영감을 선물해요.",
    "함께하는 사람들과 완벽한 호흡을 보여주는 날이에요.",
    "오늘 내린 결정은 두고두고 잘한 선택이 됩니다.",
    "세심하게 신경 쓴 만큼 오늘은 더 빛나는 하루예요.",
    "오늘은 원하는 일이 술술 풀리는 행운의 날입니다.",
    "주변 사람들에게 좋은 인상을 남기는 하루가 될 거예요.",
    "오늘 만나는 사람과 특별히 좋은 인연이 이어집니다.",
    "생각보다 빨리, 그리고 잘 마무리되는 하루예요.",
    "오늘은 자신감을 갖고 나서면 무엇이든 잘 됩니다.",
    "긍정적인 에너지가 하루 종일 함께하는 날이에요.",
    "오늘 하는 노력은 반드시 좋은 보답으로 돌아옵니다.",
    "예상보다 훨씬 즐겁고 기분 좋은 하루가 펼쳐져요.",
    "오늘은 모든 일이 나에게 유리하게 흘러갑니다.",
    "작은 행운들이 하루 종일 이어지는 날이에요.",
]


def get_daily_fortune(username):
    """사용자 이름 + 오늘 날짜(KST)를 기준으로 하루 동안 고정된, 항상 긍정적인 운세
    한 줄을 돌려줍니다."""
    seed_str = f"{username}_{kst_today().isoformat()}"
    idx = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16) % len(FORTUNE_MESSAGES)
    return FORTUNE_MESSAGES[idx]


def hash_pw(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


DEFAULT_PW_HASH = hash_pw("MOOAS1234")


DEFAULT_DATA = {
    "members": [
        {"name": "김담이", "color": "#A9C4EB", "position": "사원", "part": "1파트"},
        {"name": "천지현", "color": "#F5E6A3", "position": "과장", "part": "1파트"},
        {"name": "채지혜", "color": "#F3B8D3", "position": "대리", "part": "2파트"},
    ],
    "calendars": [],
    "schedules": [],
    "event_posts": [],
    "admin_posts": [],
    "vote_templates": [],
    "notifications": [],
    "change_logs": [],
    "last_auto_backup": None,
    "last_backup_path": None,
}

STATUS_LIST = ["제안", "진행", "미선정", "종료"]
CATEGORY_LIST = ["개인", "공동"]
ADMIN_STATUS_LIST = ["등록", "취합", "공지", "품절", "품절해지", "판매가변경", "수정", "완료"]
PART_OPTIONS = ["1파트", "2파트"]
STATUS_ICONS = {
    "등록": "📝", "완료": "✅", "취합": "🗂️", "공지": "📢",
    "제안": "💡", "진행": "🔄", "미선정": "🚫", "종료": "🏁",
    "품절": "⛔", "품절해지": "🔓", "판매가변경": "💰", "수정": "✏️",
}

PRESET_COLORS = [
    ("빨강", "#F5A9A9"), ("주황", "#F8C9A0"), ("노랑", "#F5E6A3"),
    ("연두", "#C8E6A0"), ("초록", "#A8D8B9"), ("청록", "#A0D9D0"),
    ("하늘", "#A8D0E6"), ("파랑", "#A9C4EB"), ("남색", "#B8B8E8"),
    ("보라", "#CBB2E0"), ("분홍", "#F3B8D3"), ("갈색", "#D4B896"),
]

POSITION_OPTIONS = [
    "상무", "차장", "과장", "사원", "이사", "부장",
    "부장/팀장", "대리", "부장/수석팀장", "과장/파트장",
    "차장/팀장", "대리/파트장",
]

POSITION_ORDER = [
    "상무", "이사", "부장/수석팀장", "부장/팀장", "부장",
    "차장/팀장", "차장", "과장/파트장", "과장",
    "대리/파트장", "대리", "사원",
]
POSITION_RANK = {p: i for i, p in enumerate(POSITION_ORDER)}


def new_id():
    return uuid.uuid4().hex[:10]


def now_str():
    return kst_now().strftime("%Y-%m-%d %H:%M")


def sorted_member_names_by_position(data):
    return [
        m["name"] for m in sorted(
            data["members"],
            key=lambda m: (POSITION_RANK.get(m.get("position", "사원"), 999), m["name"]),
        )
    ]


def sorted_members_by_position_full(data):
    """직급/직위 순 → 가나다순으로 정렬된 구성원 dict 리스트."""
    return sorted(
        data["members"],
        key=lambda m: (POSITION_RANK.get(m.get("position", "사원"), 999), m["name"]),
    )


def sorted_member_display_by_position(data):
    ordered = sorted_members_by_position_full(data)
    return [f"{m['name']} {m.get('position', '사원')}" for m in ordered]


def sorted_members_for_display(data):
    """구성원 관리 목록: 직급/직위 순 → 가나다순."""
    return sorted_members_by_position_full(data)


def load_data():
    if not os.path.exists(DATA_PATH):
        save_data(DEFAULT_DATA)
        return json.loads(json.dumps(DEFAULT_DATA))
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = json.loads(json.dumps(DEFAULT_DATA))
    for k, v in DEFAULT_DATA.items():
        data.setdefault(k, v if not isinstance(v, (list, dict)) else (v if not isinstance(v, list) else []))
    # 마이그레이션
    for m in data["members"]:
        m.setdefault("position", "사원")
        m.setdefault("part", "1파트")
        m.setdefault("password_hash", DEFAULT_PW_HASH)
    data.setdefault("change_logs", [])
    for p in data["admin_posts"]:
        p.setdefault("status", "등록")
        if p["status"] in ("★완료★", "진행"):
            p["status"] = "완료" if p["status"] == "★완료★" else "등록"
        p.setdefault("files", [])
        p.setdefault("images", [])
        p.setdefault("comments", [])
        for c in p["comments"]:
            c.setdefault("id", new_id())
            c.setdefault("parent_id", None)
    for p in data["event_posts"]:
        p.setdefault("files", [])
        p.setdefault("images", [])
        p.setdefault("comments", [])
        for c in p["comments"]:
            c.setdefault("id", new_id())
            c.setdefault("parent_id", None)
    return data


def save_data(data):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_data():
    if "data" not in st.session_state:
        st.session_state.data = load_data()
    return st.session_state.data


def persist():
    save_data(st.session_state.data)


def member_names(data):
    return [m["name"] for m in data["members"]]


def member_part_map(data):
    return {m["name"]: m.get("part", "1파트") for m in data["members"]}


def owner_names_combined(data):
    return sorted_member_names_by_position(data) + [c["name"] for c in data.get("calendars", [])]


def render_color_legend(names, data):
    items = [
        f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
        f"background:{owner_color(n, data)};margin-right:3px'></span>{n}"
        for n in names
    ]
    st.markdown(
        "<div style='font-size:12px;color:#555;margin-top:-6px;margin-bottom:8px'>"
        + "&nbsp;&nbsp;".join(items) + "</div>",
        unsafe_allow_html=True,
    )


def owner_color(name, data):
    for m in data["members"]:
        if m["name"] == name:
            return m["color"]
    for c in data.get("calendars", []):
        if c["name"] == name:
            return c["color"]
    return "#999999"


def vote_all_voted(post, data):
    if not post.get("vote"):
        return False
    members = set(member_names(data))
    if not members:
        return False
    voted = set()
    for o in post["vote"]["options"]:
        voted.update(o["voters"])
    return members.issubset(voted)


def vote_started(post):
    """투표 기능이 있는 게시글에 구성원이 한 명이라도 투표했는지 여부."""
    if not post.get("vote"):
        return False
    for o in post["vote"]["options"]:
        if o["voters"]:
            return True
    return False


def file_to_b64(uploaded_file):
    if uploaded_file is None:
        return None
    raw = uploaded_file.getvalue()
    return {
        "name": uploaded_file.name, "type": uploaded_file.type,
        "data": base64.b64encode(raw).decode("utf-8"),
    }


def render_attachment(att, key_prefix=""):
    if att is None:
        return
    if att.get("type", "").startswith("image/"):
        raw = base64.b64decode(att["data"])
        display_w = None
        try:
            im = Image.open(io.BytesIO(raw))
            display_w = min(im.width, 650)
        except Exception:
            display_w = None
        if display_w:
            st.image(raw, width=display_w)
        else:
            st.image(raw, width="stretch")
    else:
        st.download_button(
            f"📎 {att['name']}", data=base64.b64decode(att["data"]),
            file_name=att["name"], key=f"{key_prefix}_{att['name']}_{uuid.uuid4().hex[:6]}",
        )


def render_content(text):
    """줄바꿈을 유지하고, HTML 소스가 붙여넣기된 경우 그대로 렌더링합니다."""
    if not text:
        return
    stripped = text.strip()
    if stripped.startswith("<") and ">" in stripped:
        st.markdown(text, unsafe_allow_html=True)
    else:
        st.markdown(text.replace("\n", "  \n"))


QUILL_TOOLBAR = [
    [{"font": []}, {"size": []}],
    ["bold", "italic", "underline", "strike"],
    [{"color": []}, {"background": []}],
    [{"list": "ordered"}, {"list": "bullet"}, {"indent": "-1"}, {"indent": "+1"}],
    [{"align": []}],
    ["blockquote", "code-block", "link", "image"],
    ["formula", "clean"],
]

QUILL_CUSTOM_CSS = (
    "<style>.ql-editor {font-family:'맑은 고딕','Malgun Gothic',sans-serif !important;}</style>"
)


def rich_text_input(label, value="", key=None, height=160):
    """가능하면 위지윅(서식) 에디터를, streamlit-quill 미설치 시 일반 텍스트 입력으로 대체합니다."""
    if QUILL_AVAILABLE:
        st.caption(label)
        st.markdown(QUILL_CUSTOM_CSS, unsafe_allow_html=True)
        return st_quill(
            value=value, html=True, toolbar=QUILL_TOOLBAR,
            placeholder="내용을 입력하세요...", key=key,
        )
    st.caption(f"{label}  ·  서식 편집기를 쓰려면 `pip install streamlit-quill` 후 새로고침 해주세요.")
    return st.text_area(label, value=value, key=key, height=height, label_visibility="collapsed")



def extract_mentions(text, data):
    names = member_names(data)
    found = set()
    for name in sorted(names, key=len, reverse=True):
        if f"@{name}" in text:
            found.add(name)
    return found


def add_notification(data, user, message, board, post_id):
    if not user:
        return
    data.setdefault("notifications", []).append(
        {"id": new_id(), "user": user, "message": message, "board": board,
         "post_id": post_id, "created_at": now_str()}
    )


def add_change_log(data, user, action, target_type, title, board=None):
    """게시글/댓글 수정·삭제 시 변경 이력을 남깁니다."""
    data.setdefault("change_logs", []).append(
        {"id": new_id(), "user": user, "action": action, "target_type": target_type,
         "title": title, "board": board, "time": now_str()}
    )


def go_to(page_name, **filters):
    st.session_state["_pending_nav"] = {"page": page_name, "filters": filters}
    st.rerun()


def dash_metric(label, count, page_name, **filters):
    st.caption(label)
    if st.button(str(count), key=f"dashbtn_{label}_{page_name}_{filters}", width="stretch"):
        go_to(page_name, **filters)


def _board_display_name(board_key):
    return {"event": "온라인팀(행사)", "admin": "온라인팀(관리)"}.get(board_key, board_key)


def _build_board_html(page_title, posts_for_js):
    """게시판 형태(좌측 글 목록 + 우측 상세보기)의 정적 HTML 뷰어를 생성합니다.
    posts_for_js는 이미 JSON 직렬화 가능한 dict 리스트여야 합니다."""
    posts_json = json.dumps(posts_for_js, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{page_title}</title>
<link rel="stylesheet" href="css/style.css">
</head>
<body>
<div class="board-wrap">
  <div class="board-sidebar">
    <div class="board-logo">🌐 {page_title}</div>
    <input id="searchBox" class="search-box" type="text" placeholder="제목, 이름, 날짜 검색">
    <div id="postList" class="post-list"></div>
  </div>
  <div class="board-main" id="postDetail">
    <p class="empty-state">왼쪽에서 게시글을 선택해주세요.</p>
  </div>
</div>
<script src="scripts/script.js"></script>
<script>
const POSTS = {posts_json};
renderBoard(POSTS);
</script>
</body>
</html>"""


def _board_css():
    return """
body{font-family:'Malgun Gothic',sans-serif;margin:0;color:#222;background:#f4f5f7;}
.board-wrap{display:flex;height:100vh;}
.board-sidebar{width:320px;flex-shrink:0;background:#fff;border-right:1px solid #e2e2e2;
  overflow-y:auto;display:flex;flex-direction:column;}
.board-logo{font-size:20px;font-weight:700;color:#1f6feb;padding:16px;}
.search-box{margin:0 16px 8px;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;}
.post-list{flex:1;overflow-y:auto;}
.post-item{padding:12px 16px;border-bottom:1px solid #f0f0f0;cursor:pointer;}
.post-item:hover{background:#f7f9fc;}
.post-item.active{background:#eef4ff;border-left:3px solid #1f6feb;}
.post-item .p-title{font-size:14px;font-weight:600;color:#222;margin-bottom:4px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.post-item .p-meta{font-size:12px;color:#888;}
.board-main{flex:1;overflow-y:auto;padding:32px 48px;background:#fff;}
.empty-state{color:#999;}
.post-title{font-size:22px;font-weight:700;margin-bottom:8px;}
.post-meta{font-size:13px;color:#777;margin-bottom:16px;border-bottom:1px solid #eee;padding-bottom:12px;}
.post-meta b{color:#333;}
.status-badge{display:inline-block;background:#eef4ff;color:#1f6feb;border-radius:10px;
  padding:2px 10px;font-size:12px;margin-left:6px;}
.attachments{margin:16px 0;}
.att-img{display:inline-block;margin:0 10px 10px 0;text-align:center;vertical-align:top;}
.att-img img{max-width:220px;max-height:220px;border:1px solid #ddd;border-radius:4px;display:block;}
.att-img .att-name{font-size:11px;color:#888;margin-top:4px;max-width:220px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.att-file a{display:inline-block;margin:0 10px 8px 0;padding:6px 12px;background:#f5f5f5;
  border-radius:6px;font-size:13px;color:#333;text-decoration:none;}
.post-content{font-size:14.5px;line-height:1.7;margin:16px 0;}
.post-content table{border-collapse:collapse;width:100%;}
.post-content td,.post-content th{border:1px solid #ddd;padding:6px 10px;}
.comments-section{margin-top:24px;border-top:1px solid #eee;padding-top:16px;}
.comments-section h3{font-size:15px;margin-bottom:10px;}
.comment{padding:8px 0;border-bottom:1px solid #f4f4f4;font-size:13.5px;}
.comment b{color:#1f6feb;}
.c-time{color:#aaa;font-size:11.5px;margin-left:6px;}
.c-text{margin-top:4px;}
.no-comment{color:#999;font-size:13px;}
"""


def _board_js():
    return """
let currentPosts = [];

function renderBoard(posts) {
  currentPosts = posts;
  renderPostList(posts);
  if (posts.length > 0) showPost(posts[0].id);

  document.getElementById('searchBox').addEventListener('input', function(e) {
    const q = e.target.value.toLowerCase();
    const filtered = posts.filter(p =>
      p.title.toLowerCase().includes(q) ||
      p.author.toLowerCase().includes(q) ||
      p.date.toLowerCase().includes(q)
    );
    renderPostList(filtered);
  });
}

function renderPostList(posts) {
  const listEl = document.getElementById('postList');
  listEl.innerHTML = posts.map(p =>
    `<div class="post-item" data-id="${p.id}" onclick="showPost('${p.id}')">
       <div class="p-title">${escapeHtml(p.title)}</div>
       <div class="p-meta">${escapeHtml(p.author)} · ${escapeHtml(p.date)}</div>
     </div>`
  ).join('');
}

function showPost(id) {
  const p = currentPosts.find(x => x.id === id);
  if (!p) return;
  document.querySelectorAll('.post-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === id);
  });
  const detail = document.getElementById('postDetail');
  detail.innerHTML = `
    <div class="post-title">${escapeHtml(p.title)}${p.status ? `<span class="status-badge">${escapeHtml(p.status)}</span>` : ''}</div>
    <div class="post-meta"><b>${escapeHtml(p.author)}</b> · ${escapeHtml(p.board)} · ${escapeHtml(p.date)}</div>
    <div class="attachments">${p.attachments_html}</div>
    <div class="post-content">${p.content}</div>
    <div class="comments-section">
      <h3>💬 댓글 ${p.comment_count}개</h3>
      ${p.comments_html}
    </div>
  `;
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}
"""


def _prepare_posts_for_board(posts, board_key, image_manifest_by_post, file_manifest_by_post):
    import html as htmllib
    result = []
    for p in posts:
        atts_html = ""
        for name, path in image_manifest_by_post.get(p["id"], []):
            atts_html += f"<div class='att-img'><img src='{path}'><div class='att-name'>{htmllib.escape(name)}</div></div>"
        for name, path in file_manifest_by_post.get(p["id"], []):
            atts_html += f"<div class='att-file'><a href='{path}' target='_blank'>📎 {htmllib.escape(name)}</a></div>"
        comments = p.get("comments", [])
        comments_html = "".join(
            f"<div class='comment'><b>{htmllib.escape(c['author'])}</b><span class='c-time'>{htmllib.escape(c['time'])}</span>"
            f"<div class='c-text'>{htmllib.escape(c['text'])}</div></div>"
            for c in comments
        ) or "<div class='no-comment'>댓글이 없습니다.</div>"
        result.append({
            "id": p["id"],
            "title": p["title"],
            "author": p["author"],
            "date": p["created_at"],
            "status": p.get("status", ""),
            "board": _board_display_name(board_key),
            "content": p.get("content", "") or "",
            "attachments_html": atts_html,
            "comments_html": comments_html,
            "comment_count": len(comments),
        })
    result.sort(key=lambda x: x["date"], reverse=True)
    return result


def _extract_attachments(zf, posts):
    """게시글들의 첨부파일/이미지를 zip에 기록하고, 게시글 id별 매니페스트를 반환합니다."""
    image_manifest_by_post, file_manifest_by_post = {}, {}
    img_counter, file_counter = 1, 1
    for p in posts:
        for att in p.get("files", []) + p.get("images", []):
            try:
                raw = base64.b64decode(att["data"])
            except Exception:
                continue
            if att.get("type", "").startswith("image/"):
                rel_path = f"images/{img_counter:03d}_{att['name']}"
                zf.writestr(rel_path, raw)
                image_manifest_by_post.setdefault(p["id"], []).append((att["name"], rel_path))
                img_counter += 1
            else:
                rel_path = f"attach_files/{file_counter:03d}_{att['name']}"
                zf.writestr(rel_path, raw)
                file_manifest_by_post.setdefault(p["id"], []).append((att["name"], rel_path))
                file_counter += 1
    return image_manifest_by_post, file_manifest_by_post


def generate_backup_package(data, scope="all"):
    """attach_files / css / data / images / scripts 폴더 + index.html(게시판 형태) 구조의
    백업 패키지를 zip 바이트로 생성합니다.
    scope: "all"(전체) / "event"(온라인팀 행사) / "admin"(온라인팀 관리)"""
    import zipfile

    if scope == "event":
        posts_raw = [dict(p, _board="event") for p in data["event_posts"]]
        page_title = "온라인팀(행사) 백업"
    elif scope == "admin":
        posts_raw = [dict(p, _board="admin") for p in data["admin_posts"]]
        page_title = "온라인팀(관리) 백업"
    else:
        posts_raw = (
            [dict(p, _board="event") for p in data["event_posts"]]
            + [dict(p, _board="admin") for p in data["admin_posts"]]
        )
        page_title = "온라인팀 통합관리시스템 전체 백업"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if scope == "all":
            zf.writestr("data/backup_data.json", json.dumps(data, ensure_ascii=False, indent=2))
            schedule_lines = "\n".join(
                f"{s['title']} | {s['start']}~{s['end']} | {s['owner']} | {s['category']}"
                for s in data["schedules"]
            )
            zf.writestr("data/schedules.txt", schedule_lines or "등록된 일정이 없습니다.")
        else:
            key = "event_posts" if scope == "event" else "admin_posts"
            zf.writestr(f"data/{scope}_posts.json", json.dumps(data[key], ensure_ascii=False, indent=2))

        image_manifest_by_post, file_manifest_by_post = _extract_attachments(zf, posts_raw)

        posts_for_js = []
        for p in posts_raw:
            posts_for_js.extend(
                _prepare_posts_for_board([p], p["_board"], image_manifest_by_post, file_manifest_by_post)
            )
        posts_for_js.sort(key=lambda x: x["date"], reverse=True)

        zf.writestr("css/style.css", _board_css())
        zf.writestr("scripts/script.js", _board_js())
        zf.writestr("index.html", _build_board_html(page_title, posts_for_js))

    return buffer.getvalue()


def save_backup_file(data, scope="all"):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    suffix = {"all": "전체", "event": "행사", "admin": "관리"}.get(scope, scope)
    fname = f"backup_{suffix}_{kst_now().strftime('%Y%m%d_%H%M')}.zip"
    path = os.path.join(BACKUP_DIR, fname)
    with open(path, "wb") as f:
        f.write(generate_backup_package(data, scope=scope))
    return path


def maybe_auto_backup(data):
    """매주 금요일 밤 9시(KST) 이후 접속이 있을 때 자동으로 1회 백업합니다.
    (Streamlit은 상시 구동 스케줄러가 아니므로, 정확히 그 시각이 아니라
    그 이후 첫 접속 시점에 생성되는 '기회적' 백업입니다.)"""
    now = kst_now()
    if now.weekday() == 4 and now.hour >= 21:
        today_str = now.strftime("%Y-%m-%d")
        if data.get("last_auto_backup") != today_str:
            path = save_backup_file(data)
            data["last_auto_backup"] = today_str
            data["last_backup_path"] = path
            persist()


# --------------------------------------------------------------------------
# 캘린더 주간 블록 렌더링 (월간/주간 공용) - 색상 블록 클릭 시 상세 팝업
# --------------------------------------------------------------------------
def compute_month_lane_assignment(weeks, visible_schedules):
    """월 전체 기준으로 일정마다 고정된 레인 번호를 계산합니다.
    (주가 바뀌어도 같은 일정은 항상 같은 줄에 표시되도록)"""
    grid_start = weeks[0][0]
    grid_end = weeks[-1][-1]
    events_abs = []
    for s in visible_schedules:
        s_start = date.fromisoformat(s["start"])
        s_end = date.fromisoformat(s["end"])
        if s_end < grid_start or s_start > grid_end:
            continue
        abs_start = (max(s_start, grid_start) - grid_start).days
        abs_end = (min(s_end, grid_end) - grid_start).days
        events_abs.append((abs_start, abs_end, s))

    lanes = []  # list of list of (start,end) intervals already placed
    assignment = {}
    for abs_start, abs_end, s in sorted(events_abs, key=lambda x: (x[0], -(x[1] - x[0]))):
        lane_idx = None
        for li, intervals in enumerate(lanes):
            if all(abs_end < a or abs_start > b for a, b in intervals):
                lane_idx = li
                break
        if lane_idx is None:
            lanes.append([])
            lane_idx = len(lanes) - 1
        lanes[lane_idx].append((abs_start, abs_end))
        assignment[s["id"]] = lane_idx
    return assignment, len(lanes)


def render_week_block(
    week_dates, visible_schedules, data, week_key, current_month=None,
    lane_assignment=None, total_lanes=None,
):
    """월간/주간 캘린더의 한 주를 렌더링합니다.
    날짜 매칭 정확성을 위해 CSS 그리드 클래스 추정 대신 st.columns 비율을
    직접 계산해 배치합니다 (실제 날짜와 시각적 위치가 항상 정확히 일치).
    lane_assignment/total_lanes가 주어지면 월 전체 기준 고정 레인 번호를 사용해
    같은 일정이 주가 바뀌어도 항상 같은 줄에 표시되도록 합니다."""
    week_start, week_end = week_dates[0], week_dates[-1]
    week_events = []
    for s in visible_schedules:
        s_start = date.fromisoformat(s["start"])
        s_end = date.fromisoformat(s["end"])
        if s_end < week_start or s_start > week_end:
            continue
        col_start = max(0, (max(s_start, week_start) - week_start).days)
        col_end = min(6, (min(s_end, week_end) - week_start).days)
        week_events.append((col_start, col_end, s))

    if lane_assignment is not None and total_lanes is not None:
        lanes = [[] for _ in range(total_lanes)]
        for col_start, col_end, s in week_events:
            li = lane_assignment.get(s["id"])
            if li is not None and li < total_lanes:
                lanes[li].append((col_start, col_end, s))
        # 전역 레인 수를 그대로 쓰면 이번 주에 실제로 쓰이지 않는 레인까지
        # "숨겨진 레인"으로 잘못 계산되므로, 이번 주에 실제 내용이 있는
        # 마지막 레인까지만 유효 레인 수로 취급합니다.
        active_indices = [i for i, items in enumerate(lanes) if items]
        effective_lane_count = (max(active_indices) + 1) if active_indices else 0
    else:
        # 겹치지 않는 일정끼리 같은 줄(레인)에 묶기 (이 주만 기준으로 계산)
        lanes = []
        for col_start, col_end, s in sorted(week_events, key=lambda x: (x[0], -(x[1] - x[0]))):
            lane_idx = None
            for li, items in enumerate(lanes):
                if all(col_end < a or col_start > b for a, b, _ in items):
                    lane_idx = li
                    break
            if lane_idx is None:
                lanes.append([])
                lane_idx = len(lanes) - 1
            lanes[lane_idx].append((col_start, col_end, s))
        effective_lane_count = len(lanes)

    MAX_VISIBLE_LANES = 5
    show_all_key = f"{week_key}_showall"
    show_all = st.session_state.get(show_all_key, False)

    # "더보기"가 실제로 필요한지는 이 주 안에서 하루라도 실제로 겹치는 일정 수가
    # MAX_VISIBLE_LANES를 넘는지로 판단합니다 (전역 레인 번호가 높다고 해서
    # 실제 겹침이 없는데도 더보기가 뜨는 것을 방지).
    day_overlap_count = [0] * 7
    for col_start, col_end, s in week_events:
        for d_idx in range(col_start, col_end + 1):
            day_overlap_count[d_idx] += 1
    needs_hiding = (max(day_overlap_count) if week_events else 0) > MAX_VISIBLE_LANES

    if needs_hiding and not show_all:
        visible_lane_indices = list(range(min(effective_lane_count, MAX_VISIBLE_LANES)))
    else:
        visible_lane_indices = list(range(effective_lane_count))
    hidden_count = max(0, effective_lane_count - MAX_VISIBLE_LANES) if needs_hiding else 0

    wrap_key = f"{week_key}_wrap"
    st.markdown(
        f"<style>.st-key-{wrap_key} div[data-testid='stHorizontalBlock']"
        "{margin-top:1px !important;margin-bottom:1px !important;}"
        f".st-key-{wrap_key} div[data-testid='stVerticalBlock']"
        "{gap:1px !important;}</style>",
        unsafe_allow_html=True,
    )

    with st.container(key=wrap_key):
        # 날짜 숫자 버튼 줄 (7등분 - 항상 정확히 요일과 매칭됨)
        day_cols = st.columns(7)
        for i, d_ in enumerate(week_dates):
            day_cell_key = f"{week_key}_daycell_{i}"
            st.markdown(
                f"<style>.st-key-{day_cell_key} button {{font-size:10px !important;"
                "padding:0px 4px !important;min-height:15px !important;}}</style>",
                unsafe_allow_html=True,
            )
            with day_cols[i]:
                with st.container(key=day_cell_key):
                    if current_month is None or d_.month == current_month:
                        if st.button(str(d_.day), key=f"day_{week_key}_{d_.isoformat()}"):
                            open_new_schedule_dialog(d_)
                            st.rerun()
                    else:
                        st.markdown(
                            f"<div style='color:#ccc;font-size:10px;text-align:center'>{d_.day}</div>",
                            unsafe_allow_html=True,
                        )

        # 각 레인을 (여백/일정/여백 ...) 비율의 st.columns로 렌더링 -> 항상 정확한 날짜 위치
        for lane_idx in visible_lane_indices:
            items = lanes[lane_idx]
            if not items:
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)  # 빈 레인도 자리(줄 위치) 유지
                continue
            items = sorted(items, key=lambda x: x[0])
            segments = []  # (kind, width, schedule|None)
            cursor = 0
            for col_start, col_end, s in items:
                gap = col_start - cursor
                if gap > 0:
                    segments.append(("gap", gap, None))
                segments.append(("event", col_end - col_start + 1, s))
                cursor = col_end + 1
            trailing = 7 - cursor
            if trailing > 0:
                segments.append(("gap", trailing, None))

            lane_cols = st.columns([seg[1] for seg in segments])
            for col, (kind, _, s) in zip(lane_cols, segments):
                if kind != "event":
                    continue
                color = owner_color(s["owner"], data)
                cell_key = f"{week_key}_ev_{s['id']}"
                s_start = date.fromisoformat(s["start"])
                s_end = date.fromisoformat(s["end"])
                _today = kst_today()
                if s_start <= _today <= s_end:
                    status_icon = "🔵"  # 진행중
                elif s_start > _today:
                    status_icon = "⏳"  # 예정
                else:
                    status_icon = "✅"  # 종료
                st.markdown(
                    f"<style>.st-key-{cell_key} button {{background:{color} !important;"
                    "color:#333 !important;border:none !important;font-size:10px !important;"
                    "padding:0px 6px !important;min-height:15px !important;white-space:nowrap;overflow:hidden;"
                    "text-overflow:ellipsis;text-align:left !important;justify-content:flex-start !important;}"
                    f".st-key-{cell_key} button:hover {{filter:brightness(0.92);}}</style>",
                    unsafe_allow_html=True,
                )
                with col:
                    with st.container(key=cell_key):
                        if st.button(
                            f"{status_icon} {s['title']}", key=f"evbtn_{week_key}_{s['id']}", width="stretch"
                        ):
                            open_view_schedule_dialog(s["id"])
                            st.rerun()

        if hidden_count > 0:
            # 요일별 개별 더보기 버튼 대신, 주 오른쪽에 버튼 하나만 두고
            # 누르면 그 주 전체를 한 번에 펼칩니다.
            spacer_col, more_col = st.columns([7, 1])
            with more_col:
                if not show_all:
                    if st.button(f"+{hidden_count}개", key=f"{week_key}_more_btn", width="stretch"):
                        st.session_state[show_all_key] = True
                        st.rerun()
                else:
                    if st.button("접기", key=f"{week_key}_less_btn", width="stretch"):
                        st.session_state[show_all_key] = False
                        st.rerun()

        if not lanes:
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    st.markdown(
        "<hr style='margin:4px 0;border:none;border-top:1px solid #eee'>", unsafe_allow_html=True
    )


# --------------------------------------------------------------------------
# 사이드바
# --------------------------------------------------------------------------
data = get_data()
maybe_auto_backup(data)

if st.session_state.pop("_reset_vote_options", False):
    st.session_state["vote_options_text"] = ""

st.session_state.setdefault("page_radio", "대시보드")

_pending_nav = st.session_state.pop("_pending_nav", None)
if _pending_nav:
    st.session_state["page_radio"] = _pending_nav["page"]
    for k, v in _pending_nav["filters"].items():
        st.session_state[k] = v

with st.sidebar:
    _persisted_authed = st.session_state.get("authed_users", set())
    _persisted_user = st.session_state.get("current_user_select")
    if _persisted_user and _persisted_user in _persisted_authed:
        st.info(f"🔮 {_persisted_user}님의 오늘의 운세\n\n{get_daily_fortune(_persisted_user)}")

    if st.button("🔄 새로고침", width="stretch"):
        if "data" in st.session_state:
            del st.session_state["data"]
        st.rerun()

    st.markdown("## 🌐 온라인팀 통합관리시스템")
    st.markdown("#### 메뉴")
    page = st.radio(
        "메뉴", ["대시보드", "일정 관리", "온라인팀(행사)", "온라인팀(관리)", "구성원 관리"],
        label_visibility="collapsed", key="page_radio",
    )

# 페이지를 벗어나면 해당 페이지 전용 팝업은 자동으로 닫습니다
# (다른 화면으로 이동했는데 이전 팝업이 남아있는 문제 방지)
if page != "일정 관리":
    st.session_state["sched_dialog_open"] = False
if page != "온라인팀(관리)":
    st.session_state["_vote_empty_warning"] = False

with st.sidebar:
    st.markdown("---")
    st.markdown("##### 현재 사용자")
    names = sorted_member_names_by_position(data)
    authenticated_user = None
    if names:
        selected_name = st.selectbox("현재 사용자", names, label_visibility="collapsed", key="current_user_select")
        st.session_state.setdefault("authed_users", set())
        member_rec = next((m for m in data["members"] if m["name"] == selected_name), None)
        if selected_name in st.session_state.authed_users:
            authenticated_user = selected_name
            with st.expander("🔑 비밀번호 변경"):
                old_pw = st.text_input("현재 비밀번호", type="password", key=f"old_pw_{selected_name}")
                new_pw = st.text_input("새 비밀번호", type="password", key=f"new_pw_{selected_name}")
                if st.button("변경", key=f"change_pw_{selected_name}"):
                    if hash_pw(old_pw) == member_rec.get("password_hash", DEFAULT_PW_HASH):
                        if new_pw.strip():
                            member_rec["password_hash"] = hash_pw(new_pw)
                            persist()
                            st.success("비밀번호가 변경되었습니다.")
                        else:
                            st.warning("새 비밀번호를 입력해주세요.")
                    else:
                        st.error("현재 비밀번호가 올바르지 않습니다.")
        else:
            st.caption("사용자 확인을 위해 비밀번호를 입력해주세요. (초기 비밀번호: MOOAS1234)")
            pw_input = st.text_input("비밀번호", type="password", key=f"pw_input_{selected_name}")
            if st.button("확인", key=f"pw_confirm_{selected_name}"):
                if hash_pw(pw_input) == member_rec.get("password_hash", DEFAULT_PW_HASH):
                    st.session_state.authed_users.add(selected_name)
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
    else:
        st.info("구성원 관리에서 먼저 구성원을 추가해주세요.")

    current_user = authenticated_user

    # 바로가기: 순수 HTML/JS 드롭다운으로 만들어서, Streamlit 서버 왕복(rerun) 없이
    # 선택하는 즉시(같은 사용자 동작 안에서) 새 창이 열리도록 합니다.
    # (일반 st.selectbox로 만들면 선택 → 서버 재실행 → 새 창 열기 순서가 되어 브라우저의
    # 팝업 차단 정책에 걸리지만, 이 방식은 선택과 창 열기가 브라우저 안에서 한 번에
    # 일어나므로 팝업 차단을 받지 않습니다.)
    SHORTCUT_LINKS = {
        "무아스 스마트스토어": "https://brand.naver.com/mooas",
        "교보핫트랙스 어드민": "https://admin.hottracks.co.kr/admin/login/form",
        "샵바이 파트너 어드민": "https://partner.shopby.co.kr/login",
        "스룩": "https://srookpay.com/",
    }
    st.markdown("---")
    st.markdown("##### 🔗 바로가기")
    _shortcut_options_html = "".join(
        f'<option value="{url}">{name}</option>' for name, url in SHORTCUT_LINKS.items()
    )
    _shortcut_html = f"""
        <html><head><style>
        html, body {{ margin:0; padding:0; overflow:hidden; }}
        select {{
            width:100%; padding:8px 10px; border-radius:6px; border:1px solid #d0d0d0;
            font-size:14px; font-family:inherit; background:#f0f2f6; color:#333;
            box-sizing:border-box; display:block;
        }}
        </style></head><body>
        <select onchange="if(this.value){{window.open(this.value, '_blank');}} this.selectedIndex=0;">
          <option value="" selected>바로가기 선택...</option>
          {_shortcut_options_html}
        </select>
        </body></html>
        """
    st.iframe(
        "data:text/html;charset=utf-8," + urllib.parse.quote(_shortcut_html),
        height=40,
    )

    if current_user:
        pending_votes = [
            p for p in data["admin_posts"]
            if p.get("vote") and current_user not in {v for o in p["vote"]["options"] for v in o["voters"]}
        ]
        if pending_votes:
            st.markdown("---")
            st.markdown("##### ⚠️ 확인이 필요한 게시글")
            for p in pending_votes[:6]:
                if st.button(f"🗳️ {p['title']}", key=f"pending_jump_{p['id']}", width="stretch"):
                    go_to(
                        "온라인팀(관리)", admin_view_filter="전체", admin_quick_filter="없음",
                        _highlight_post_id=p["id"],
                    )

        my_notifs = [n for n in data.get("notifications", []) if n["user"] == current_user]
        if my_notifs:
            st.markdown("---")
            st.markdown("##### 🔔 알림")
            for n in my_notifs[:8]:
                if st.button(n["message"], key=f"notif_{n['id']}", width="stretch"):
                    data["notifications"] = [x for x in data["notifications"] if x["id"] != n["id"]]
                    persist()
                    target_page = "온라인팀(행사)" if n["board"] == "event" else "온라인팀(관리)"
                    highlight_kwargs = {"_highlight_post_id": n["post_id"]}
                    if target_page == "온라인팀(행사)":
                        highlight_kwargs["event_filter_status"] = "전체"
                    else:
                        highlight_kwargs["admin_view_filter"] = "전체"
                        highlight_kwargs["admin_quick_filter"] = "없음"
                    go_to(target_page, **highlight_kwargs)

    st.markdown("---")
    st.caption(f"ⓒ {kst_today().year} {COPYRIGHT_OWNER} All Rights Reserved.")
    st.caption(f"배포 버전: {APP_VERSION} RELEASE ({APP_BUILD_DATE})")
    st.caption("First version distributed by online team CHEA")

if names and current_user is None:
    st.title("🌐 온라인팀 통합관리시스템")
    st.info("왼쪽 사이드바에서 사용자를 선택하고 비밀번호를 확인해주세요.")
    st.stop()

# --------------------------------------------------------------------------
# 공통: 일정 등록/조회 팝업 (st.dialog)
# --------------------------------------------------------------------------
if "sched_dialog_open" not in st.session_state:
    st.session_state.sched_dialog_open = False
if "sched_dialog_date" not in st.session_state:
    st.session_state.sched_dialog_date = None
if "sched_dialog_edit_id" not in st.session_state:
    st.session_state.sched_dialog_edit_id = None


def open_new_schedule_dialog(d):
    st.session_state.sched_dialog_open = True
    st.session_state.sched_dialog_date = d
    st.session_state.sched_dialog_edit_id = None


def open_view_schedule_dialog(sched_id):
    st.session_state.sched_dialog_open = True
    st.session_state.sched_dialog_edit_id = sched_id
    st.session_state.sched_dialog_date = None


def _close_schedule_dialog():
    st.session_state.sched_dialog_open = False


@st.dialog("일정", on_dismiss=_close_schedule_dialog)
def schedule_dialog():
    d = get_data()
    edit_id = st.session_state.sched_dialog_edit_id
    editing_existing = edit_id is not None
    sched = None
    if editing_existing:
        sched = next((s for s in d["schedules"] if s["id"] == edit_id), None)
        if sched is None:
            st.session_state.sched_dialog_open = False
            st.rerun()

    edit_mode_key = f"edit_mode_{edit_id or 'new'}"
    if editing_existing and edit_mode_key not in st.session_state:
        st.session_state[edit_mode_key] = False

    if editing_existing and not st.session_state[edit_mode_key]:
        st.markdown(f"### {sched['title']}")
        st.write(f"**기간** : {sched['start']} ~ {sched['end']}")
        st.write(f"**담당자** : {sched['owner']}  ·  **구분** : {sched['category']}")
        if sched.get("memo"):
            st.write("**메모**")
            st.info(sched["memo"].replace("\n", "  \n"))
        c1, c2, c3 = st.columns([1, 1, 3])
        if c1.button("✏️ 수정", width="stretch"):
            st.session_state[edit_mode_key] = True
            st.rerun()
        if c2.button("🗑️ 삭제", width="stretch"):
            d["schedules"] = [s for s in d["schedules"] if s["id"] != edit_id]
            persist()
            st.session_state.sched_dialog_open = False
            st.rerun()
        return

    default_title = sched["title"] if sched else ""
    default_start = date.fromisoformat(sched["start"]) if sched else (
        st.session_state.sched_dialog_date or kst_today()
    )
    default_end = date.fromisoformat(sched["end"]) if sched else default_start
    owner_options = owner_names_combined(d)
    default_owner = sched["owner"] if sched else (current_user or (owner_options[0] if owner_options else ""))
    default_cat = sched["category"] if sched else "개인"
    default_memo = sched["memo"] if sched else ""

    title = st.text_input("제목", value=default_title)
    dcol1, dcol2 = st.columns(2)
    start_d = dcol1.date_input("시작일", value=default_start)
    end_d = dcol2.date_input("종료일", value=max(default_end, start_d), min_value=start_d)
    owner = st.selectbox(
        "담당자 / 캘린더", owner_options,
        index=owner_options.index(default_owner) if default_owner in owner_options else 0,
    )
    render_color_legend(owner_options, d)
    category = st.selectbox("구분", CATEGORY_LIST, index=CATEGORY_LIST.index(default_cat))
    memo = st.text_area("메모", value=default_memo, height=100)

    b1, b2 = st.columns(2)
    if b1.button("저장", type="primary", width="stretch"):
        if not title.strip():
            st.warning("제목을 입력해주세요.")
        else:
            if editing_existing:
                sched.update(
                    title=title.strip(), start=start_d.isoformat(), end=end_d.isoformat(),
                    owner=owner, category=category, memo=memo,
                )
            else:
                d["schedules"].append(
                    {"id": new_id(), "title": title.strip(), "start": start_d.isoformat(),
                     "end": end_d.isoformat(), "owner": owner, "category": category, "memo": memo}
                )
            persist()
            st.session_state.sched_dialog_open = False
            if editing_existing:
                st.session_state[edit_mode_key] = False
            st.rerun()
    if b2.button("취소", width="stretch"):
        st.session_state.sched_dialog_open = False
        if editing_existing:
            st.session_state[edit_mode_key] = False
        st.rerun()


if st.session_state.sched_dialog_open:
    schedule_dialog()


@st.dialog("투표 확인", on_dismiss=lambda: st.session_state.update({"_vote_empty_warning": False}))
def vote_empty_warning_dialog():
    st.warning("선택지를 선택한 후 투표를 완료해주세요.")
    if st.button("확인", type="primary"):
        st.session_state["_vote_empty_warning"] = False
        st.rerun()


if st.session_state.get("_vote_empty_warning"):
    vote_empty_warning_dialog()

# --------------------------------------------------------------------------
# 댓글 렌더링 (수정/삭제/답변/멘션 지원)
# --------------------------------------------------------------------------
def render_comments(p, board_name, current_user, data):
    comments = p.setdefault("comments", [])
    by_parent = {}
    for c in comments:
        by_parent.setdefault(c.get("parent_id"), []).append(c)

    def render_one(c, indent=0):
        editing = st.session_state.get(f"editcm_{c['id']}", False)
        prefix = "&nbsp;&nbsp;&nbsp;&nbsp;" * indent
        text_col, btn_group = st.columns([9, 3])
        with text_col:
            if editing:
                pass
            else:
                st.markdown(f"{prefix}**{c['author']}** ({c['time']}): {c['text']}", unsafe_allow_html=True)
        with btn_group:
            c2, c3, c4 = st.columns([1, 1, 1], gap="xxsmall")
            with c2:
                if st.button("답변", key=f"replybtn_{c['id']}"):
                    st.session_state[f"replying_{c['id']}"] = not st.session_state.get(f"replying_{c['id']}", False)
            if c["author"] == current_user:
                with c3:
                    if not editing:
                        if st.button("수정", key=f"cmeditbtn_{c['id']}"):
                            st.session_state[f"editcm_{c['id']}"] = True
                            st.rerun()
                with c4:
                    if st.button("삭제", key=f"cmdel_{c['id']}"):
                        p["comments"] = [x for x in p["comments"] if x["id"] != c["id"]]
                        add_change_log(data, current_user, "삭제", "댓글", c["text"][:30], board_name)
                        persist()
                        st.rerun()

        if editing:
            new_text = st.text_input(
                "댓글 수정", value=c["text"], key=f"cmedittext_{c['id']}", label_visibility="collapsed"
            )
            if st.button("저장", key=f"cmsave_{c['id']}"):
                add_change_log(data, current_user, "수정", "댓글", c["text"][:30], board_name)
                c["text"] = new_text
                persist()
                st.session_state[f"editcm_{c['id']}"] = False
                st.rerun()

        if st.session_state.get(f"replying_{c['id']}"):
            reply_default = f"@{c['author']} "
            reply_text = st.text_input(
                "답변 작성", value=reply_default, key=f"replytext_{c['id']}", label_visibility="collapsed"
            )
            if st.button("답변 등록", key=f"replysubmit_{c['id']}"):
                if reply_text.strip():
                    new_c = {
                        "id": new_id(), "author": current_user, "text": reply_text.strip(),
                        "time": now_str(), "parent_id": c["id"],
                    }
                    p["comments"].append(new_c)
                    if current_user != p["author"]:
                        add_notification(data, p["author"], f"[{p['title']}]에 댓글이 달렸습니다.", board_name, p["id"])
                    for m in extract_mentions(reply_text, data) - {current_user}:
                        add_notification(data, m, f"[{p['title']}] 댓글에서 멘션되었습니다.", board_name, p["id"])
                    persist()
                    st.session_state[f"replying_{c['id']}"] = False
                    st.rerun()

        for child in by_parent.get(c["id"], []):
            render_one(child, indent + 1)

    for c in by_parent.get(None, []):
        render_one(c, 0)

    new_comment = st.text_input(
        "댓글 작성 (@이름으로 멘션 가능)", key=f"comment_input_{board_name}_{p['id']}",
        label_visibility="collapsed", placeholder="댓글을 입력하세요 (@이름 으로 멘션 가능)",
    )
    if st.button("댓글 등록", key=f"comment_btn_{board_name}_{p['id']}"):
        if new_comment.strip():
            p["comments"].append(
                {"id": new_id(), "author": current_user, "text": new_comment.strip(),
                 "time": now_str(), "parent_id": None}
            )
            if current_user != p["author"]:
                add_notification(data, p["author"], f"[{p['title']}]에 댓글이 달렸습니다.", board_name, p["id"])
            for m in extract_mentions(new_comment, data) - {current_user}:
                add_notification(data, m, f"[{p['title']}] 댓글에서 멘션되었습니다.", board_name, p["id"])
            persist()
            st.rerun()


# --------------------------------------------------------------------------
# 페이지: 대시보드
# --------------------------------------------------------------------------
if page == "대시보드":
    header_col, weather_col = st.columns([2, 1])
    with header_col:
        st.markdown("# 🌐 온라인팀 통합관리시스템")
        st.caption("일정 · 안건 · 투표를 한 곳에서 관리합니다.")
    with weather_col:
        _weather = fetch_songpa_weather()
        if _weather:
            _emoji = weather_condition_to_emoji(_weather["condition"])
            st.markdown(
                f"""
                <div style='border:1px solid #eee;border-radius:12px;padding:12px 18px;
                            display:flex;align-items:center;gap:14px;background:#fafbfc;
                            margin-top:8px'>
                    <div style='font-size:40px;line-height:1'>{_emoji}</div>
                    <div>
                        <div style='font-size:12px;color:#888'>
                            📍 송파구 문정동 · {kst_now().strftime('%H:%M')} KST
                        </div>
                        <div style='font-size:20px;font-weight:700;color:#222'>{_weather['temp']}</div>
                        <div style='font-size:11.5px;color:#666'>
                            체감 {_weather['feels_like']} · 습도 {_weather['humidity']} · 바람 {_weather['wind']}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.caption("📍 송파구 문정동 날씨: 정보를 불러오지 못했습니다. (네트워크 연결을 확인해주세요)")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        dash_metric(
            "🗓️ 진행중 일정",
            len([
                s for s in data["schedules"]
                if date.fromisoformat(s["start"]) <= kst_today() <= date.fromisoformat(s["end"])
            ]),
            "일정 관리", week_anchor=kst_today(),
        )
    with dc2:
        dash_metric(
            "📅 예정된 일정",
            len([s for s in data["schedules"] if date.fromisoformat(s["start"]) > kst_today()]),
            "일정 관리", week_anchor=kst_today() + timedelta(days=7),
        )
    with dc3:
        dash_metric(
            "📢 등록된 공지", len([p for p in data["admin_posts"] if p.get("status") == "공지"]),
            "온라인팀(관리)", admin_view_filter="공지", admin_quick_filter="없음",
        )

    st.markdown("#### 📌 온라인팀(행사)")
    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        dash_metric("💡 제안 중 행사", len([p for p in data["event_posts"] if p["status"] == "제안"]),
                    "온라인팀(행사)", event_filter_status="제안")
    with ec2:
        dash_metric("🔄 진행 중 행사", len([p for p in data["event_posts"] if p["status"] == "진행"]),
                    "온라인팀(행사)", event_filter_status="진행")
    with ec3:
        dash_metric("🏁 종료된 행사", len([p for p in data["event_posts"] if p["status"] == "종료"]),
                    "온라인팀(행사)", event_filter_status="종료")

    st.markdown("#### ⚙️ 온라인팀(관리)")
    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        dash_metric(
            "📝 등록",
            len([
                p for p in data["admin_posts"]
                if p.get("status", "등록") not in ("공지", "완료") and not vote_started(p)
            ]),
            "온라인팀(관리)", admin_view_filter="전체", admin_quick_filter="진행중",
        )
    with ac2:
        dash_metric(
            "🗳️ 투표 진행중",
            len([p for p in data["admin_posts"] if vote_started(p) and not vote_all_voted(p, data)]),
            "온라인팀(관리)", admin_view_filter="전체", admin_quick_filter="투표 진행중",
        )
    with ac3:
        dash_metric(
            "⏳ 완료 처리 필요",
            len([p for p in data["admin_posts"] if vote_all_voted(p, data) and p.get("status") != "완료"]),
            "온라인팀(관리)", admin_view_filter="전체", admin_quick_filter="완료처리필요",
        )

    st.markdown("### 🗓️ 오늘 이후 일정")
    my_only_dash = st.checkbox("내 일정만 보기", key="dash_my_only")
    today = kst_today()
    upcoming = [s for s in data["schedules"] if date.fromisoformat(s["end"]) >= today]
    if my_only_dash and current_user:
        upcoming = [s for s in upcoming if s["owner"] == current_user]
    upcoming.sort(key=lambda s: s["start"])
    if upcoming:
        rows = [
            {"제목": s["title"], "기간": f"{s['start']} ~ {s['end']}", "담당자": s["owner"], "구분": s["category"]}
            for s in upcoming
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("등록된 예정 일정이 없습니다.")

    st.markdown("---")
    left_col, _ = st.columns([1, 3])
    with left_col:
        st.markdown("##### 💾 백업")
        st.caption(
            "게시판 형태(좌측 글 목록 + 상세보기)의 index.html이 포함된 zip으로 생성됩니다. "
            "전체 또는 게시판별로 따로 받을 수 있습니다."
        )
        backup_scope = st.selectbox(
            "백업 범위", ["전체", "온라인팀(행사)", "온라인팀(관리)"], key="backup_scope_select",
        )
        scope_map = {"전체": "all", "온라인팀(행사)": "event", "온라인팀(관리)": "admin"}
        selected_scope = scope_map[backup_scope]

        if st.button("지금 백업하기", key="manual_backup_btn"):
            path = save_backup_file(data, scope=selected_scope)
            data["last_backup_path"] = path
            persist()
            st.success(f"'{backup_scope}' 백업이 생성되었습니다.")
        last_path = data.get("last_backup_path")
        if last_path and os.path.exists(last_path):
            with open(last_path, "rb") as f:
                st.download_button(
                    "⬇️ 최근 백업파일 다운받기", data=f.read(),
                    file_name=os.path.basename(last_path), mime="application/zip",
                    key="download_backup_btn",
                )
        else:
            st.caption("아직 생성된 백업이 없습니다.")

    st.markdown("---")
    with st.expander("📜 최근 변경 로그 (게시글·댓글 수정/삭제 이력)"):
        logs = sorted(data.get("change_logs", []), key=lambda l: l["time"], reverse=True)
        if logs:
            for lg in logs[:30]:
                board_label = {"event": "온라인팀(행사)", "admin": "온라인팀(관리)"}.get(lg.get("board"), "")
                st.markdown(
                    f"- `{lg['time']}` **{lg['user']}** — {lg['target_type']} {lg['action']}"
                    f" ({board_label}): {lg['title']}"
                )
        else:
            st.caption("변경 이력이 없습니다.")

# --------------------------------------------------------------------------
# 페이지: 일정 관리
# --------------------------------------------------------------------------
elif page == "일정 관리":
    st.markdown("# 🗓️ 일정 관리")

    search_q = st.text_input("🔍 검색 (제목/메모)", key="sched_search").strip().lower()

    colA, colB, colC = st.columns([1, 1, 2])
    with colA:
        filter_members = st.multiselect(
            "구성원/캘린더 필터 (비워두면 전체)", owner_names_combined(data), key="sched_filter_members"
        )
    with colB:
        my_only_sched = st.checkbox("내 일정만 보기", key="sched_my_only")
    with colC:
        legend_items = [
            f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
            f"background:{owner_color(n, data)};margin-right:3px'></span>{n}"
            for n in owner_names_combined(data)
        ]
        st.markdown(
            "<div style='font-size:12px;color:#555'>" + "&nbsp;&nbsp;".join(legend_items) + "</div>",
            unsafe_allow_html=True,
        )

    visible_schedules = data["schedules"]
    if filter_members:
        visible_schedules = [s for s in visible_schedules if s["owner"] in filter_members]
    if my_only_sched and current_user:
        visible_schedules = [s for s in visible_schedules if s["owner"] == current_user]
    if search_q:
        visible_schedules = [
            s for s in visible_schedules
            if search_q in s["title"].lower() or search_q in s.get("memo", "").lower()
        ]

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["월간 일정 보기", "주간 일정 보기", "목록보기", "일정 등록", "기타 캘린더"]
    )

    with tab1:
        c1, c2 = st.columns(2)
        if "cal_year" not in st.session_state:
            st.session_state.cal_year = kst_today().year
        if "cal_month" not in st.session_state:
            st.session_state.cal_month = kst_today().month

        with c1:
            st.write("연도")
            y1, y2, y3 = st.columns([1, 2, 1])
            if y1.button("−", key="y_minus"):
                st.session_state.cal_year -= 1
                st.rerun()
            year_options = list(range(kst_today().year - 5, kst_today().year + 6))
            if st.session_state.cal_year not in year_options:
                year_options.append(st.session_state.cal_year)
                year_options.sort()
            new_year = y2.selectbox(
                "연도 선택", year_options, index=year_options.index(st.session_state.cal_year),
                label_visibility="collapsed",
            )
            if new_year != st.session_state.cal_year:
                st.session_state.cal_year = new_year
                st.rerun()
            if y3.button("＋", key="y_plus"):
                st.session_state.cal_year += 1
                st.rerun()
        with c2:
            st.write("월")
            m1, m2, m3 = st.columns([1, 2, 1])
            if m1.button("−", key="m_minus"):
                st.session_state.cal_month -= 1
                if st.session_state.cal_month < 1:
                    st.session_state.cal_month = 12
                    st.session_state.cal_year -= 1
                st.rerun()
            new_month = m2.selectbox(
                "월 선택", list(range(1, 13)), index=st.session_state.cal_month - 1,
                label_visibility="collapsed",
            )
            if new_month != st.session_state.cal_month:
                st.session_state.cal_month = new_month
                st.rerun()
            if m3.button("＋", key="m_plus"):
                st.session_state.cal_month += 1
                if st.session_state.cal_month > 12:
                    st.session_state.cal_month = 1
                    st.session_state.cal_year += 1
                st.rerun()

        st.caption("날짜를 클릭하면 일정 등록 팝업이, 색상 블록을 클릭하면 상세 팝업이 열립니다.")
        st.caption("🔵 진행중  ·  ⏳ 예정  ·  ✅ 종료  (일정 앞 아이콘, 오늘 기준 KST)")

        year = st.session_state.cal_year
        month = st.session_state.cal_month
        calendar_obj = cal.Calendar(firstweekday=6)
        weeks = calendar_obj.monthdatescalendar(year, month)

        weekday_labels = ["일", "월", "화", "수", "목", "금", "토"]
        header_cols = st.columns(7)
        for i, wl in enumerate(weekday_labels):
            color = "#d33" if i == 0 else ("#36c" if i == 6 else "#333")
            header_cols[i].markdown(
                f"<div style='text-align:center;font-weight:600;color:{color}'>{wl}</div>",
                unsafe_allow_html=True,
            )

        month_lane_assignment, month_total_lanes = compute_month_lane_assignment(weeks, visible_schedules)
        for week_idx, week in enumerate(weeks):
            render_week_block(
                week, visible_schedules, data,
                week_key=f"monthgrid_{year}_{month}_{week_idx}", current_month=month,
                lane_assignment=month_lane_assignment, total_lanes=month_total_lanes,
            )

    with tab2:
        if "week_anchor" not in st.session_state:
            st.session_state.week_anchor = kst_today()
        wc1, wc2, wc3 = st.columns([1, 2, 1])
        if wc1.button("◀ 이전 주"):
            st.session_state.week_anchor -= timedelta(days=7)
            st.rerun()
        anchor = st.session_state.week_anchor
        delta = (anchor.weekday() + 1) % 7
        week_start = anchor - timedelta(days=delta)
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        wc2.markdown(
            f"<h4 style='text-align:center'>{week_dates[0].strftime('%Y-%m-%d')} ~ {week_dates[-1].strftime('%Y-%m-%d')}</h4>",
            unsafe_allow_html=True,
        )
        if wc3.button("다음 주 ▶"):
            st.session_state.week_anchor += timedelta(days=7)
            st.rerun()

        weekday_labels = ["일", "월", "화", "수", "목", "금", "토"]
        header_cols = st.columns(7)
        for i, wl in enumerate(weekday_labels):
            color = "#d33" if i == 0 else ("#36c" if i == 6 else "#333")
            header_cols[i].markdown(
                f"<div style='text-align:center;font-weight:600;color:{color}'>{wl}</div>",
                unsafe_allow_html=True,
            )
        render_week_block(
            week_dates, visible_schedules, data,
            week_key=f"weekview_{week_start.strftime('%Y%m%d')}", current_month=None,
        )

    with tab3:
        st.markdown("#### 📋 전체 일정 목록 (시작일순, 시작일은 볼드체로 표기)")
        lf1, lf2 = st.columns(2)
        year_choices = ["전체"] + list(range(kst_today().year - 5, kst_today().year + 6))
        list_year = lf1.selectbox("연도", year_choices, key="list_year_filter")
        list_month = lf2.selectbox("월", ["전체"] + list(range(1, 13)), key="list_month_filter")

        def _schedule_year_months(s):
            s_start = date.fromisoformat(s["start"])
            s_end = date.fromisoformat(s["end"])
            months = set()
            y, m = s_start.year, s_start.month
            while (y, m) <= (s_end.year, s_end.month):
                months.add((y, m))
                m += 1
                if m > 12:
                    m = 1
                    y += 1
            return months

        listed = sorted(visible_schedules, key=lambda s: s["start"])
        if list_year != "전체" or list_month != "전체":
            filtered_listed = []
            for s in listed:
                yms = _schedule_year_months(s)
                ok = True
                if list_year != "전체" and not any(y == list_year for y, _ in yms):
                    ok = False
                if list_month != "전체" and not any(m == list_month for _, m in yms):
                    ok = False
                if ok:
                    filtered_listed.append(s)
            listed = filtered_listed

        if listed:
            for s in listed:
                color = owner_color(s["owner"], data)
                st.markdown(
                    f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
                    f"background:{color};margin-right:6px'></span>"
                    f"**{s['start']}** ~ {s['end']} · **{s['title']}** · {s['owner']} ({s['category']})",
                    unsafe_allow_html=True,
                )
                cbtn1, cbtn2 = st.columns([8, 1])
                if cbtn2.button("상세보기", key=f"list_view_{s['id']}"):
                    open_view_schedule_dialog(s["id"])
                    st.rerun()
        else:
            st.caption("표시할 일정이 없습니다.")

    with tab4:
        st.markdown("#### 새 일정 등록")
        title = st.text_input("제목", key="direct_title")
        dcol1, dcol2 = st.columns(2)
        st.session_state.setdefault("direct_start", kst_today())
        s_d = dcol1.date_input("시작일", key="direct_start")
        # 키가 있는 위젯은 이전에 저장된 값이 새 min_value보다 이전일 경우 충돌이 나므로 미리 보정합니다.
        st.session_state.setdefault("direct_end", kst_today())
        if st.session_state["direct_end"] < s_d:
            st.session_state["direct_end"] = s_d
        e_d = dcol2.date_input("종료일", key="direct_end", min_value=s_d)
        owner_opts = owner_names_combined(data)
        owner = st.selectbox("담당자 / 캘린더", owner_opts, key="direct_owner") if owner_opts else None
        if owner_opts:
            render_color_legend(owner_opts, data)
        category = st.selectbox("구분", CATEGORY_LIST, key="direct_category")
        memo = st.text_area("메모", key="direct_memo")
        if st.button("일정 등록", type="primary"):
            if not title.strip():
                st.warning("제목을 입력해주세요.")
            else:
                data["schedules"].append(
                    {"id": new_id(), "title": title.strip(), "start": s_d.isoformat(),
                     "end": e_d.isoformat(), "owner": owner, "category": category, "memo": memo}
                )
                persist()
                st.success("일정이 등록되었습니다.")
                st.rerun()

    with tab5:
        st.markdown("### 🗓️ 기타 캘린더")
        st.caption("구성원 개인 일정 외에, 공용/기타 목적의 캘린더를 추가로 만들 수 있습니다. "
                   "추가 → 이름 수정 → 색상 지정 순서로 설정해주세요.")
        if st.button("+ 캘린더 추가"):
            used = {m["color"] for m in data["members"]} | {c["color"] for c in data.get("calendars", [])}
            avail = [hexcode for _, hexcode in PRESET_COLORS if hexcode not in used]
            new_color = avail[0] if avail else "#999999"
            idx = len(data.get("calendars", [])) + 1
            data.setdefault("calendars", []).append(
                {"id": new_id(), "name": f"새 캘린더 {idx}", "color": new_color}
            )
            persist()
            st.rerun()

        for c in data.get("calendars", []):
            cc1, cc2, cc3 = st.columns([3, 2, 1])
            with cc1:
                new_cal_name = st.text_input(
                    "이름", value=c["name"], key=f"cal_name_{c['id']}", label_visibility="collapsed"
                )
            with cc2:
                new_cal_color = st.color_picker(
                    "색상", value=c["color"], key=f"cal_color_{c['id']}", label_visibility="collapsed"
                )
            if new_cal_name != c["name"] or new_cal_color != c["color"]:
                c["name"] = new_cal_name
                c["color"] = new_cal_color
                persist()
            if cc3.button("삭제", key=f"cal_del_{c['id']}"):
                data["calendars"] = [x for x in data["calendars"] if x["id"] != c["id"]]
                persist()
                st.rerun()

# --------------------------------------------------------------------------
# 페이지: 온라인팀(행사)
# --------------------------------------------------------------------------
elif page == "온라인팀(행사)":
    st.markdown("# 📝 온라인팀(행사)")
    st.caption("행사와 관련된 아이디어, 진행 사항, 선정 결과를 관리합니다.")

    search_q = st.text_input("🔍 검색 (제목/내용/파일명)", key="event_search").strip().lower()

    filter_status = st.radio(
        "보기", ["전체"] + STATUS_LIST, horizontal=True, key="event_filter_status",
        format_func=lambda s: s if s == "전체" else f"{STATUS_ICONS.get(s, '')} {s}",
    )
    fc1, fc2 = st.columns([1, 1])
    with fc1:
        only_mine = st.checkbox("내가 쓴 글만 보기")
    with fc2:
        part_filter = st.selectbox("파트별 보기", ["전체"] + PART_OPTIONS, key="event_part_filter")

    if filter_status == "제안":
        if st.button("➕ 새 행사 게시글 작성", key="toggle_new_event_form"):
            st.session_state["show_new_event_form"] = not st.session_state.get("show_new_event_form", False)

        if st.session_state.get("show_new_event_form"):
            with st.container(border=True):
                st.markdown("#### ➕ 새 행사 게시글 작성 (상태: 💡 제안)")
                e_title = st.text_input("제목", key="new_event_title")
                e_content = rich_text_input("내용", key="new_event_content")
                e_files = st.file_uploader(
                    "첨부파일 (이미지 포함, 드래그앤드롭 지원)", accept_multiple_files=True, key="new_event_files"
                )
                if st.button("게시글 등록", type="primary", key="submit_event_post"):
                    if not e_title.strip():
                        st.warning("제목을 입력해주세요.")
                    else:
                        final_content = e_content or ""
                        data["event_posts"].append(
                            {
                                "id": new_id(), "title": e_title.strip(), "status": "제안",
                                "content": final_content, "images": [],
                                "files": [file_to_b64(f_) for f_ in (e_files or [])],
                                "author": current_user, "created_at": now_str(), "comments": [],
                            }
                        )
                        persist()
                        st.session_state["show_new_event_form"] = False
                        st.success("게시글이 등록되었습니다.")
                        st.rerun()
    else:
        st.caption("새 게시글 작성은 '제안' 탭에서만 가능합니다.")

    st.markdown("---")

    # 최신 등록 글이 위로 오도록 (등록 순서 그대로 뒤집음 - 같은 분에 여러 개 등록돼도 정확)
    posts = list(reversed(data["event_posts"]))
    shown = [p for p in posts if (filter_status == "전체" or p["status"] == filter_status)]
    if only_mine:
        shown = [p for p in shown if p["author"] == current_user]
    if part_filter != "전체":
        pmap = member_part_map(data)
        shown = [p for p in shown if pmap.get(p["author"]) == part_filter]
    if search_q:
        def _match(p):
            atts = p.get("files", []) + p.get("images", [])
            return (
                search_q in p["title"].lower() or search_q in p.get("content", "").lower()
                or any(search_q in a["name"].lower() for a in atts)
            )
        shown = [p for p in shown if _match(p)]

    highlight_id = st.session_state.pop("_highlight_post_id", None)
    if highlight_id:
        matched = [p for p in shown if p["id"] == highlight_id]
        others = [p for p in shown if p["id"] != highlight_id]
        shown = matched + others

    if not shown:
        st.info("표시할 게시글이 없습니다.")

    for p in shown:
        if highlight_id and p["id"] == highlight_id:
            st.markdown(
                "<div style='background:#FFF7D6;border-left:4px solid #F5B301;"
                "padding:4px 10px;border-radius:4px;margin-bottom:-4px;font-size:12.5px'>"
                "🔎 확인하러 온 게시글</div>", unsafe_allow_html=True,
            )
        with st.container(border=True):
            status_col, spacer_col, btn_group = st.columns([3, 5, 2])
            with status_col:
                new_status = st.selectbox(
                    "상태", STATUS_LIST, index=STATUS_LIST.index(p["status"]),
                    format_func=lambda s: f"{STATUS_ICONS.get(s, '')} {s}",
                    key=f"status_{p['id']}", label_visibility="collapsed",
                )
                if new_status != p["status"]:
                    old_status = p["status"]
                    p["status"] = new_status
                    if current_user != p["author"]:
                        add_notification(data, p["author"], f"[{p['title']}]의 상태가 변경되었습니다.", "event", p["id"])
                    persist()
                    st.rerun()
            if p["author"] == current_user:
                with btn_group:
                    edit_col, del_col = st.columns([1, 1], gap="xxsmall")
                    edit_key = f"editing_event_{p['id']}"
                    if edit_col.button("수정", key=f"edit_btn_{p['id']}"):
                        st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                        st.rerun()
                    if del_col.button("삭제", key=f"del_btn_{p['id']}"):
                        add_change_log(data, current_user, "삭제", "게시글", p["title"], "event")
                        data["event_posts"] = [x for x in data["event_posts"] if x["id"] != p["id"]]
                        persist()
                        st.rerun()

            st.markdown(f"### {p['title']}")
            st.caption(f"작성자 {p['author']} · {p['created_at']}")

            existing_atts = p.get("files", []) + p.get("images", [])

            if p["author"] == current_user and st.session_state.get(f"editing_event_{p['id']}"):
                new_title = st.text_input("제목 수정", value=p["title"], key=f"et_{p['id']}")
                new_content = rich_text_input("내용 수정", value=p["content"], key=f"ec_{p['id']}")
                st.write("기존 첨부파일 (삭제할 항목 체크)")
                keep_flags = []
                for idx, att in enumerate(existing_atts):
                    cA, cB = st.columns([4, 1])
                    cA.write(f"📎 {att['name']}")
                    remove = cB.checkbox("삭제", key=f"ev_delatt_{p['id']}_{idx}")
                    keep_flags.append(not remove)
                add_files = st.file_uploader("첨부파일 추가", accept_multiple_files=True, key=f"ev_addfiles_{p['id']}")
                if st.button("저장", key=f"save_edit_{p['id']}"):
                    kept = [att for keep, att in zip(keep_flags, existing_atts) if keep]
                    added = [file_to_b64(f_) for f_ in (add_files or [])]
                    add_change_log(data, current_user, "수정", "게시글", new_title.strip() or p["title"], "event")
                    p["title"] = new_title.strip() or p["title"]
                    p["content"] = new_content or ""
                    p["files"] = kept + added
                    p["images"] = []
                    persist()
                    st.session_state[f"editing_event_{p['id']}"] = False
                    st.rerun()
            else:
                render_content(p["content"])
                for att in existing_atts:
                    render_attachment(att, key_prefix=f"ev_{p['id']}")

            st.markdown("**💬 댓글**")
            render_comments(p, "event", current_user, data)

# --------------------------------------------------------------------------
# 페이지: 온라인팀(관리)
# --------------------------------------------------------------------------
elif page == "온라인팀(관리)":
    st.markdown("# ⚙️ 온라인팀(관리)")
    st.caption("공지·안건 게시글과 투표를 함께 관리합니다.")

    search_q = st.text_input("🔍 검색 (제목/내용/파일명)", key="admin_search").strip().lower()

    view_filter = st.radio(
        "보기", ["전체"] + ADMIN_STATUS_LIST, horizontal=True, key="admin_view_filter",
        format_func=lambda s: s if s == "전체" else f"{STATUS_ICONS.get(s, '')} {s}",
    )
    quick_filter = st.selectbox(
        "빠른 필터", ["없음", "진행중", "투표 진행중", "완료처리필요"], key="admin_quick_filter"
    )

    if view_filter == "전체":
        if st.button("➕ 새 글 작성", key="toggle_new_admin_form"):
            st.session_state["show_new_admin_form"] = not st.session_state.get("show_new_admin_form", False)

        if st.session_state.get("show_new_admin_form"):
            with st.container(border=True):
                st.markdown("#### ➕ 새 글 작성")
                a_title = st.text_input("제목", key="new_admin_title")
                a_status = st.selectbox(
                    "상태", ADMIN_STATUS_LIST, key="new_admin_status",
                    format_func=lambda s: f"{STATUS_ICONS.get(s, '')} {s}",
                )
                a_content = rich_text_input("내용", key="new_admin_content")
                a_files = st.file_uploader(
                    "첨부파일 (이미지 포함, 드래그앤드롭 지원)", accept_multiple_files=True, key="new_admin_files"
                )

                add_vote = st.checkbox("🗳️ 이 게시글에 투표 추가하기", key="new_admin_add_vote")
                v_multi = False
                if add_vote:
                    st.markdown("##### 투표 설정")
                    st.caption("투표 문항은 위의 '제목'이 그대로 사용됩니다. 선택지를 아래에 입력해주세요.")
                    templates = data["vote_templates"]
                    template_names = ["(직접 입력)"] + [t["name"] for t in templates]
                    tcol1, tcol2, tcol3 = st.columns([2, 1, 1])
                    chosen_template = tcol1.selectbox("투표 양식 불러오기", template_names, key="vote_template_select")
                    if tcol2.button("양식 불러오기", width="stretch"):
                        if chosen_template != "(직접 입력)":
                            tpl = next(t for t in templates if t["name"] == chosen_template)
                            st.session_state["vote_options_text"] = "\n".join(tpl["options"])
                            st.rerun()
                    if tcol3.button("👥 구성원 불러오기", width="stretch"):
                        st.session_state["vote_options_text"] = "\n".join(sorted_member_display_by_position(data))
                        st.rerun()

                    st.session_state.setdefault("vote_options_text", "")
                    v_options_text = st.text_area("선택지 (한 줄에 하나씩 입력)", key="vote_options_text", height=120)
                    v_multi = st.checkbox("복수 선택 허용", key="new_vote_multi")

                    with st.expander("📋 현재 선택지를 투표 양식(템플릿)으로 저장"):
                        tpl_name = st.text_input("템플릿 이름", key="tpl_save_name")
                        if st.button("템플릿으로 저장"):
                            opts = [o.strip() for o in st.session_state["vote_options_text"].split("\n") if o.strip()]
                            if not tpl_name.strip() or len(opts) < 1:
                                st.warning("템플릿 이름과 선택지를 입력해주세요.")
                            else:
                                data["vote_templates"] = [t for t in data["vote_templates"] if t["name"] != tpl_name.strip()]
                                data["vote_templates"].append({"name": tpl_name.strip(), "options": opts})
                                persist()
                                st.success("템플릿이 저장되었습니다.")
                                st.rerun()
                        if templates:
                            st.write("저장된 템플릿")
                            for t in templates:
                                tc1, tc2 = st.columns([4, 1])
                                tc1.write(f"**{t['name']}** — {', '.join(t['options'])}")
                                if tc2.button("삭제", key=f"tpl_del_{t['name']}"):
                                    data["vote_templates"] = [x for x in data["vote_templates"] if x["name"] != t["name"]]
                                    persist()
                                    st.rerun()

                if st.button("게시글 등록", type="primary", key="submit_admin_post"):
                    if not a_title.strip():
                        st.warning("제목을 입력해주세요.")
                    else:
                        vote_field = None
                        if add_vote:
                            opts = [o.strip() for o in st.session_state.get("vote_options_text", "").split("\n") if o.strip()]
                            if len(opts) < 2:
                                st.warning("투표 선택지를 2개 이상 입력해주세요.")
                                st.stop()
                            vote_field = {
                                "question": a_title.strip(), "multi": v_multi,
                                "options": [{"text": o, "voters": []} for o in opts],
                            }
                        new_post = {
                            "id": new_id(), "title": a_title.strip(), "content": a_content or "",
                            "status": a_status, "author": current_user, "created_at": now_str(),
                            "comments": [], "images": [],
                            "files": [file_to_b64(f_) for f_ in (a_files or [])],
                        }
                        if vote_field:
                            new_post["vote"] = vote_field
                        data["admin_posts"].append(new_post)
                        persist()
                        st.session_state["_reset_vote_options"] = True
                        st.session_state["show_new_admin_form"] = False
                        st.success("게시글이 등록되었습니다.")
                        st.rerun()
    else:
        st.caption("새 글 작성은 '전체' 보기에서만 가능합니다.")

    st.markdown("---")

    # 최신 등록 글이 위로 오도록 (등록 순서 그대로 뒤집음 - 같은 분에 여러 개 등록돼도 정확)
    posts = list(reversed(data["admin_posts"]))
    if view_filter != "전체":
        posts = [p for p in posts if p.get("status", "등록") == view_filter]
    if quick_filter == "진행중":
        posts = [
            p for p in posts
            if p.get("status", "등록") not in ("공지", "완료") and not vote_started(p)
        ]
    elif quick_filter == "투표 진행중":
        posts = [p for p in posts if vote_started(p) and not vote_all_voted(p, data)]
    elif quick_filter == "완료처리필요":
        posts = [p for p in posts if vote_all_voted(p, data) and p.get("status") != "완료"]
    if search_q:
        def _match_admin(p):
            atts = p.get("files", []) + p.get("images", [])
            return (
                search_q in p["title"].lower() or search_q in p.get("content", "").lower()
                or any(search_q in a["name"].lower() for a in atts)
            )
        posts = [p for p in posts if _match_admin(p)]

    highlight_id = st.session_state.pop("_highlight_post_id", None)
    if highlight_id:
        matched = [p for p in posts if p["id"] == highlight_id]
        others = [p for p in posts if p["id"] != highlight_id]
        posts = matched + others

    if not posts:
        st.info("표시할 게시글이 없습니다.")

    for p in posts:
        if highlight_id and p["id"] == highlight_id:
            st.markdown(
                "<div style='background:#FFF7D6;border-left:4px solid #F5B301;"
                "padding:4px 10px;border-radius:4px;margin-bottom:-4px;font-size:12.5px'>"
                "🔎 확인하러 온 게시글</div>", unsafe_allow_html=True,
            )
        with st.container(border=True):
            status_col, spacer_col, btn_group = st.columns([3, 5, 2])
            with status_col:
                cur_status = p.get("status", "등록")
                new_status = st.selectbox(
                    "상태", ADMIN_STATUS_LIST, index=ADMIN_STATUS_LIST.index(cur_status),
                    format_func=lambda s: f"{STATUS_ICONS.get(s, '')} {s}",
                    key=f"admin_status_{p['id']}", label_visibility="collapsed",
                )
                if new_status != cur_status:
                    p["status"] = new_status
                    if current_user != p["author"]:
                        add_notification(data, p["author"], f"[{p['title']}]의 상태가 변경되었습니다.", "admin", p["id"])
                    persist()
                    st.rerun()
            if p["author"] == current_user:
                with btn_group:
                    edit_col, del_col = st.columns([1, 1], gap="xxsmall")
                    if edit_col.button("수정", key=f"aedit_{p['id']}"):
                        st.session_state[f"admin_editing_{p['id']}"] = not st.session_state.get(f"admin_editing_{p['id']}", False)
                        st.rerun()
                    if del_col.button("삭제", key=f"adel_{p['id']}"):
                        add_change_log(data, current_user, "삭제", "게시글", p["title"], "admin")
                        data["admin_posts"] = [x for x in data["admin_posts"] if x["id"] != p["id"]]
                        persist()
                        st.rerun()

            title_prefix = "🗳️ " if p.get("vote") else ""
            if vote_all_voted(p, data):
                title_prefix += "✅ "
            st.markdown(f"### {title_prefix}{p['title']}")
            st.caption(f"작성자 {p['author']} · {p['created_at']}")

            existing_atts = p.get("files", []) + p.get("images", [])

            if p["author"] == current_user and st.session_state.get(f"admin_editing_{p['id']}"):
                new_title = st.text_input("제목 수정", value=p["title"], key=f"at_{p['id']}")
                new_content = rich_text_input("내용 수정", value=p.get("content", ""), key=f"ac_{p['id']}")

                st.write("기존 첨부파일 (삭제할 항목 체크)")
                keep_flags = []
                for idx, att in enumerate(existing_atts):
                    cA, cB = st.columns([4, 1])
                    cA.write(f"📎 {att['name']}")
                    remove = cB.checkbox("삭제", key=f"ad_delatt_{p['id']}_{idx}")
                    keep_flags.append(not remove)
                add_files = st.file_uploader("첨부파일 추가", accept_multiple_files=True, key=f"ad_addfiles_{p['id']}")

                new_vote_options_text = None
                new_vote_multi = None
                add_new_vote = False
                if p.get("vote"):
                    st.write("투표 선택지 수정 (한 줄에 하나씩, 텍스트가 같으면 기존 투표 결과가 유지됩니다)")
                    existing_opts_text = "\n".join(o["text"] for o in p["vote"]["options"])
                    new_vote_options_text = st.text_area(
                        "선택지", value=existing_opts_text, key=f"editvote_{p['id']}", height=100
                    )
                    new_vote_multi = st.checkbox(
                        "복수 선택 허용", value=p["vote"].get("multi", False), key=f"editvotemulti_{p['id']}"
                    )
                else:
                    add_new_vote = st.checkbox(
                        "🗳️ 이 게시글에 투표 추가하기", key=f"admin_edit_add_vote_{p['id']}"
                    )
                    if add_new_vote:
                        st.caption("투표 문항은 위의 '제목 수정' 내용이 그대로 사용됩니다.")
                        templates = data["vote_templates"]
                        template_names = ["(직접 입력)"] + [t["name"] for t in templates]
                        etcol1, etcol2, etcol3 = st.columns([2, 1, 1])
                        chosen_template = etcol1.selectbox(
                            "투표 양식 불러오기", template_names, key=f"edit_vote_template_{p['id']}"
                        )
                        if etcol2.button("양식 불러오기", key=f"edit_vote_tpl_load_{p['id']}", width="stretch"):
                            if chosen_template != "(직접 입력)":
                                tpl = next(t for t in templates if t["name"] == chosen_template)
                                st.session_state[f"edit_new_vote_options_{p['id']}"] = "\n".join(tpl["options"])
                                st.rerun()
                        if etcol3.button("👥 구성원 불러오기", key=f"edit_vote_member_load_{p['id']}", width="stretch"):
                            st.session_state[f"edit_new_vote_options_{p['id']}"] = "\n".join(
                                sorted_member_display_by_position(data)
                            )
                            st.rerun()
                        st.session_state.setdefault(f"edit_new_vote_options_{p['id']}", "")
                        new_vote_options_text = st.text_area(
                            "선택지 (한 줄에 하나씩 입력)", key=f"edit_new_vote_options_{p['id']}", height=100
                        )
                        new_vote_multi = st.checkbox("복수 선택 허용", key=f"edit_new_vote_multi_{p['id']}")

                if st.button("저장", key=f"admin_save_{p['id']}"):
                    kept = [att for keep, att in zip(keep_flags, existing_atts) if keep]
                    added = [file_to_b64(f_) for f_ in (add_files or [])]
                    add_change_log(data, current_user, "수정", "게시글", new_title.strip() or p["title"], "admin")
                    p["title"] = new_title.strip() or p["title"]
                    p["content"] = new_content or ""
                    p["files"] = kept + added
                    p["images"] = []
                    if p.get("vote") and new_vote_options_text is not None:
                        old_by_text = {o["text"]: o["voters"] for o in p["vote"]["options"]}
                        new_lines = [l.strip() for l in new_vote_options_text.split("\n") if l.strip()]
                        p["vote"]["options"] = [{"text": t, "voters": old_by_text.get(t, [])} for t in new_lines]
                        p["vote"]["multi"] = new_vote_multi
                        p["vote"]["question"] = p["title"]
                    elif add_new_vote and new_vote_options_text is not None:
                        new_lines = [l.strip() for l in new_vote_options_text.split("\n") if l.strip()]
                        if len(new_lines) < 2:
                            st.warning("투표 선택지를 2개 이상 입력해주세요.")
                            st.stop()
                        p["vote"] = {
                            "question": p["title"], "multi": new_vote_multi,
                            "options": [{"text": t, "voters": []} for t in new_lines],
                        }
                    persist()
                    st.session_state[f"admin_editing_{p['id']}"] = False
                    st.rerun()
            else:
                if p.get("content"):
                    render_content(p["content"])
                for att in existing_atts:
                    render_attachment(att, key_prefix=f"admin_{p['id']}")

            if p.get("vote"):
                vote = p["vote"]
                st.markdown(f"**🗳️ {vote['question']}**")
                options = vote["options"]
                my_votes = [i for i, o in enumerate(options) if current_user in o["voters"]]
                already_voted = len(my_votes) > 0

                if already_voted:
                    info_col, reselect_col = st.columns([5, 1])
                    info_col.info("✅ 이미 투표하셨습니다: " + ", ".join(options[i]["text"] for i in my_votes))
                    if reselect_col.button("다시 선택하기", key=f"vote_reselect_{p['id']}"):
                        for o in options:
                            if current_user in o["voters"]:
                                o["voters"].remove(current_user)
                        persist()
                        st.rerun()
                else:
                    if vote.get("multi"):
                        picked = st.multiselect(
                            "선택지 (복수 선택 가능)", list(range(len(options))),
                            format_func=lambda i: options[i]["text"], key=f"vote_multi_{p['id']}",
                        )
                    else:
                        picked_single = st.radio(
                            "선택지", list(range(len(options))), index=None,
                            format_func=lambda i: options[i]["text"], key=f"vote_single_{p['id']}",
                        )
                        picked = [picked_single] if picked_single is not None else []

                    if st.button("투표하기", key=f"vote_submit_{p['id']}"):
                        if not picked:
                            st.session_state["_vote_empty_warning"] = True
                            st.rerun()
                        else:
                            for i in picked:
                                if current_user not in options[i]["voters"]:
                                    options[i]["voters"].append(current_user)
                            persist()
                            st.rerun()

                st.markdown("**👥 투표자 현황**")
                member_position_map = {m["name"]: m.get("position", "") for m in data["members"]}
                seen_voters = []
                for o in options:
                    for v in o["voters"]:
                        if v not in seen_voters:
                            seen_voters.append(v)
                if seen_voters:
                    display_list = [f"{v} {member_position_map.get(v, '')}".strip() for v in seen_voters]
                    st.markdown(", ".join(display_list))
                else:
                    st.markdown("-")

            st.markdown("**💬 댓글**")
            render_comments(p, "admin", current_user, data)

# --------------------------------------------------------------------------
# 페이지: 구성원 관리
# --------------------------------------------------------------------------
elif page == "구성원 관리":
    st.markdown("# ⚙️ 구성원 관리")

    st.markdown("### 구성원 추가")
    new_name = st.text_input("이름", key="new_member_name", placeholder="이름")
    ncol1, ncol2 = st.columns(2)
    new_position = ncol1.selectbox("직책/직위", POSITION_OPTIONS, key="new_member_position")
    new_part = ncol2.selectbox("파트", PART_OPTIONS, key="new_member_part")

    used_colors = {m["color"] for m in data["members"]} | {c["color"] for c in data.get("calendars", [])}
    available_presets = [c for c in PRESET_COLORS if c[1] not in used_colors]

    if "member_color_choice" not in st.session_state:
        st.session_state.member_color_choice = available_presets[0][1] if available_presets else "custom"

    st.markdown("**개인 색상 선택** (이미 다른 구성원/캘린더가 사용 중인 색상은 표시되지 않습니다)")
    swatch_cols = st.columns(6)
    for i, (cname, hexcode) in enumerate(available_presets):
        with swatch_cols[i % 6]:
            selected = st.session_state.member_color_choice == hexcode
            border = "3px solid #111827" if selected else "1px solid #ddd"
            st.markdown(
                f"<div style='width:100%;height:34px;border-radius:8px;background:{hexcode};"
                f"border:{border}'></div><div style='height:8px'></div>", unsafe_allow_html=True,
            )
            if st.button(cname, key=f"swatch_{hexcode}", width="stretch"):
                st.session_state.member_color_choice = hexcode
                st.rerun()

    other_selected = st.session_state.member_color_choice == "custom"
    other_col = swatch_cols[len(available_presets) % 6] if len(available_presets) % 6 != 0 else st.columns(6)[0]
    with other_col:
        border = "3px solid #111827" if other_selected else "1px dashed #999"
        st.markdown(
            f"<div style='width:100%;height:34px;border-radius:8px;"
            "background:repeating-linear-gradient(45deg,#eee,#eee 4px,#fff 4px,#fff 8px);"
            f"border:{border}'></div><div style='height:8px'></div>", unsafe_allow_html=True,
        )
        if st.button("기타", key="swatch_custom", width="stretch"):
            st.session_state.member_color_choice = "custom"
            st.rerun()

    final_color = st.session_state.member_color_choice
    if final_color == "custom":
        final_color = st.color_picker("기타 색상 직접 선택", value="#999999", key="member_custom_color")

    if st.button("추가", type="primary"):
        if not new_name.strip():
            st.warning("이름을 입력해주세요.")
        elif new_name.strip() in member_names(data):
            st.warning("이미 존재하는 구성원입니다.")
        elif final_color in used_colors:
            st.warning("이미 사용 중인 색상입니다. 다른 색상을 선택해주세요.")
        else:
            data["members"].append(
                {"name": new_name.strip(), "color": final_color, "position": new_position, "part": new_part}
            )
            persist()
            del st.session_state["member_color_choice"]
            st.success(f"{new_name.strip()}님이 추가되었습니다.")
            st.rerun()

    st.markdown("---")
    st.markdown("### 현재 구성원")
    st.caption("직책에 '팀장'·'파트장'이 포함된 구성원은 목록 상단에 가나다순으로 표시됩니다.")
    if not data["members"]:
        st.info("등록된 구성원이 없습니다.")
    for m in sorted_members_for_display(data):
        c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 1, 1])
        c1.markdown(
            f"<div style='width:22px;height:22px;border-radius:50%;background:{m['color']}'></div>",
            unsafe_allow_html=True,
        )
        c2.write(m["name"])
        c3.caption(m.get("position", "사원"))
        c4.caption(m.get("part", "1파트"))
        if c5.button("삭제", key=f"member_del_{m['name']}"):
            data["members"] = [x for x in data["members"] if x["name"] != m["name"]]
            persist()
            st.success(f"{m['name']}님이 삭제되었습니다.")
            st.rerun()
