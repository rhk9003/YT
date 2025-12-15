import streamlit as st
import requests
import google.generativeai as genai
from googleapiclient.discovery import build
import concurrent.futures

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
    MODEL_VERSION = st.selectbox("Gemini 模型", ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"])
    
    st.markdown("---")
    st.markdown("**字幕爬取設定**")
    MAX_CONCURRENT_AI = st.slider("同時爬取影片數", 1, 5, 3, help="太高可能觸發 API 限制")

# ==========================================
# 2. 核心功能函式庫
# ==========================================

def get_youtube_suggestions(keyword):
    """抓取 YouTube 搜尋下拉選單的自動完成關鍵字"""
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
    """使用 YouTube Data API 獲取影片列表與詳細數據"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        search_response = youtube.search().list(
            q=query,
            part='id,snippet',
            maxResults=max_results,
            type='video',
            order='relevance'
        ).execute()

        video_ids = [item['id']['videoId'] for item in search_response['items']]
        
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
        
        return results

    except Exception as e:
        st.error(f"YouTube API 錯誤: {e}")
        return []

# ==========================================
# 3. AI 字幕爬取與分析函式 (核心修改)
# ==========================================

def extract_video_content_via_ai(api_key, video_info, model_version):
    """
    🔥 核心功能：用 AI 直接爬取單支 YouTube 影片的內容摘要
    給 AI 影片 URL，讓它自己去解析字幕/內容
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)
    
    video_url = video_info['url']
    video_title = video_info['title']
    
    prompt = f"""
    請分析這支 YouTube 影片的完整內容：
    影片網址：{video_url}
    影片標題：{video_title}
    
    請提供：
    1. **影片主題**：這支影片在講什麼？(1-2句)
    2. **核心論點**：影片的主要觀點或教學重點 (條列3-5點)
    3. **內容結構**：影片的段落架構 (開頭講什麼、中間講什麼、結尾講什麼)
    4. **關鍵金句**：影片中有價值的句子或觀點 (2-3句)
    5. **目標受眾**：這支影片是拍給誰看的？
    6. **內容缺口**：這支影片沒講到但觀眾可能想知道的 (1-2點)
    
    請用繁體中文回答，格式清晰。
    """
    
    try:
        response = model.generate_content(prompt)
        return {
            'video_id': video_info['id'],
            'title': video_title,
            'url': video_url,
            'view_count': video_info['view_count'],
            'ai_analysis': response.text,
            'success': True
        }
    except Exception as e:
        return {
            'video_id': video_info['id'],
            'title': video_title,
            'url': video_url,
            'view_count': video_info['view_count'],
            'ai_analysis': f"爬取失敗: {str(e)}",
            'success': False
        }

def batch_extract_videos(api_key, videos_list, model_version, max_workers=3):
    """
    批次爬取多支影片，使用 ThreadPoolExecutor 並行處理
    """
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_video = {
            executor.submit(extract_video_content_via_ai, api_key, video, model_version): video 
            for video in videos_list
        }
        
        for future in concurrent.futures.as_completed(future_to_video):
            video = future_to_video[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({
                    'video_id': video['id'],
                    'title': video['title'],
                    'url': video['url'],
                    'view_count': video['view_count'],
                    'ai_analysis': f"執行錯誤: {str(e)}",
                    'success': False
                })
    
    return results

def analyze_search_intent(api_key, query, videos_data, model_version):
    """第一階段 AI：分析搜尋結果意圖"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)
    
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

def generate_content_strategy(api_key, all_video_analyses, user_goal, model_version):
    """
    🔥 最終整合：綜合所有爬到的影片分析，產出策略報告
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)

    # 整理所有影片的分析結果
    combined_context = ""
    for idx, analysis in enumerate(all_video_analyses, 1):
        combined_context += f"""
========================================
【競品 {idx}】{analysis['title']}
網址：{analysis['url']}
觀看數：{analysis['view_count']:,}
----------------------------------------
{analysis['ai_analysis']}
========================================

"""

    prompt = f"""
    你是一位頂尖的 YouTube 內容策略顧問。
    
    我已經幫你分析了以下 {len(all_video_analyses)} 支競品影片的詳細內容：
    
    {combined_context}
    
    【使用者的創作目標】
    {user_goal}
    
    請根據以上所有競品分析，提出完整的影片製作策略。務必包含：
    
    ## 🎯 競品綜合洞察
    - 這些影片的共同特點是什麼？
    - 觀眾反應最好的內容類型是？
    - 市場上明顯的內容缺口在哪？
    
    ## 🔗 相關策略 (Related)
    如何利用這些影片的現有熱度？
    - 具體標題建議 (3個)
    - 關鍵字佈局建議
    - 如何做「回應影片」或「補充觀點」
    
    ## 📈 延伸策略 (Extended)  
    這些影片沒講清楚的是什麼？
    - 可以深入探討的細節 (列舉3點)
    - 實作步驟補充建議
    - 數據佐證強化方向
    
    ## 🚀 超越策略 (Superior)
    如何製作一支品質更高的影片？
    - 視覺化升級建議
    - 獨特觀點切入角度
    - 情緒共鳴點設計
    - 權威性建立方法
    
    ## 📝 推薦腳本大綱
    給出一個完整的影片腳本結構建議。
    
    請用繁體中文回答，格式清晰專業。
    """
    
    response = model.generate_content(prompt)
    return response.text

# ==========================================
# 4. Streamlit 主程式邏輯
# ==========================================

st.title("🎯 YouTube 戰略內容切入分析儀 v2")
st.markdown("流程：`關鍵字意圖分析` ➝ `勾選競品` ➝ `AI 爬取字幕` ➝ `綜合策略生成`")
st.caption("💡 本版本使用 AI 直接爬取影片內容，不依賴傳統字幕 API")

# Session State 管理
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "intent_analysis" not in st.session_state:
    st.session_state.intent_analysis = ""
if "video_analyses" not in st.session_state:
    st.session_state.video_analyses = []

# --- STEP 1: 搜尋與意圖分析 ---
st.subheader("STEP 1: 搜尋與市場意圖分析")

col1, col2 = st.columns([2, 1])
with col1:
    search_query = st.text_input("輸入核心關鍵字", placeholder="例如：AI 影片生成")
    
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
                    st.rerun()

with col2:
    st.info(f"鎖定關鍵字：**{target_keyword}**")
    if st.button("🔍 執行搜尋與意圖分析", type="primary"):
        if not GEMINI_API_KEY or not YOUTUBE_API_KEY:
            st.error("請先在左側設定 API Key")
        else:
            with st.spinner("正在呼叫 YouTube API 並進行 AI 意圖分析..."):
                results = search_youtube_api(YOUTUBE_API_KEY, target_keyword, max_results=6)
                st.session_state.search_results = results
                st.session_state.video_analyses = []  # 清空之前的分析
                
                if results:
                    analysis = analyze_search_intent(GEMINI_API_KEY, target_keyword, results, MODEL_VERSION)
                    st.session_state.intent_analysis = analysis
                else:
                    st.warning("找不到相關影片")

# 顯示 Stage 1 結果
if st.session_state.search_results:
    st.markdown("### 📊 市場意圖分析報告")
    st.markdown(st.session_state.intent_analysis)
    st.divider()

# --- STEP 2: 勾選競品 ---
if st.session_state.search_results:
    st.subheader("STEP 2: 選擇競品進行深度分析")
    st.caption("請勾選您想參考或超越的對手（AI 將爬取這些影片的完整內容）：")

    selected_videos = []
    cols = st.columns(3)
    for idx, video in enumerate(st.session_state.search_results):
        with cols[idx % 3]:
            st.image(video['thumbnail'], use_container_width=True)
            st.markdown(f"**{video['title']}**")
            st.markdown(f"👀 觀看數: `{video['view_count']:,}`")
            st.markdown(f"🔗 [觀看影片]({video['url']})")
            if st.checkbox("納入分析", key=video['id']):
                selected_videos.append(video)
    
    st.markdown(f"已選擇 **{len(selected_videos)}** 個競品")

    # --- STEP 3: AI 爬取與策略生成 ---
    if selected_videos:
        st.markdown("---")
        st.subheader("STEP 3: AI 爬取字幕 & 生成策略")
        
        user_goal = st.text_area(
            "您的創作目標", 
            value="我想做一支能蹭到流量，但在專業度上超越他們的影片",
            help="描述你想達成的目標，AI 會根據這個來制定策略"
        )
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("🤖 AI 爬取選中影片內容", type="secondary"):
                if not GEMINI_API_KEY:
                    st.error("請先設定 Gemini API Key")
                else:
                    st.markdown("#### 📡 正在爬取影片內容...")
                    
                    # 進度顯示
                    progress_bar = st.progress(0)
                    status_container = st.empty()
                    
                    # 顯示正在處理的影片
                    status_container.info(f"正在處理 {len(selected_videos)} 支影片，請稍候...")
                    
                    # 批次爬取
                    analyses = batch_extract_videos(
                        GEMINI_API_KEY, 
                        selected_videos, 
                        MODEL_VERSION,
                        max_workers=MAX_CONCURRENT_AI
                    )
                    
                    progress_bar.progress(100)
                    st.session_state.video_analyses = analyses
                    
                    # 顯示結果摘要
                    success_count = sum(1 for a in analyses if a['success'])
                    status_container.success(f"✅ 完成！成功爬取 {success_count}/{len(analyses)} 支影片")
        
        with col_btn2:
            can_generate = len(st.session_state.video_analyses) > 0
            if st.button("🚀 生成綜合策略報告", type="primary", disabled=not can_generate):
                if not st.session_state.video_analyses:
                    st.warning("請先執行「AI 爬取」")
                else:
                    with st.spinner("正在整合分析，生成策略報告..."):
                        strategy = generate_content_strategy(
                            GEMINI_API_KEY,
                            st.session_state.video_analyses,
                            user_goal,
                            MODEL_VERSION
                        )
                        
                        st.success("🎉 策略報告生成完成！")
                        st.markdown(strategy)
                        
                        st.download_button(
                            "📥 下載策略報告 (.md)", 
                            strategy, 
                            "youtube_strategy_report.md",
                            mime="text/markdown"
                        )
        
        # 顯示已爬取的影片分析詳情 (可展開)
        if st.session_state.video_analyses:
            st.markdown("---")
            st.markdown("#### 📋 各影片爬取結果詳情")
            
            for analysis in st.session_state.video_analyses:
                status_icon = "✅" if analysis['success'] else "❌"
                with st.expander(f"{status_icon} {analysis['title']}", expanded=False):
                    st.markdown(f"**影片網址**: {analysis['url']}")
                    st.markdown(f"**觀看數**: {analysis['view_count']:,}")
                    st.markdown("---")
                    st.markdown(analysis['ai_analysis'])
