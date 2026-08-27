import streamlit as st
import pandas as pd
from datetime import date, datetime
from pathlib import Path
import json
import uuid

st.set_page_config(page_title="모임 관리", page_icon="📌", layout="wide")

DATA_FILE = Path("demo_data.json")

DEFAULT_DATA = {
    "members": ["지혜", "민지", "수연", "유진", "서연"],
    "events": [
        {"id":"e1","title":"정기 모임","date":"2026-09-05","owner":"지혜","category":"공동","memo":"다음 정기 모임"},
        {"id":"e2","title":"개인 일정","date":"2026-09-07","owner":"민지","category":"개인","memo":"개인 일정 예시"},
        {"id":"e3","title":"행사 준비 회의","date":"2026-09-10","owner":"수연","category":"공동","memo":"행사 준비 논의"},
    ],
    "posts": [
        {"id":"p1","title":"가을 단체 여행을 제안합니다","author":"지혜","status":"제안","content":"10월 중 하루 또는 1박 2일 여행을 가면 어떨까요?","created_at":"2026-08-27 09:00"},
        {"id":"p2","title":"9월 정기 모임 장소 선정","author":"민지","status":"진행","content":"후보 장소를 조사하고 있습니다.","created_at":"2026-08-26 14:30"},
        {"id":"p3","title":"8월 번개 모임 후기","author":"수연","status":"종료","content":"즐거운 시간 보내고 마무리했습니다.","created_at":"2026-08-20 20:10"},
    ],
    "polls": [
        {
            "id":"v1","title":"다음 정기 모임 날짜","author":"지혜",
            "options":["9월 5일","9월 6일","9월 12일"],
            "votes":{"9월 5일":["지혜","민지"],"9월 6일":["수연"],"9월 12일":[]},
            "multiple":False,"closed":False,"created_at":"2026-08-27 09:00"
        }
    ]
}

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_DATA.copy()

def save_data():
    DATA_FILE.write_text(
        json.dumps(st.session_state.data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

if "data" not in st.session_state:
    st.session_state.data = load_data()

def rerun():
    st.rerun()

def event_df():
    rows = st.session_state.data["events"]
    if not rows:
        return pd.DataFrame(columns=["날짜","제목","담당자","구분","메모"])
    df = pd.DataFrame(rows)
    return df.rename(columns={"date":"날짜","title":"제목","owner":"담당자","category":"구분","memo":"메모"})[
        ["날짜","제목","담당자","구분","메모"]
    ].sort_values("날짜")

st.sidebar.title("📌 모임 관리")
page = st.sidebar.radio(
    "메뉴",
    ["🏠 대시보드", "📅 일정 관리", "📝 제안·진행·종료", "🗳️ 투표 게시판", "⚙️ 구성원 관리"]
)
st.sidebar.divider()
current_user = st.sidebar.selectbox("현재 사용자", st.session_state.data["members"])
st.sidebar.caption("초안 버전 · 데이터는 앱 폴더의 demo_data.json에 저장됩니다.")

if page == "🏠 대시보드":
    st.title("🏠 모임 관리 대시보드")
    today = date.today().isoformat()

    total_events = len(st.session_state.data["events"])
    active_posts = len([p for p in st.session_state.data["posts"] if p["status"] != "종료"])
    open_polls = len([p for p in st.session_state.data["polls"] if not p["closed"]])

    a,b,c = st.columns(3)
    a.metric("등록된 일정", f"{total_events}개")
    b.metric("진행 중 안건", f"{active_posts}개")
    c.metric("진행 중 투표", f"{open_polls}개")

    st.subheader("📅 예정된 일정")
    df = event_df()
    upcoming = df[df["날짜"] >= today].head(8)
    st.dataframe(upcoming, use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.subheader("📝 진행 중인 안건")
        active = [p for p in st.session_state.data["posts"] if p["status"] != "종료"]
        for p in active:
            st.info(f"**[{p['status']}] {p['title']}**\n\n작성자: {p['author']}")
    with right:
        st.subheader("🗳️ 진행 중인 투표")
        for poll in [x for x in st.session_state.data["polls"] if not x["closed"]]:
            st.warning(f"**{poll['title']}**\n\n선택지 {len(poll['options'])}개")

elif page == "📅 일정 관리":
    st.title("📅 일정 관리")

    tab1, tab2 = st.tabs(["일정 보기", "일정 등록"])

    with tab1:
        members = st.multiselect(
            "보고 싶은 구성원을 선택하세요 (비워두면 전체)",
            st.session_state.data["members"]
        )
        categories = st.multiselect("구분", ["개인","공동"], default=["개인","공동"])

        df = event_df()
        if members:
            df = df[df["담당자"].isin(members)]
        if categories:
            df = df[df["구분"].isin(categories)]

        st.subheader("선택한 일정")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("달력형 간단 보기")
        if len(df):
            for day, group in df.groupby("날짜"):
                with st.expander(f"📅 {day} · {len(group)}개 일정"):
                    for _, row in group.iterrows():
                        st.write(f"**{row['제목']}** — {row['담당자']} ({row['구분']})")
                        if row["메모"]:
                            st.caption(row["메모"])

    with tab2:
        with st.form("event_form", clear_on_submit=True):
            title = st.text_input("일정 제목")
            event_date = st.date_input("날짜", value=date.today())
            owner = st.selectbox("담당자", st.session_state.data["members"], index=st.session_state.data["members"].index(current_user))
            category = st.radio("일정 구분", ["개인","공동"], horizontal=True)
            memo = st.text_area("메모")
            submitted = st.form_submit_button("일정 등록")
            if submitted:
                if not title.strip():
                    st.error("일정 제목을 입력해주세요.")
                else:
                    st.session_state.data["events"].append({
                        "id": str(uuid.uuid4()),
                        "title": title.strip(),
                        "date": event_date.isoformat(),
                        "owner": owner,
                        "category": category,
                        "memo": memo.strip()
                    })
                    save_data()
                    st.success("일정이 등록되었습니다!")
                    rerun()

elif page == "📝 제안·진행·종료":
    st.title("📝 제안 · 진행 · 종료 게시판")
    status_filter = st.radio("상태 보기", ["전체","제안","진행","종료"], horizontal=True)

    left, right = st.columns([1.2, 1])
    with left:
        posts = st.session_state.data["posts"]
        if status_filter != "전체":
            posts = [p for p in posts if p["status"] == status_filter]

        for p in sorted(posts, key=lambda x: x["created_at"], reverse=True):
            with st.container(border=True):
                st.markdown(f"### {p['title']}")
                st.caption(f"{p['status']} · 작성자 {p['author']} · {p['created_at']}")
                st.write(p["content"])
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
                        st.success("상태를 변경했습니다.")
                        rerun()

    with right:
        st.subheader("새 안건 작성")
        with st.form("post_form", clear_on_submit=True):
            title = st.text_input("제목")
            status = st.selectbox("현재 상태", ["제안","진행","종료"])
            content = st.text_area("내용", height=180)
            if st.form_submit_button("게시글 등록"):
                if not title.strip():
                    st.error("제목을 입력해주세요.")
                else:
                    st.session_state.data["posts"].append({
                        "id": str(uuid.uuid4()),
                        "title": title.strip(),
                        "author": current_user,
                        "status": status,
                        "content": content.strip(),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    save_data()
                    st.success("게시글이 등록되었습니다!")
                    rerun()

elif page == "🗳️ 투표 게시판":
    st.title("🗳️ 관리용 투표 게시판")
    tab1, tab2 = st.tabs(["투표하기", "새 투표 만들기"])

    with tab1:
        for poll in st.session_state.data["polls"]:
            with st.container(border=True):
                state = "🔒 종료" if poll["closed"] else "🟢 진행 중"
                st.subheader(f"{state} · {poll['title']}")
                st.caption(f"작성자: {poll['author']} · {'복수 선택 가능' if poll['multiple'] else '단일 선택'}")

                voted_options = [opt for opt, users in poll["votes"].items() if current_user in users]
                if poll["closed"]:
                    st.bar_chart(pd.DataFrame({
                        "선택지": poll["options"],
                        "득표수": [len(poll["votes"].get(opt, [])) for opt in poll["options"]]
                    }).set_index("선택지"))
                else:
                    if poll["multiple"]:
                        selected = st.multiselect("선택", poll["options"], default=voted_options, key=f"poll_{poll['id']}")
                    else:
                        selected = st.radio("선택", poll["options"], index=(poll["options"].index(voted_options[0]) if voted_options else None), key=f"poll_{poll['id']}")
                        selected = [selected] if selected else []

                    if st.button("내 투표 저장", key=f"vote_{poll['id']}"):
                        for opt in poll["options"]:
                            poll["votes"].setdefault(opt, [])
                            if current_user in poll["votes"][opt]:
                                poll["votes"][opt].remove(current_user)
                        for opt in selected:
                            poll["votes"][opt].append(current_user)
                        save_data()
                        st.success("투표가 저장되었습니다.")
                        rerun()

                    if poll["author"] == current_user:
                        if st.button("투표 종료하기", key=f"close_{poll['id']}"):
                            poll["closed"] = True
                            save_data()
                            rerun()

                result_df = pd.DataFrame({
                    "선택지": poll["options"],
                    "득표수": [len(poll["votes"].get(opt, [])) for opt in poll["options"]]
                })
                st.dataframe(result_df, use_container_width=True, hide_index=True)

    with tab2:
        with st.form("poll_form", clear_on_submit=True):
            title = st.text_input("투표 제목")
            options_text = st.text_area("선택지 (한 줄에 하나씩)", placeholder="9월 5일\n9월 6일\n9월 12일")
            multiple = st.checkbox("복수 선택 허용")
            if st.form_submit_button("투표 생성"):
                options = [x.strip() for x in options_text.splitlines() if x.strip()]
                if not title.strip() or len(options) < 2:
                    st.error("제목과 2개 이상의 선택지를 입력해주세요.")
                else:
                    st.session_state.data["polls"].append({
                        "id": str(uuid.uuid4()),
                        "title": title.strip(),
                        "author": current_user,
                        "options": options,
                        "votes": {opt: [] for opt in options},
                        "multiple": multiple,
                        "closed": False,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    save_data()
                    st.success("투표가 생성되었습니다!")
                    rerun()

elif page == "⚙️ 구성원 관리":
    st.title("⚙️ 구성원 관리")
    st.write("초안 버전에서는 간단하게 구성원을 추가할 수 있습니다.")
    with st.form("member_form", clear_on_submit=True):
        new_member = st.text_input("새 구성원 이름")
        if st.form_submit_button("구성원 추가"):
            if new_member.strip() and new_member.strip() not in st.session_state.data["members"]:
                st.session_state.data["members"].append(new_member.strip())
                save_data()
                st.success("구성원을 추가했습니다.")
                rerun()
            else:
                st.warning("이름을 확인해주세요.")

    st.dataframe(pd.DataFrame({"구성원": st.session_state.data["members"]}), use_container_width=True, hide_index=True)
