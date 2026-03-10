import streamlit as st
import pandas as pd
import random
import requests
import re
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
import google.generativeai as genai
import json
import os
import io # 💡 메모리 버퍼 처리를 위한 라이브러리
from datetime import datetime, timedelta
import streamlit.components.v1 as components
from youtube_transcript_api import YouTubeTranscriptApi

# 페이지 기본 설정
st.set_page_config(page_title="유튜브 데이터 마이닝 솔루션", layout="wide", initial_sidebar_state="expanded")

# --- 🧠 화면 상태 저장 (세션 스테이트) ---
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'trend'

# --- 💾 API 키 저장/불러오기 기능 ---
CONFIG_FILE = "api_keys.json"

def load_api_keys():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"youtube": "", "gemini": ""}
    return {"youtube": "", "gemini": ""}

def save_api_keys(youtube_key, gemini_key):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"youtube": youtube_key, "gemini": gemini_key}, f)

saved_keys = load_api_keys()

# --- 🛠️ 유틸리티 함수 ---
def parse_youtube_duration(duration_str):
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match: return 0
    h, m, s = match.groups()
    return (int(h) if h else 0) * 3600 + (int(m) if m else 0) * 60 + (int(s) if s else 0)

def format_duration(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

# 💡 데이터를 진짜 엑셀 파일(.xlsx)로 변환하는 함수
def to_excel(df):
    output = io.BytesIO()
    # xlsxwriter 엔진을 사용하여 엑셀 작성
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='YouTube_Data')
    return output.getvalue()

@st.cache_data(ttl=600)
def get_google_trends():
    try:
        res = requests.get("https://trends.google.co.kr/trending/rss?geo=KR")
        soup = BeautifulSoup(res.text, 'xml')
        trends = [t.text for t in soup.find_all('title')[1:11]]
        return pd.DataFrame({"순위": range(1, len(trends)+1), "키워드": trends})
    except:
        return pd.DataFrame({"순위": range(1, 11), "키워드": ["수집 지연"] * 10})

@st.cache_data(ttl=600)
def get_naver_realtime():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get("https://signal.bz/", headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        trends = []
        for rank in soup.find_all('span', class_='rank-text'):
            if rank.text.strip() and rank.text.strip() not in trends:
                trends.append(rank.text.strip())
            if len(trends) >= 10: break
        if not trends: return pd.DataFrame({"순위": range(1, 11), "키워드": ["수집 오류"] * 10})
        return pd.DataFrame({"순위": range(1, len(trends)+1), "키워드": trends})
    except:
        return pd.DataFrame({"순위": range(1, 11), "키워드": ["수집 실패"] * 10})

# --- 🖼️ 표 렌더링 함수 ---
def render_large_thumbnail_table(df):
    html_df = df.copy()
    
    text_cols = {
        '제목': {'min': '180px', 'max': '250px', 'bg': 'transparent', 'color': '#333'},
        '자막요약': {'min': '220px', 'max': '300px', 'bg': '#f9f9f9', 'color': '#555'},
        '베스트댓글': {'min': '220px', 'max': '300px', 'bg': '#fff9e6', 'color': '#666'}
    }

    for col, style in text_cols.items():
        if col in html_df.columns:
            html_df[col] = html_df[col].astype(str).str.replace('<', '&lt;').str.replace('>', '&gt;')
            html_df[col] = html_df[col].apply(lambda x: f'<div style="min-width: {style["min"]}; max-width: {style["max"]}; text-align: left; white-space: normal; word-break: keep-all; line-height: 1.5; font-size: 13px; color: {style["color"]}; background: {style["bg"]}; padding: 10px; border-radius: 8px;">{x}</div>')

    if '썸네일' in html_df.columns and '영상링크' in html_df.columns:
        html_df['썸네일'] = html_df.apply(
            lambda row: f'<a href="{row["영상링크"]}" target="_blank" title="클릭하여 영상 보기">'
                        f'<img src="{row["썸네일"]}" style="width: 160px; height: 90px; object-fit: cover; border-radius: 8px; box-shadow: 0px 3px 6px rgba(0,0,0,0.2); transition: transform 0.2s;" '
                        f'onmouseover="this.style.transform=\'scale(1.05)\'" onmouseout="this.style.transform=\'scale(1)\'"></a>',
            axis=1
        )
        html_df = html_df.drop(columns=['영상링크'])
    
    table_html = html_df.to_html(escape=False, index=False, justify='center')
    table_html = table_html.replace('<table border="1" class="dataframe">', '<table class="custom-table">')
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ margin: 0; padding: 0; font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; background-color: transparent; }}
        .table-container {{ width: 100%; height: 100vh; overflow: auto; }}
        .custom-table {{ min-width: 2200px; width: 100%; border-collapse: collapse; text-align: center; font-size: 14px; background-color: white; }}
        .custom-table th {{ background-color: #f4f6f9; color: #333; padding: 12px 10px; border: 1px solid #ddd; white-space: nowrap; position: sticky; top: 0; z-index: 1; }}
        .custom-table td {{ padding: 10px; border: 1px solid #ddd; vertical-align: middle; color: #333; white-space: nowrap; }}
        .custom-table tr:hover {{ background-color: #f0f4f8; }}
    </style>
    </head>
    <body>
        <div class="table-container">
            {table_html}
        </div>
    </body>
    </html>
    """
    return html_content


# --- 🎨 사이드바 (설정 영역) ---
with st.sidebar:
    st.title("⚙️ 수집 설정 패널")
    search_query = st.text_input("🔍 검색어 입력", placeholder="예: 다이소 추천템")
    
    with st.expander("📌 검색 설정", expanded=True):
        col1, col2 = st.columns(2)
        with col1: sort_by = st.selectbox("정렬 기준", ["조회수순", "최신순"])
        with col2: license_type = st.selectbox("라이선스", ["전체", "재사용 OK"])
        video_type = st.selectbox("타입", ["쇼츠+롱폼", "쇼츠", "롱폼(4~20분)", "20분이상"])
        video_count = st.selectbox("영상 수집 수", ["50개 (테스트용)", "100개", "500개"])
        period = st.selectbox("기간 선택", ["모든기간", "1년 이내", "6개월 이내", "3개월 이내", "1개월 이내", "7일 이내", "1일 이내", "1시간 이내", "직접입력"])
        country = st.selectbox("국가 선택", ["한국", "일본", "미국", "대만", "영국", "캐나다", "호주", "독일", "프랑스", "스페인", "인도", "인도네시아", "러시아"])

    with st.expander("🏷️ 필터 설정", expanded=True):
        views_filter = st.selectbox("조회수 필터", ["선택안함", "1만 이상", "5만 이상", "10만 이상", "50만 이상", "100만 이상"])
        subs_filter = st.selectbox("구독자수 필터", ["선택안함", "1천명 이하", "5천명 이하", "1만명 이하", "5만명 이하", "10만명 이하"])

    with st.expander("🔑 설정 (API 키)", expanded=False):
        yt_api_key = st.text_input("유튜브 API 키", value=saved_keys.get("youtube", ""), type="password")
        gemini_api_key = st.text_input("제미나이 API 키", value=saved_keys.get("gemini", ""), type="password")
        if st.button("💾 API 키 저장", use_container_width=True):
            save_api_keys(yt_api_key, gemini_api_key)
            st.success("키가 성공적으로 저장되었습니다!")

    st.divider()
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("🚀 검색 시작", type="primary", use_container_width=True):
            st.session_state.view_mode = 'search'
    with btn_col2:
        if st.button("🔥 트렌드 보기", use_container_width=True):
            st.session_state.view_mode = 'trend'

# --- 🖥️ 메인 화면 ---
st.title("📈 유튜브 트렌드 마이닝 대시보드")

if st.session_state.view_mode == 'trend':
    st.subheader("🔥 실시간 검색어 트렌드 Top 10")
    col_g, col_nb, col_n = st.columns(3)
    with col_g:
        st.markdown("##### 🌐 구글 실시간 트렌드")
        st.dataframe(get_google_trends(), hide_index=True, use_container_width=True)
    with col_n:
        st.markdown("##### 🟢 네이버 실시간 (이슈)")
        st.dataframe(get_naver_realtime(), hide_index=True, use_container_width=True)
    with col_nb:
        st.markdown("##### 💼 네이버 비즈 인기")
        st.dataframe(pd.DataFrame({"순위": range(1, 11), "키워드": ["🔒 API 연동 필요"] * 10}), hide_index=True, use_container_width=True)

elif st.session_state.view_mode == 'search':
    if search_query == "":
        st.warning("왼쪽 패널에서 검색어를 입력해주세요!")
    elif not yt_api_key:
        st.error("🔑 왼쪽 패널에서 '유튜브 API 키'를 입력해주세요!")
    else:
        with st.spinner(f"'{search_query}' 데이터를 정밀 수집 중입니다..."):
            try:
                youtube = build('youtube', 'v3', developerKey=yt_api_key)
                max_res = 50 if "50개" in video_count else 50
                
                license_param = 'creativeCommon' if license_type == "재사용 OK" else 'any'
                
                published_after = None
                if period != "모든기간" and period != "직접입력":
                    now = datetime.utcnow()
                    if "1년" in period: dt = now - timedelta(days=365)
                    elif "6개월" in period: dt = now - timedelta(days=180)
                    elif "3개월" in period: dt = now - timedelta(days=90)
                    elif "1개월" in period: dt = now - timedelta(days=30)
                    elif "7일" in period: dt = now - timedelta(days=7)
                    elif "1일" in period: dt = now - timedelta(days=1)
                    elif "1시간" in period: dt = now - timedelta(hours=1)
                    published_after = dt.isoformat("T") + "Z"
                
                search_kwargs = {
                    'q': search_query, 'part': 'id,snippet', 'maxResults': max_res, 
                    'type': 'video', 'videoLicense': license_param
                }
                if published_after: search_kwargs['publishedAfter'] = published_after
                
                search_response = youtube.search().list(**search_kwargs).execute()
                
                video_ids = []
                channel_ids = set()
                for item in search_response.get('items', []):
                    if 'videoId' in item.get('id', {}):
                        v_id = item['id']['videoId']
                        video_ids.append(v_id)
                        channel_ids.add(item['snippet']['channelId'])
                
                channel_ids = list(channel_ids)
                
                if not video_ids:
                    st.warning("조건에 맞는 검색 결과가 없습니다.")
                else:
                    channel_stats = {}
                    if channel_ids:
                        channels_response = youtube.channels().list(id=','.join(channel_ids), part='statistics').execute()
                        for ch in channels_response.get('items', []):
                            channel_stats[ch['id']] = {
                                'subs': int(ch['statistics'].get('subscriberCount', 0)),
                                'total_views': int(ch['statistics'].get('viewCount', 0)),
                                'video_count': int(ch['statistics'].get('videoCount', 0))
                            }

                    videos_response = youtube.videos().list(id=','.join(video_ids), part='snippet,statistics,contentDetails').execute()
                    
                    real_data = []
                    progress_bar = st.progress(0)
                    for idx, video in enumerate(videos_response.get('items', [])):
                        v_id = video['id']
                        snippet = video['snippet']
                        stats = video.get('statistics', {})
                        ch_id = snippet['channelId']
                        
                        v_views = int(stats.get('viewCount', 0))
                        v_likes = int(stats.get('likeCount', 0))
                        v_comments = int(stats.get('commentCount', 0))
                        
                        c_stat = channel_stats.get(ch_id, {'subs': 0, 'total_views': 0, 'video_count': 0})
                        subs = c_stat['subs']
                        ch_total_views = c_stat['total_views']
                        ch_video_count = c_stat['video_count']
                        
                        engagement = round(((v_likes + v_comments) / max(v_views, 1)) * 100, 2)
                        perf_ratio = round(v_views / subs, 2) if subs > 0 else 0.0
                        contribution = round((v_views / ch_total_views) * 100, 2) if ch_total_views > 0 else 0.0
                        
                        duration_sec = parse_youtube_duration(video['contentDetails']['duration'])
                        thumb = snippet['thumbnails'].get('mqdefault', snippet['thumbnails']['default'])['url']
                        
                        caption = "자막 없음"
                        try:
                            t_list = YouTubeTranscriptApi.get_transcript(v_id, languages=['ko', 'en'])
                            full_t = " ".join([t['text'] for t in t_list])
                            caption = full_t[:150] + "..." if len(full_t) > 150 else full_t
                        except:
                            caption = "🚫 자막 없음"

                        best_comment = "-"
                        try:
                            comment_response = youtube.commentThreads().list(
                                part="snippet", videoId=v_id, maxResults=1, order="relevance"
                            ).execute()
                            if comment_response.get('items'):
                                best_comment = comment_response['items'][0]['snippet']['topLevelComment']['snippet']['textDisplay']
                                best_comment = re.sub('<[^<]+?>', '', best_comment)
                        except:
                            best_comment = "댓글 비활성화"

                        real_data.append({
                            "썸네일": thumb,
                            "채널명": snippet['channelTitle'],
                            "제목": snippet['title'],
                            "게시일": snippet['publishedAt'][:10],
                            "자막요약": caption,
                            "구독자수(명)": f"{subs:,}", 
                            "조회수(회)": f"{v_views:,}",
                            "채널 기여도(%)": contribution,
                            "성과도 배율(배)": perf_ratio,
                            "좋아요수(개)": f"{v_likes:,}",
                            "댓글수(개)": f"{v_comments:,}",
                            "베스트댓글": best_comment,
                            "참여율(%)": engagement,
                            "총 영상수(개)": f"{ch_video_count:,}",
                            "CII": "AI 분석대기",
                            "영상길이(초)": duration_sec, 
                            "영상 길이": format_duration(duration_sec),
                            "영상링크": f"https://youtu.be/{v_id}"
                        })
                        progress_bar.progress((idx + 1) / len(videos_response.get('items', [])))
                    
                    progress_bar.empty()
                    df = pd.DataFrame(real_data)
                    
                    if not df.empty:
                        if video_type == "쇼츠": df = df[df['영상길이(초)'] <= 60]
                        elif video_type == "롱폼(4~20분)": df = df[(df['영상길이(초)'] > 60) & (df['영상길이(초)'] <= 1200)]
                        elif video_type == "20분이상": df = df[df['영상길이(초)'] > 1200]
                            
                        if views_filter != "선택안함":
                            v_limit = {"1만 이상": 10000, "5만 이상": 50000, "10만 이상": 100000, "50만 이상": 500000, "100만 이상": 1000000}
                            df = df[df['조회수(회)'].str.replace(',','').astype(int) >= v_limit.get(views_filter, 0)]
                            
                        if subs_filter != "선택안함":
                            s_limit = {"1천명 이하": 1000, "5천명 이하": 5000, "1만명 이하": 10000, "5만명 이하": 50000, "10만명 이하": 100000}
                            df = df[df['구독자수(명)'].str.replace(',','').astype(int) <= s_limit.get(subs_filter, 999999999)]
                        
                        if '영상길이(초)' in df.columns: df = df.drop(columns=['영상길이(초)'])

                    if not df.empty:
                        if sort_by == "조회수순":
                            df['temp'] = df['조회수(회)'].str.replace(',','').astype(int)
                            df = df.sort_values(by="temp", ascending=False).drop(columns=['temp']).reset_index(drop=True)
                        else:
                            df = df.sort_values(by="게시일", ascending=False).reset_index(drop=True)
                            
                        st.success(f"🎉 데이터 수집 및 분석 완료! (총 {len(df)}개)")
                        
                        df_placeholder = st.empty()
                        with df_placeholder.container():
                            components.html(render_large_thumbnail_table(df), height=650, scrolling=True)

                        # 💡 엑셀 파일 다운로드 버튼 (한글 절대 안 깨짐)
                        excel_data = to_excel(df)
                        st.download_button(
                            label="📥 엑셀(.xlsx) 파일 다운로드",
                            data=excel_data,
                            file_name=f"{search_query}_youtube_result.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        
                        # AI 분석 영역
                        st.divider()
                        st.subheader("✨ 제미나이 AI 트렌드 & CII 지표 분석")
                        
                        if not gemini_api_key:
                            st.warning("사이드바에서 제미나이 API 키를 입력하면 AI 분석 기능을 쓸 수 있습니다.")
                        else:
                            if st.button("🚀 AI 분석 시작"):
                                with st.spinner("AI가 데이터를 분석 중입니다..."):
                                    try:
                                        genai.configure(api_key=gemini_api_key)
                                        model = genai.GenerativeModel('gemini-1.5-flash')
                                        ai_data = df[['제목', '조회수(회)', '베스트댓글']].to_dict(orient='records')
                                        prompt = f"다음 데이터를 분석해 트렌드 3줄 요약과 각 영상별 CII 등급(great, good, soso)을 JSON으로 주시오. 데이터: {ai_data}"
                                        
                                        response = model.generate_content(prompt)
                                        raw_text = response.text.strip()
                                        
                                        if raw_text.startswith("```json"):
                                            raw_text = raw_text[7:-3].strip()
                                        elif raw_text.startswith("```"):
                                            raw_text = raw_text[3:-3].strip()
                                        
                                        result_json = json.loads(raw_text)
                                        st.info(f"**💡 AI 분석 리포트**\n\n{result_json.get('summary', '요약 실패')}")
                                        
                                        cii_res = result_json.get('cii_list', [])
                                        df['CII'] = (cii_res + ["-"] * len(df))[:len(df)]
                                        
                                        with df_placeholder.container():
                                            components.html(render_large_thumbnail_table(df), height=650, scrolling=True)
                                        
                                        # 💡 AI 결과 포함 엑셀 다운로드
                                        excel_ai_data = to_excel(df)
                                        st.download_button(
                                            label="📥 AI 분석 완료 엑셀(.xlsx) 다운로드",
                                            data=excel_ai_data,
                                            file_name=f"{search_query}_ai_analyzed.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            key="ai_excel_dl"
                                        )
                                            
                                    except Exception as ai_e:
                                        st.error(f"AI 분석 중 오류: {ai_e}")
                    else:
                        st.warning("⚠️ 조건에 맞는 영상이 없습니다.")
            except Exception as e:
                st.error(f"데이터 수집 중 오류: {e}")