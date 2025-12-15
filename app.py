import streamlit as st
import requests
import google.generativeai as genai
from googleapiclient.discovery import build
import concurrent.futures
from datetime import datetime

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
    st.markdown("**搜尋設定**")
    MAX_RESULTS_PER_KEYWORD = st.slider("每個關鍵字抓取影片數", 3, 10, 5)
    MAX_CONCURRENT_AI = st.slider("同時爬取影片數", 1, 5, 3, help="太高可能觸發 API 限制")
    
    st.markdown("---")
    st.markdown("**流程進度**")
    # 動態顯示進度
    step1_done = "search_results" in st.session_state and st.session_state.search_results
    step2_done = "video_analyses" in st.session_state and st.session_state.video_analyses
    step3_done = "final_strategy" in st.session_state and st.session_state.final_strategy
    
    st.markdown(f"{'✅' if step1_done else '⬜'} STEP 1: 搜尋與意圖分析")
    st.markdown(f"{'✅' if step2_done else '⬜'} STEP 2: AI 爬取影片內容")
    st.markdown(f"{'✅' if step3_done else '⬜'} STEP 3: 生成策略報告")

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
        
        if not video_ids:
            return []
        
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
                'url': f"https://www.youtube.com/watch?v={item['id']}",
                'source_keyword': query
            })
        
        return results

    except Exception as e:
        st.error(f"YouTube API 錯誤 ({query}): {e}")
        return []

def search_multiple_keywords(api_key, keywords_list, max_results_per_keyword):
    """批次搜尋多個關鍵字"""
    all_results = []
    seen_ids = set()
    
    for keyword in keywords_list:
        results = search_youtube_api(api_key, keyword, max_results_per_keyword)
        for video in results:
            if video['id'] not in seen_ids:
                seen_ids.add(video['id'])
                all_results.append(video)
    
    return all_results

# ==========================================
# 3. AI 分析函式
# ==========================================

def extract_video_content_via_ai(api_key, video_info, model_version):
    """用 AI 直接爬取單支 YouTube 影片的內容摘要"""
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
            'source_keyword': video_info.get('source_keyword', ''),
            'ai_analysis': response.text,
            'success': True
        }
    except Exception as e:
        return {
            'video_id': video_info['id'],
            'title': video_title,
            'url': video_url,
            'view_count': video_info['view_count'],
            'source_keyword': video_info.get('source_keyword', ''),
            'ai_analysis': f"爬取失敗: {str(e)}",
            'success': False
        }

def batch_extract_videos(api_key, videos_list, model_version, max_workers=3):
    """批次爬取多支影片"""
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
                    'source_keyword': video.get('source_keyword', ''),
                    'ai_analysis': f"執行錯誤: {str(e)}",
                    'success': False
                })
    
    return results

def analyze_search_intent(api_key, keywords_list, videos_data, model_version):
    """第一階段 AI：分析多個關鍵字的搜尋結果意圖"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)
    
    data_summary = ""
    for keyword in keywords_list:
        keyword_videos = [v for v in videos_data if v.get('source_keyword') == keyword]
        if keyword_videos:
            data_summary += f"\n### 關鍵字：「{keyword}」\n"
            for v in keyword_videos[:3]:
                data_summary += f"- 標題: {v['title']}\n  觀看數: {v['view_count']:,}\n  描述摘要: {v['description'][:80]}...\n\n"

    prompt = f"""
    你是一個搜尋意圖分析專家。
    使用者搜尋了以下關鍵字群組：{', '.join(keywords_list)}
    
    以下是各關鍵字的 YouTube 搜尋結果：
    {data_summary}
    
    請分析：
    1. 【關鍵字關聯】：這些關鍵字之間的關係是什麼？使用者可能想達成什麼目標？
    2. 【使用者痛點】：搜尋這些詞的人，最想解決什麼問題？
    3. 【市場缺口】：目前的熱門影片主要集中在講什麼？還有什麼角度是被忽略的？
    4. 【內容機會】：綜合這些關鍵字，最有潛力的內容方向是？
    
    請用精簡的 Markdown 條列式回答。
    """
    
    response = model.generate_content(prompt)
    return response.text

def generate_content_strategy(api_key, all_video_analyses, keywords_list, user_goal, model_version):
    """最終整合策略報告"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)

    combined_context = ""
    for idx, analysis in enumerate(all_video_analyses, 1):
        combined_context += f"""
========================================
【競品 {idx}】{analysis['title']}
來源關鍵字：{analysis.get('source_keyword', 'N/A')}
網址：{analysis['url']}
觀看數：{analysis['view_count']:,}
----------------------------------------
{analysis['ai_analysis']}
========================================

"""

    prompt = f"""
    你是一位頂尖的 YouTube 內容策略顧問。
    
    使用者研究的關鍵字群組：{', '.join(keywords_list)}
    
    我已經幫你分析了以下 {len(all_video_analyses)} 支競品影片的詳細內容：
    
    {combined_context}
    
    【使用者的創作目標】
    {user_goal}
    
    請根據以上所有競品分析，提出完整的影片製作策略。務必包含：
    
    ## 🎯 競品綜合洞察
    - 這些影片的共同特點是什麼？
    - 不同關鍵字的影片有什麼差異？
    - 觀眾反應最好的內容類型是？
    - 市場上明顯的內容缺口在哪？
    
    ## 🔗 相關策略 (Related)
    如何利用這些影片的現有熱度？
    - 具體標題建議 (3個，融合多個關鍵字)
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
# 4. 輔助函式：生成下載內容
# ==========================================

def generate_all_analyses_md(video_analyses):
    """將所有影片分析整合成一份 Markdown"""
    content = f"# YouTube 競品影片分析報告\n\n"
    content += f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    content += f"共分析 {len(video_analyses)} 支影片\n\n"
    content += "---\n\n"
    
    for idx, analysis in enumerate(video_analyses, 1):
        status = "✅ 成功" if analysis['success'] else "❌ 失敗"
        content += f"## {idx}. {analysis['title']}\n\n"
        content += f"- **狀態**: {status}\n"
        content += f"- **來源關鍵字**: {analysis.get('source_keyword', 'N/A')}\n"
        content += f"- **網址**: {analysis['url']}\n"
        content += f"- **觀看數**: {analysis['view_count']:,}\n\n"
        content += f"### 分析內容\n\n{analysis['ai_analysis']}\n\n"
        content += "---\n\n"
    
    return content

# ==========================================
# 5. Streamlit 主程式邏輯
# ==========================================

st.title("🎯 YouTube 戰略內容切入分析儀")
st.caption("支援多關鍵字搜尋 → AI 爬取字幕 → 綜合策略生成｜每個步驟結果皆可下載")

# Session State 初始化
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "intent_analysis" not in st.session_state:
    st.session_state.intent_analysis = ""
if "video_analyses" not in st.session_state:
    st.session_state.video_analyses = []
if "final_keywords" not in st.session_state:
    st.session_state.final_keywords = []
if "suggestions_dict" not in st.session_state:
    st.session_state.suggestions_dict = {}
if "selected_video_ids" not in st.session_state:
    st.session_state.selected_video_ids = []
if "final_strategy" not in st.session_state:
    st.session_state.final_strategy = ""
if "user_goal" not in st.session_state:
    st.session_state.user_goal = "我想做一支能蹭到流量，但在專業度上超越他們的影片"

# ============================================================
# STEP 1: 關鍵字輸入與搜尋
# ============================================================
st.header("STEP 1｜關鍵字搜尋與市場意圖分析")

with st.container(border=True):
    # 1-1: 輸入關鍵字
    st.subheader("1-1. 輸入關鍵字")
    keywords_input = st.text_area(
        "每行一個關鍵字，或用逗號分隔",
        placeholder="AI 影片生成\nAI 剪輯工具\nYouTube 自動化",
        height=100,
        key="keywords_input"
    )
    
    # 解析關鍵字
    input_keywords = []
    if keywords_input:
        for line in keywords_input.replace('，', ',').split('\n'):
            for kw in line.split(','):
                kw = kw.strip()
                if kw:
                    input_keywords.append(kw)
    
    if input_keywords:
        st.caption(f"已輸入 {len(input_keywords)} 個關鍵字：{', '.join(input_keywords)}")

with st.container(border=True):
    # 1-2: 建議關鍵字
    st.subheader("1-2. 取得 YouTube 建議關鍵字（選用）")
    
    col_sug1, col_sug2 = st.columns([1, 3])
    with col_sug1:
        fetch_suggestions_btn = st.button("🔍 取得建議", disabled=not input_keywords)
    
    if fetch_suggestions_btn and input_keywords:
        suggestions_dict = {}
        with st.spinner("正在取得建議關鍵字..."):
            for kw in input_keywords:
                suggestions = get_youtube_suggestions(kw)
                if suggestions:
                    suggestions_dict[kw] = suggestions
        st.session_state.suggestions_dict = suggestions_dict

    # 顯示並勾選建議
    selected_suggestions = []
    if st.session_state.suggestions_dict:
        for base_kw, suggestions in st.session_state.suggestions_dict.items():
            st.markdown(f"**{base_kw}** 的延伸：")
            cols = st.columns(4)
            for i, sug in enumerate(suggestions[:8]):
                with cols[i % 4]:
                    if st.checkbox(sug, key=f"sug_{base_kw}_{i}"):
                        selected_suggestions.append(sug)
        
        if selected_suggestions:
            st.caption(f"已選擇 {len(selected_suggestions)} 個建議關鍵字")

with st.container(border=True):
    # 1-3: 執行搜尋
    st.subheader("1-3. 執行搜尋")
    
    final_keywords = list(set(input_keywords + selected_suggestions))
    
    if final_keywords:
        st.info(f"🎯 最終搜尋關鍵字 ({len(final_keywords)} 個)：{', '.join(final_keywords)}")
        
        if st.button("🚀 執行批次搜尋與意圖分析", type="primary"):
            if not GEMINI_API_KEY or not YOUTUBE_API_KEY:
                st.error("請先在左側設定 API Key")
            else:
                with st.spinner(f"正在搜尋 {len(final_keywords)} 個關鍵字..."):
                    results = search_multiple_keywords(
                        YOUTUBE_API_KEY, 
                        final_keywords, 
                        MAX_RESULTS_PER_KEYWORD
                    )
                    st.session_state.search_results = results
                    st.session_state.final_keywords = final_keywords
                    st.session_state.video_analyses = []
                    st.session_state.final_strategy = ""
                    
                    if results:
                        analysis = analyze_search_intent(
                            GEMINI_API_KEY, 
                            final_keywords, 
                            results, 
                            MODEL_VERSION
                        )
                        st.session_state.intent_analysis = analysis
                        st.rerun()
                    else:
                        st.warning("找不到相關影片")
    else:
        st.warning("請先輸入至少一個關鍵字")

# 顯示意圖分析結果
if st.session_state.intent_analysis:
    with st.container(border=True):
        st.subheader("📊 市場意圖分析報告")
        st.markdown(st.session_state.intent_analysis)
        
        # 下載按鈕
        st.download_button(
            "📥 下載意圖分析報告",
            st.session_state.intent_analysis,
            f"intent_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown"
        )

# ============================================================
# STEP 2: 選擇競品 & AI 爬取
# ============================================================
if st.session_state.search_results:
    st.markdown("---")
    st.header("STEP 2｜選擇競品 & AI 爬取影片內容")
    
    with st.container(border=True):
        st.subheader("2-1. 選擇要分析的競品影片")
        st.caption(f"共搜尋到 {len(st.session_state.search_results)} 支不重複影片")
        
        # 依關鍵字分組
        videos_by_keyword = {}
        for video in st.session_state.search_results:
            kw = video.get('source_keyword', '其他')
            if kw not in videos_by_keyword:
                videos_by_keyword[kw] = []
            videos_by_keyword[kw].append(video)
        
        selected_videos = []
        
        for keyword, videos in videos_by_keyword.items():
            with st.expander(f"🔑 {keyword} ({len(videos)} 支)", expanded=True):
                cols = st.columns(3)
                for idx, video in enumerate(videos):
                    with cols[idx % 3]:
                        st.image(video['thumbnail'], use_container_width=True)
                        title_display = video['title'][:35] + "..." if len(video['title']) > 35 else video['title']
                        st.markdown(f"**{title_display}**")
                        st.caption(f"👀 {video['view_count']:,} | [觀看]({video['url']})")
                        if st.checkbox("納入分析", key=f"vid_{video['id']}"):
                            selected_videos.append(video)
        
        st.markdown(f"### ✅ 已選擇 {len(selected_videos)} 個競品")
    
    with st.container(border=True):
        st.subheader("2-2. AI 爬取影片內容")
        
        if selected_videos:
            if st.button("🤖 開始 AI 爬取", type="primary"):
                if not GEMINI_API_KEY:
                    st.error("請先設定 Gemini API Key")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    status_text.info(f"正在爬取 {len(selected_videos)} 支影片...")
                    
                    analyses = batch_extract_videos(
                        GEMINI_API_KEY, 
                        selected_videos, 
                        MODEL_VERSION,
                        max_workers=MAX_CONCURRENT_AI
                    )
                    
                    progress_bar.progress(100)
                    st.session_state.video_analyses = analyses
                    
                    success_count = sum(1 for a in analyses if a['success'])
                    status_text.success(f"✅ 完成！成功 {success_count}/{len(analyses)} 支")
                    st.rerun()
        else:
            st.warning("請先勾選至少一個影片")
    
    # 顯示爬取結果
    if st.session_state.video_analyses:
        with st.container(border=True):
            st.subheader("📋 影片分析結果")
            
            success_count = sum(1 for a in st.session_state.video_analyses if a['success'])
            st.caption(f"成功 {success_count}/{len(st.session_state.video_analyses)} 支")
            
            for analysis in st.session_state.video_analyses:
                status_icon = "✅" if analysis['success'] else "❌"
                with st.expander(f"{status_icon} [{analysis.get('source_keyword', '')}] {analysis['title'][:40]}"):
                    st.markdown(f"**網址**: {analysis['url']}")
                    st.markdown(f"**觀看數**: {analysis['view_count']:,}")
                    st.markdown("---")
                    st.markdown(analysis['ai_analysis'])
                    
                    # 單支影片下載
                    single_content = f"# {analysis['title']}\n\n"
                    single_content += f"- 網址: {analysis['url']}\n"
                    single_content += f"- 觀看數: {analysis['view_count']:,}\n"
                    single_content += f"- 來源關鍵字: {analysis.get('source_keyword', 'N/A')}\n\n"
                    single_content += f"## 分析內容\n\n{analysis['ai_analysis']}"
                    
                    st.download_button(
                        "📥 下載此影片分析",
                        single_content,
                        f"video_analysis_{analysis['video_id']}.md",
                        mime="text/markdown",
                        key=f"dl_{analysis['video_id']}"
                    )
            
            # 全部下載
            st.markdown("---")
            all_analyses_md = generate_all_analyses_md(st.session_state.video_analyses)
            st.download_button(
                "📥 下載全部影片分析（合併）",
                all_analyses_md,
                f"all_video_analyses_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
                type="primary"
            )

# ============================================================
# STEP 3: 生成策略報告
# ============================================================
if st.session_state.video_analyses:
    st.markdown("---")
    st.header("STEP 3｜生成綜合策略報告")
    
    with st.container(border=True):
        st.subheader("3-1. 設定創作目標")
        user_goal = st.text_area(
            "描述您的創作目標",
            value=st.session_state.user_goal,
            height=80,
            key="goal_input"
        )
        st.session_state.user_goal = user_goal
    
    with st.container(border=True):
        st.subheader("3-2. 生成策略")
        
        if st.button("🚀 生成綜合策略報告", type="primary"):
            with st.spinner("正在整合所有分析，生成策略報告..."):
                strategy = generate_content_strategy(
                    GEMINI_API_KEY,
                    st.session_state.video_analyses,
                    st.session_state.final_keywords,
                    user_goal,
                    MODEL_VERSION
                )
                st.session_state.final_strategy = strategy
                st.rerun()
    
    # 顯示策略報告
    if st.session_state.final_strategy:
        with st.container(border=True):
            st.subheader("🎯 綜合策略報告")
            st.markdown(st.session_state.final_strategy)
            
            # 下載策略報告
            st.download_button(
                "📥 下載策略報告",
                st.session_state.final_strategy,
                f"youtube_strategy_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
                type="primary"
            )

# ============================================================
# 全部下載區
# ============================================================
if st.session_state.final_strategy:
    st.markdown("---")
    st.header("📦 一鍵下載全部")
    
    with st.container(border=True):
        # 組合所有內容
        full_report = f"# YouTube 戰略內容分析完整報告\n\n"
        full_report += f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        full_report += f"研究關鍵字：{', '.join(st.session_state.final_keywords)}\n\n"
        full_report += "---\n\n"
        
        full_report += "# PART 1: 市場意圖分析\n\n"
        full_report += st.session_state.intent_analysis + "\n\n"
        full_report += "---\n\n"
        
        full_report += "# PART 2: 競品影片分析\n\n"
        full_report += generate_all_analyses_md(st.session_state.video_analyses)
        full_report += "\n---\n\n"
        
        full_report += "# PART 3: 綜合策略報告\n\n"
        full_report += st.session_state.final_strategy
        
        st.download_button(
            "📥 下載完整報告（含所有分析）",
            full_report,
            f"youtube_full_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            type="primary"
        )
        
        st.caption("包含：市場意圖分析 + 所有影片分析 + 策略報告")
