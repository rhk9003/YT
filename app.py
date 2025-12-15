import streamlit as st
import requests
import google.generativeai as genai
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# ==========================================
# 1. 系統配置與 API 設定
# ==========================================

st.set_page_config(
    page_title="YouTube 戰略內容切入分析儀",
    page_icon="🎯",
    layout="wide"
)

# 側邊欄配置
with st.sidebar:
    st.header("🔑 API 金鑰設定")
    GEMINI_API_KEY = st.text_input("Gemini API Key", type="password")
    YOUTUBE_API_KEY = st.text_input("YouTube Data API Key", type="password", help="需至 Google Cloud Console 啟用 YouTube Data API v3")
    
    st.markdown("---")
    st.markdown("**分析模型設定**")
    MODEL_VERSION = st.selectbox("Gemini 模型", ["gemini-3-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash"])

# ==========================================
# 2. 核心功能函式庫
# ==========================================

def get_youtube_suggestions(keyword):
    """
    (您的程式碼) 抓取 YouTube 搜尋下拉選單的自動完成關鍵字
    """
    try:
        url = "http://suggestqueries.google.com/complete/search"
        params = {
            "client": "firefox",
            "ds": "yt",
            "q": keyword,
            "hl": "zh-TW"
        }
        response = requests.get(url, params=params, timeout=2)
        data = response.json()
        if data and len(data) > 1:
            return data[1]
        return []
    except Exception:
        return []

def search_youtube_api(api_key, query, max_results=5):
    """
    第一階段：使用 YouTube Data API 獲取影片列表與詳細數據 (觀看數)
    """
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # 1. 搜尋影片 ID
        search_response = youtube.search().list(
            q=query,
            part='id,snippet',
            maxResults=max_results,
            type='video',
            order='relevance' # 依相關性排序
        ).execute()

        video_ids = [item['id']['videoId'] for item in search_response['items']]
        
        # 2. 獲取詳細數據 (搜尋 API 不給播放次數，需用 videos API 再查一次)
        stats_response = youtube.videos().list(
            part='snippet,statistics',
            id=','.join(video_ids)
        ).execute()

        results = []
        for item in stats_response['items']:
            results.append({
                'id': item['id'],
                'title': item['snippet']['title'],
                'description': item['snippet']['description'],
                'channel': item['snippet']['channelTitle'],
                'publish_time': item['snippet']['publishedAt'],
                'view_count': int(item['statistics'].get('viewCount', 0)),
                'thumbnail': item['snippet']['thumbnails']['high']['url'],
                'url': f"https://www.youtube.com/watch?v={item['id']}"
            })
        
        # 依照觀看次數排序 (可選，目前保持相關性排序但提供數據)
        return results

    except Exception as e:
        st.error(f"YouTube API 錯誤: {e}")
        return []

def get_transcript(video_id):
    """獲取字幕內容 (優先繁中)"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['zh-TW', 'zh-Hant', 'zh-CN'])
            obj = transcript.fetch()
        except:
            try:
                transcript = transcript_list.find_transcript(['en'])
                obj = transcript.translate('zh-Hant').fetch()
            except:
                transcript = transcript_list[0]
                obj = transcript.translate('zh-Hant').fetch()
        
        formatter = TextFormatter()
        return formatter.format_transcript(obj), True
    except:
        return "", False

# ==========================================
# 3. AI 分析函式 (Gemini)
# ==========================================

def analyze_search_intent(api_key, query, videos_data):
    """
    第一階段 AI：分析搜尋結果意圖
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_VERSION)
    
    # 整理給 AI 的摘要數據
    data_summary = ""
    for v in videos_data:
        data_summary += f"- 標題: {v['title']}\n  觀看數: {v['view_count']}\n  描述摘要: {v['description'][:100]}...\n\n"

    prompt = f"""
    你是一個搜尋意圖分析專家。
    使用者搜尋關鍵字：「{query}」。
    以下是 YouTube API 回傳的前幾名高相關性影片數據：
    
    {data_summary}
    
    請分析：
    1. 【使用者痛點】：搜尋這個詞的人，這時候最想解決什麼問題？
    2. 【市場缺口】：目前的熱門影片主要集中在講什麼？還有什麼角度是被忽略的？
    3. 【意圖分類】：這是屬於「資訊尋求」、「交易決策」還是「娛樂消遣」？
    請用精簡的 Markdown 條列式回答。
    """
    
    response = model.generate_content(prompt)
    return response.text

def generate_content_strategy(api_key, target_videos_context, user_goal):
    """
    第二階段 AI：內容切入策略 (相關、延伸、超越)
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_VERSION)

    prompt = f"""
    你是一位頂尖的 YouTube 內容策略顧問。
    使用者希望針對以下競品影片進行內容製作。
    
    【競品詳細資料 (含字幕重點)】
    {target_videos_context}
    
    【使用者目標】
    {user_goal}
    
    請針對這些競品，提出具體的影片製作策略，請務必包含以下三個面向的切入點：
    
    1. **相關 (Related)**：如何利用這些影片的現有熱度？(例如：製作回應影片、針對同一主題的補充觀點、利用類似的關鍵字佈局)。
    2. **延伸 (Extended)**：這些影片沒講清楚的是什麼？(例如：深入探討某個被帶過的細節、提供實作步驟、提供更多數據佐證)。
    3. **超越 (Superior)**：如何製作一支品質更高的影片？(例如：更好的視覺化、更獨特的觀點、更強烈的情緒共鳴、更權威的資訊來源)。
    
    請給出具體的標題建議與腳本大綱方向。
    """
    
    response = model.generate_content(prompt)
    return response.text

# ==========================================
# 4. Streamlit 主程式邏輯
# ==========================================

st.title("🎯 YouTube 戰略內容切入分析儀")
st.markdown("流程：`關鍵字意圖分析` ➝ `競品數據爬取` ➝ `AI 策略生成 (相關/延伸/超越)`")

# Session State 管理
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "intent_analysis" not in st.session_state:
    st.session_state.intent_analysis = ""

# --- STEP 1: 搜尋與意圖分析 ---
st.subheader("STEP 1: 搜尋與市場意圖分析")

col1, col2 = st.columns([2, 1])
with col1:
    search_query = st.text_input("輸入核心關鍵字", placeholder="例如：AI 影片生成")
    
    # 顯示建議
    suggestions = []
    if search_query:
        suggestions = get_youtube_suggestions(search_query)
        
    target_keyword = search_query
    if suggestions:
        st.write("💡 建議關鍵字：")
        cols_s = st.columns(4)
        for i, s in enumerate(suggestions[:4]):
            with cols_s[i]:
                if st.button(s, key=f"s_{i}"):
                    target_keyword = s
                    st.rerun() # 重新整理以更新輸入框 (或直接觸發)

with col2:
    st.info(f"鎖定關鍵字：**{target_keyword}**")
    if st.button("🔍 執行搜尋與意圖分析", type="primary"):
        if not GEMINI_API_KEY or not YOUTUBE_API_KEY:
            st.error("請先在左側設定 API Key")
        else:
            with st.spinner("正在呼叫 YouTube API 並進行 AI 意圖分析..."):
                # 1. 抓資料
                results = search_youtube_api(YOUTUBE_API_KEY, target_keyword, max_results=6)
                st.session_state.search_results = results
                
                # 2. AI 分析意圖 (Stage 1)
                if results:
                    analysis = analyze_search_intent(GEMINI_API_KEY, target_keyword, results)
                    st.session_state.intent_analysis = analysis
                else:
                    st.warning("找不到相關影片")

# 顯示 Stage 1 結果
if st.session_state.search_results:
    st.markdown("### 📊 市場意圖分析報告")
    st.markdown(st.session_state.intent_analysis)
    st.divider()

# --- STEP 2: 勾選競品與策略生成 ---
if st.session_state.search_results:
    st.subheader("STEP 2: 選擇競品進行戰略打擊")
    st.caption("請勾選您想參考或超越的對手：")

    # 顯示影片列表供勾選
    selected_videos = []
    cols = st.columns(3)
    for idx, video in enumerate(st.session_state.search_results):
        with cols[idx % 3]:
            st.image(video['thumbnail'], use_container_width=True)
            st.markdown(f"**{video['title']}**")
            st.markdown(f"👀 觀看數: `{video['view_count']:,}`")
            if st.checkbox("納入分析", key=video['id']):
                selected_videos.append(video)
    
    st.markdown(f"已選擇 **{len(selected_videos)}** 個競品")

    # 策略生成按鈕
    if selected_videos:
        st.markdown("---")
        st.subheader("STEP 3: 生成切入策略")
        user_goal = st.text_area("您的創作目標 (選填)", value="我想做一支能蹭到流量，但在專業度上超越他們的影片")
        
        if st.button("🚀 生成「相關、延伸、超越」策略", type="primary"):
            full_context = ""
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 爬取字幕與整合資料
            for i, vid in enumerate(selected_videos):
                status_text.text(f"正在分析對手資料: {vid['title']}...")
                
                transcript, has_sub = get_transcript(vid['id'])
                sub_status = "有字幕" if has_sub else "無字幕 (僅參考標題/描述)"
                
                full_context += f"\n\n=== 競品影片: {vid['title']} ===\n"
                full_context += f"觀看數: {vid['view_count']}\n"
                full_context += f"影片描述: {vid['description']}\n"
                full_context += f"字幕狀態: {sub_status}\n"
                full_context += f"字幕內容摘要 (前 5000 字): {transcript[:5000]}\n" # 避免 token 爆炸，視情況調整
                
                progress_bar.progress((i + 1) / len(selected_videos))
            
            status_text.text("正在進行戰略推演...")
            
            # AI 生成策略 (Stage 2)
            try:
                strategy_report = generate_content_strategy(GEMINI_API_KEY, full_context, user_goal)
                st.success("戰略分析完成！")
                st.markdown(strategy_report)
                
                st.download_button("下載策略報告 (.md)", strategy_report, "strategy.md")
            except Exception as e:
                st.error(f"AI 生成失敗: {e}")
