import streamlit as st
import google.generativeai as genai
# 修改點：改用 youtubesearchpython (對應 requirements.txt)
from youtubesearchpython import VideosSearch
from youtube_transcript_api import YouTubeTranscriptApi
import urllib.parse
import json

# 設定頁面配置
st.set_page_config(page_title="YouTube 內容策略分析戰情室", layout="wide")

# --- 側邊欄：設定 ---
st.sidebar.title("🔧 系統設定")
api_key = st.sidebar.text_input("輸入 Google Gemini API Key", type="password")
model_name = st.sidebar.text_input("模型名稱", value="gemini-1.5-pro", help="請輸入您想使用的模型版本，如 gemini-1.5-pro 或 gemini-3-pro")

# 初始化 Gemini
if api_key:
    genai.configure(api_key=api_key)

# --- 工具函式 ---

def get_video_id(url):
    """從 YouTube 網址提取 Video ID"""
    try:
        query = urllib.parse.urlparse(url)
        if query.hostname == 'youtu.be':
            return query.path[1:]
        if query.hostname in ('www.youtube.com', 'youtube.com'):
            if query.path == '/watch':
                p = urllib.parse.parse_qs(query.query)
                return p['v'][0]
            if query.path[:7] == '/embed/':
                return query.path.split('/')[2]
            if query.path[:3] == '/v/':
                return query.path.split('/')[2]
    except:
        return None
    return None

def search_youtube_videos(keywords, max_results=5):
    """搜尋 YouTube 並返回前幾名結果 (使用 youtube-search-python)"""
    try:
        videosSearch = VideosSearch(keywords, limit=max_results)
        results = videosSearch.result()['result']
        
        processed_results = []
        for video in results:
            # 處理觀看次數格式 (API 返回結構可能不同，做安全存取)
            views = "N/A"
            if 'viewCount' in video:
                if isinstance(video['viewCount'], dict):
                    views = video['viewCount'].get('short', 'N/A')
                else:
                    views = str(video['viewCount'])

            processed_results.append({
                "title": video['title'],
                "link": video['link'],
                "id": video['id'],
                "views": views
            })
        return processed_results
    except Exception as e:
        st.error(f"搜尋發生錯誤: {e}")
        return []

def get_video_transcript(video_id):
    """獲取影片字幕"""
    try:
        # 嘗試獲取中文或英文字幕
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['zh-TW', 'zh-CN', 'en'])
        text = " ".join([t['text'] for t in transcript_list])
        return text
    except Exception as e:
        # 常見錯誤處理
        error_msg = str(e)
        if "Subtitles are disabled" in error_msg:
            return "錯誤：該影片未提供字幕 (CC) 或字幕被停用。"
        elif "No transcripts were found" in error_msg:
            return "錯誤：找不到支援語言的字幕 (僅支援繁中/簡中/英文)。"
        return f"無法獲取字幕: {error_msg}"

def analyze_with_gemini(prompt, model_ver):
    """呼叫 Gemini API 進行分析"""
    try:
        model = genai.GenerativeModel(model_ver)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"API 呼叫錯誤: {str(e)}"

# --- 主介面 ---

st.title("📊 YouTube 內容策略分析戰情室")
st.markdown("---")

# 狀態管理
if 'search_results' not in st.session_state:
    st.session_state.search_results = []
if 'analysis_step1' not in st.session_state:
    st.session_state.analysis_step1 = ""

# === 第一階段：關鍵字搜索與市場意圖分析 ===
st.header("第一階段：關鍵字搜索與意圖偵察")

keywords = st.text_input("輸入目標關鍵字 (例如：『生產力工具』、『AI 繪圖教學』)")

if st.button("🚀 啟動偵察", key="search_btn"):
    if not api_key:
        st.error("請先在側邊欄輸入 API Key")
    elif not keywords:
        st.warning("請輸入關鍵字")
    else:
        with st.spinner(f"正在分析 YouTube 戰場：{keywords}..."):
            # 1. 爬取 YouTube 搜尋結果
            st.session_state.search_results = search_youtube_videos(keywords)
            
            if st.session_state.search_results:
                # 顯示結果
                st.subheader(f"🔍 '{keywords}' 搜尋排名 Top 5")
                for idx, vid in enumerate(st.session_state.search_results):
                    st.markdown(f"**{idx+1}. [{vid['title']}]({vid['link']})** (觀看數: {vid['views']})")
                
                # 2. Gemini 意圖分析
                search_data_str = "\n".join([f"{i+1}. {v['title']}" for i, v in enumerate(st.session_state.search_results)])
                
                prompt_intent = f"""
                你是一位專業的內容策略分析師。我正在針對關鍵字「{keywords}」進行 YouTube 市場調查。
                以下是該關鍵字目前搜尋排名最前五名的影片標題：

                {search_data_str}

                請根據這些標題，幫我進行深入推論與分析：
                1. **搜尋意圖分析**：搜尋這個字的人，背後真正的心理需求和動機是什麼？(是想解決問題？尋找娛樂？還是學習技能？)
                2. **內容缺口 (Content Gap)**：根據現有前五名的標題，推論有沒有什麼是搜尋者可能想看到，但目前的熱門內容似乎沒有直接回答或涵蓋到的面向？
                
                請以條列式、專業且具體的語氣回答。
                """
                
                analysis = analyze_with_gemini(prompt_intent, model_name)
                st.session_state.analysis_step1 = analysis
            else:
                st.warning("未能找到相關影片，請稍後再試或更換關鍵字。")
            
if st.session_state.analysis_step1:
    st.markdown("### 🧠 Gemini 搜尋意圖與缺口分析")
    st.info(st.session_state.analysis_step1)

st.markdown("---")

# === 第二階段：競品深度解構 ===
st.header("第二階段：競品內容深度解構")
st.markdown("請輸入您想鎖定的影片網址 (一行一個)，系統將爬取字幕並進行結構拆解。")

video_urls_input = st.text_area("貼上影片網址", height=150, help="貼上剛剛搜尋到的，或是您想參考的特定影片網址")

if st.button("🧬 進行 DNA 解構分析", key="analyze_btn"):
    if not api_key:
        st.error("請先輸入 API Key")
    elif not video_urls_input:
        st.warning("請貼上影片網址")
    else:
        urls = video_urls_input.strip().split('\n')
        transcripts_data = ""
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        valid_videos = 0
        
        for i, url in enumerate(urls):
            url = url.strip()
            if not url: continue
            
            vid_id = get_video_id(url)
            if vid_id:
                status_text.text(f"正在讀取影片字幕 ({i+1}/{len(urls)}): {url} ...")
                transcript = get_video_transcript(vid_id)
                
                # 簡單檢查回傳是否為錯誤訊息 (如果字串開頭包含"錯誤"或"無法")
                if transcript.startswith("錯誤") or transcript.startswith("無法"):
                    st.warning(f"影片 {vid_id} 略過: {transcript}")
                else:
                    transcripts_data += f"\n=== 影片 ID: {vid_id} 的字幕內容 ===\n{transcript[:20000]}...\n"
                    valid_videos += 1
            else:
                st.warning(f"無效的 YouTube 網址格式: {url}")
            
            progress_bar.progress((i + 1) / len(urls))
            
        if valid_videos > 0:
            status_text.text("正在呼叫 Gemini 進行深度分析...")
            
            prompt_structure = f"""
            我收集了幾部關於該主題的熱門影片字幕內容。請閱讀以下內容並擔任內容架構師的角色：

            {transcripts_data}

            ---
            任務需求：
            請綜合分析以上影片內容，並回答以下問題：
            
            1. **主要切入點 (Angle)**：這些影片大多是從什麼角度切入這個主題的？(例如：恐懼行銷、手把手教學、趨勢分析、個人經驗談？)
            2. **敘述架構 (Structure)**：歸納它們的腳本邏輯。它們是如何開場？中間如何鋪陳？最後如何結尾？
            3. **手法分析 (Techniques)**：它們使用了哪些吸引觀眾的技巧？(例如：反直覺的觀點、大量數據佐證、情感共鳴？)
            4. **延伸策略建議 (Strategy)**：如果我要以這些影片為競爭目標，製作一支「延伸」且「超越」它們內容的影片，我該準備哪些差異化的主題或內容？請給我 3 個具體的影片企劃方向。

            輸出格式請使用 Markdown，保持專業、客觀。
            """
            
            final_analysis = analyze_with_gemini(prompt_structure, model_name)
            
            st.success("分析完成！")
            st.markdown("### 📝 影片切入點與架構解構報告")
            st.write(final_analysis)
        else:
            st.error("沒有任何影片成功提取到字幕，無法進行分析。")
