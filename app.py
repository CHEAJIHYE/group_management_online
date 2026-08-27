import streamlit as st
import pandas as pd
import calendar
from datetime import date, datetime, timedelta
from pathlib import Path
import json, uuid, base64

st.set_page_config(page_title="온라인팀", page_icon="🌐", layout="wide")
DATA_FILE = Path("online_team_data.json")

DEFAULT_DATA = {
    "members": [
        {"name":"지혜","color":"#FF8A8A"},
        {"name":"민지","color":"#6EC6FF"},
        {"name":"수연","color":"#81C784"},
        {"name":"유진","color":"#FFD166"},
    ],
    "events": [
        {"id":"e1","title":"정기 모임","start":"2026-09-05","end":"2026-09-05","owner":"지혜","category":"공동","memo":"다음 정기 모임"},
        {"id":"e2","title":"개인 일정","start":"2026-09-07","end":"2026-09-09","owner":"민지","category":"개인","memo":"개인 일정 예시"},
    ],
    "posts": [],
    "polls": []
}

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_DATA))

def save_data():
    DATA_FILE.write_text(json.dumps(st.session_state.data, ensure_ascii=False, indent=2), encoding="utf-8")

if "data" not in st.session_state:
    st.session_state.data = load_data()
if "selected_day" not in st.session_state:
    st.session_state.selected_day = date.today()

def members():
    return st.session_state.data["members"]

def member_names():
    return [m["name"] for m in members()]

def member_color(name):
    for m in members():
        if m["name"] == name:
            return m["color"]
    return "#999999"

def rerun():
    st.rerun()

def event_occurs_on(event, day):
    s = datetime.strptime(event["start"], "%Y-%m-%d").date()
    e = datetime.strptime(event["end"], "%Y-%m-%d").date()
    return s <= day <= e

st.markdown("""
<style>
.online-title {font-size: 2.3rem; font-weight: 800; margin-bottom: .1rem;}
.calendar-day {min-height:120px; border:1px solid #e6e6e6; border-radius:10px; padding:7px; margin:2px;}
.day-num {font-weight:700; margin-bottom:6px;}
.event-pill {font-size:0.78rem; padding:3px 6px; border-radius:7px; margin-bottom:3px; color:#222;}
.post-image {max-width:100%; border-radius:10px; margin-top:8px;}
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🌐 온라인팀")
page = st.sidebar.radio("메뉴", ["🏠 대시보드","📅 일정 관리","📝 제안·진행·종료","🗳️ 투표 게시판","⚙️ 구성원 관리"])
st.sidebar.divider()
current_user = st.sidebar.selectbox("현재 사용자", member_names())

if page == "🏠 대시보드":
    st.markdown('<div class="online-title">🌐 온라인팀</div>', unsafe_allow_html=True)
    st.caption("일정 · 안건 · 투표를 한 곳에서 관리합니다.")

    today = date.today()
    active_posts = [p for p in st.session_state.data["posts"] if p["status"] != "종료"]
    open_polls = [p for p in st.session_state.data["polls"] if not p["closed"]]
    c1,c2,c3 = st.columns(3)
    c1.metric("등록된 일정", len(st.session_state.data["events"]))
    c2.metric("진행 중 안건", len(active_posts))
    c3.metric("진행 중 투표", len(open_polls))

    st.subheader("📅 오늘 이후 일정")
    rows = []
    for e in st.session_state.data["events"]:
        if datetime.strptime(e["end"], "%Y-%m-%d").date() >= today:
            rows.append({"제목":e["title"],"기간":f'{e["start"]} ~ {e["end"]}',"담당자":e["owner"],"구분":e["category"]})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

elif page == "📅 일정 관리":
    st.title("📅 일정 관리")
    tab1, tab2 = st.tabs(["월간 일정 보기","일정 직접 등록"])

    with tab1:
        control1, control2, control3 = st.columns([1,1,2])
        year = control1.number_input("연도", 2020, 2100, date.today().year)
        month = control2.number_input("월", 1, 12, date.today().month)
        selected_members = control3.multiselect("구성원 필터 (비워두면 전체)", member_names())

        st.caption("날짜를 클릭하면 아래에 해당 날짜를 시작일로 하는 일정 등록창이 열립니다.")
        cal = calendar.Calendar(firstweekday=6)
        weeks = cal.monthdatescalendar(int(year), int(month))
        headers = st.columns(7)
        for col, wd in zip(headers, ["일","월","화","수","목","금","토"]):
            col.markdown(f"**{wd}**")

        for week in weeks:
            cols = st.columns(7)
            for col, day in zip(cols, week):
                with col:
                    if day.month != int(month):
                        st.markdown("<div style='opacity:.25;height:120px'></div>", unsafe_allow_html=True)
                    else:
                        if st.button(str(day.day), key=f"day_{day.isoformat()}"):
                            st.session_state.selected_day = day
                        st.markdown("<div style='min-height:90px'>", unsafe_allow_html=True)
                        shown = [
                            e for e in st.session_state.data["events"]
                            if event_occurs_on(e, day) and (not selected_members or e["owner"] in selected_members)
                        ]
                        for e in shown[:4]:
                            color = member_color(e["owner"])
                            st.markdown(
                                f"<div class='event-pill' style='background:{color}55;border-left:4px solid {color};'>"
                                f"<b>{e['owner']}</b> · {e['title']}</div>",
                                unsafe_allow_html=True
                            )
                        if len(shown) > 4:
                            st.caption(f"+{len(shown)-4}개 더")
                        st.markdown("</div>", unsafe_allow_html=True)

        st.divider()
        st.subheader(f"➕ {st.session_state.selected_day.strftime('%Y-%m-%d')} 일정 등록")
        with st.form("quick_event_form", clear_on_submit=True):
            q_title = st.text_input("일정 제목")
            q_end = st.date_input("종료일", value=st.session_state.selected_day, min_value=st.session_state.selected_day)
            q_owner = st.selectbox("담당자", member_names(), index=member_names().index(current_user))
            q_cat = st.radio("구분", ["개인","공동"], horizontal=True)
            q_memo = st.text_area("메모")
            if st.form_submit_button("선택한 날짜에 일정 등록"):
                if q_title.strip():
                    st.session_state.data["events"].append({
                        "id":str(uuid.uuid4()),"title":q_title.strip(),
                        "start":st.session_state.selected_day.isoformat(),"end":q_end.isoformat(),
                        "owner":q_owner,"category":q_cat,"memo":q_memo.strip()
                    })
                    save_data()
                    st.success("일정을 등록했습니다.")
                    rerun()
                else:
                    st.error("일정 제목을 입력해주세요.")

    with tab2:
        with st.form("event_form", clear_on_submit=True):
            title = st.text_input("일정 제목")
            c1,c2 = st.columns(2)
            start = c1.date_input("시작일", value=date.today())
            end = c2.date_input("종료일", value=date.today())
            owner = st.selectbox("담당자", member_names(), index=member_names().index(current_user))
            category = st.radio("일정 구분", ["개인","공동"], horizontal=True)
            memo = st.text_area("메모")
            if st.form_submit_button("일정 등록"):
                if not title.strip():
                    st.error("일정 제목을 입력해주세요.")
                elif end < start:
                    st.error("종료일은 시작일보다 빠를 수 없습니다.")
                else:
                    st.session_state.data["events"].append({
                        "id":str(uuid.uuid4()),"title":title.strip(),
                        "start":start.isoformat(),"end":end.isoformat(),
                        "owner":owner,"category":category,"memo":memo.strip()
                    })
                    save_data()
                    st.success("일정이 등록되었습니다.")
                    rerun()

elif page == "📝 제안·진행·종료":
    st.title("📝 제안 · 진행 · 종료 게시판")
    status_filter = st.radio("보기", ["전체","제안","진행","종료"], horizontal=True)

    left,right = st.columns([1.25,1])
    with left:
        posts = st.session_state.data["posts"]
        if status_filter != "전체":
            posts = [p for p in posts if p["status"] == status_filter]

        for p in sorted(posts, key=lambda x:x["created_at"], reverse=True):
            with st.container(border=True):
                st.markdown(f"### [{p['status']}] {p['title']}")
                st.caption(f"작성자 {p['author']} · {p['created_at']}")
                if p.get("text"):
                    st.write(p["text"])
                for img in p.get("images", []):
                    st.image(base64.b64decode(img))
                files = p.get("files", [])
                if files:
                    st.caption("첨부파일")
                    for f in files:
                        raw = base64.b64decode(f["data"])
                        st.download_button(f"📎 {f['name']}", raw, file_name=f["name"], key=f"dl_{p['id']}_{f['name']}")

                if p["author"] == current_user:
                    new_status = st.selectbox(
                        "상태 변경",
                        ["제안","진행","종료"],
                        index=["제안","진행","종료"].index(p["status"]),
                        key=f"status_{p['id']}"
                    )
                    if st.button("상태 저장", key=f"save_{p['id']}"):
                        p["status"] = new_status
                        save_data()
                        rerun()

    with right:
        st.subheader("새 게시글")
        with st.form("post_form", clear_on_submit=True):
            title = st.text_input("제목")
            status = st.selectbox("상태", ["제안","진행","종료"])
            text = st.text_area("내용 (텍스트 입력 또는 붙여넣기)")
            pasted_or_uploaded_images = st.file_uploader(
                "이미지 첨부",
                type=["png","jpg","jpeg","gif","webp"],
                accept_multiple_files=True,
                help="이미지를 드래그앤드롭하거나 파일로 첨부할 수 있습니다."
            )
            attached_files = st.file_uploader(
                "첨부파일",
                accept_multiple_files=True,
                help="파일을 이곳에 드래그앤드롭해서 첨부할 수 있습니다."
            )
            if st.form_submit_button("게시글 등록"):
                if not title.strip():
                    st.error("제목을 입력해주세요.")
                else:
                    images = [base64.b64encode(f.getvalue()).decode() for f in (pasted_or_uploaded_images or [])]
                    files = []
                    for f in (attached_files or []):
                        files.append({"name":f.name,"data":base64.b64encode(f.getvalue()).decode()})
                    st.session_state.data["posts"].append({
                        "id":str(uuid.uuid4()),"title":title.strip(),"author":current_user,
                        "status":status,"text":text,"images":images,"files":files,
                        "created_at":datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    save_data()
                    st.success("게시글이 등록되었습니다.")
                    rerun()

        st.caption("※ 브라우저에서 복사한 이미지를 글 편집창에 직접 Ctrl+V로 붙이는 '리치 에디터'는 기본 Streamlit만으로는 제한이 있어, 현재 초안에서는 드래그앤드롭/파일 첨부 방식으로 구현했습니다.")

elif page == "🗳️ 투표 게시판":
    st.title("🗳️ 관리용 투표 게시판")
    tab1,tab2 = st.tabs(["투표하기","새 투표"])

    with tab1:
        if not st.session_state.data["polls"]:
            st.info("아직 등록된 투표가 없습니다.")
        for poll in st.session_state.data["polls"]:
            with st.container(border=True):
                st.subheader(("🔒 " if poll["closed"] else "🟢 ") + poll["title"])
                voted = [o for o,u in poll["votes"].items() if current_user in u]
                if not poll["closed"]:
                    if poll["multiple"]:
                        choice = st.multiselect("선택",poll["options"],default=voted,key=poll["id"])
                    else:
                        choice = st.radio("선택",poll["options"],index=(poll["options"].index(voted[0]) if voted else None),key=poll["id"])
                        choice = [choice] if choice else []
                    if st.button("내 투표 저장",key="savevote_"+poll["id"]):
                        for o in poll["options"]:
                            if current_user in poll["votes"].setdefault(o,[]): poll["votes"][o].remove(current_user)
                        for o in choice: poll["votes"][o].append(current_user)
                        save_data(); rerun()
                    if poll["author"] == current_user and st.button("투표 종료",key="close_"+poll["id"]):
                        poll["closed"]=True; save_data(); rerun()
                result = pd.DataFrame({"선택지":poll["options"],"득표수":[len(poll["votes"].get(o,[])) for o in poll["options"]]})
                st.dataframe(result,use_container_width=True,hide_index=True)

    with tab2:
        with st.form("poll_form",clear_on_submit=True):
            title=st.text_input("투표 제목")
            options=st.text_area("선택지 (한 줄에 하나씩)")
            multiple=st.checkbox("복수 선택 허용")
            if st.form_submit_button("투표 생성"):
                opts=[x.strip() for x in options.splitlines() if x.strip()]
                if title.strip() and len(opts)>=2:
                    st.session_state.data["polls"].append({
                        "id":str(uuid.uuid4()),"title":title.strip(),"author":current_user,
                        "options":opts,"votes":{o:[] for o in opts},"multiple":multiple,
                        "closed":False,"created_at":datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    save_data(); st.success("투표를 만들었습니다."); rerun()
                else: st.error("제목과 선택지 2개 이상을 입력해주세요.")

elif page == "⚙️ 구성원 관리":
    st.title("⚙️ 구성원 관리")
    st.subheader("구성원 추가")
    c1,c2,c3 = st.columns([2,1,1])
    new_name = c1.text_input("이름", key="new_member_name")
    new_color = c2.color_picker("개인 색상", "#6EC6FF")
    if c3.button("추가"):
        if new_name.strip() and new_name.strip() not in member_names():
            st.session_state.data["members"].append({"name":new_name.strip(),"color":new_color})
            save_data(); rerun()
        else:
            st.warning("이름을 확인해주세요.")

    st.divider()
    st.subheader("현재 구성원")
    for m in list(members()):
        a,b,c = st.columns([0.5,3,1])
        a.markdown(f"<div style='width:28px;height:28px;border-radius:50%;background:{m['color']};margin-top:4px'></div>", unsafe_allow_html=True)
        b.write(m["name"])
        if c.button("삭제", key="del_"+m["name"]):
            if len(members()) <= 1:
                st.error("최소 한 명의 구성원이 필요합니다.")
            elif m["name"] == current_user:
                st.warning("현재 선택된 사용자는 바로 삭제할 수 없습니다. 다른 사용자를 선택한 뒤 삭제해주세요.")
            else:
                st.session_state.data["members"] = [x for x in members() if x["name"] != m["name"]]
                save_data()
                rerun()
