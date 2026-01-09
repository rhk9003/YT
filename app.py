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
    page_title="YouTube 戰略內容切入分析儀 v3",
    page_icon="🎯",
    layout="wide"
)

# 固定爬字幕用的模型（低成本）
TRANSCRIPT_MODEL = "gemini-2.5-flash"

# 策略模組定義
STRATEGY_MODULES = {
    "related": {
        "name": "🔗 相關策略 (Related)",
        "description": "利用現有熱門影片的流量，做關聯內容",
        "prompt": """
## 🔗 相關策略 (Related)
如何利用這些影片的現有熱度？

請提供：
1. **關聯標題建議** (3個，融合多個關鍵字)
2. **關鍵字佈局建議**：主關鍵字、長尾關鍵字、標籤建議
3. **回應影片策略**：如何做「回應影片」或「補充觀點」
4. **SEO 優化建議**：標題、描述、縮圖的優化方向
"""
    },
    "trending": {
        "name": "🔥 蹭流量策略 (Trending)",
        "description": "快速蹭熱門話題的流量",
        "prompt": """
## 🔥 蹭流量策略 (Trending)
如何快速蹭到這些熱門話題的流量？

請提供：
1. **時效性切入**：目前最熱的議題點是什麼？
2. **快速製作建議**：如何在 24-48 小時內產出相關內容
3. **標題公式**：3 個能蹭流量的標題範本
4. **風險評估**：這個話題的熱度週期預估
5. **差異化角度**：如何在眾多蹭流量影片中脫穎而出
"""
    },
    "extended": {
        "name": "📈 延伸策略 (Extended)",
        "description": "深入探討競品沒講清楚的內容",
        "prompt": """
## 📈 延伸策略 (Extended)
這些影片沒講清楚的是什麼？

請提供：
1. **深度延伸點** (列舉 3-5 點)：競品影片提到但沒深入的主題
2. **實作步驟補充**：競品只講概念，你可以補充的實際操作
3. **數據佐證方向**：可以用什麼數據讓內容更有說服力
4. **案例補充**：可以新增哪些案例讓內容更豐富
5. **進階內容**：適合進階觀眾的延伸主題
"""
    },
    "superior": {
        "name": "🚀 超越策略 (Superior)",
        "description": "製作品質更高的影片",
        "prompt": """
## 🚀 超越策略 (Superior)
如何製作一支品質更高的影片？

請提供：
1. **視覺化升級**：如何用更好的視覺呈現（動畫、圖表、實拍）
2. **獨特觀點**：競品都沒提到的獨特切入角度
3. **情緒共鳴設計**：如何設計能引發觀眾共鳴的橋段
4. **權威性建立**：如何展現你比競品更專業
5. **製作規格建議**：片長、節奏、段落結構
6. **腳本大綱**：完整的影片腳本結構建議
"""
    },
    "localization": {
        "name": "🌏 搬運策略 (Localization)",
        "description": "將英文優質內容本地化",
        "prompt": """
## 🌏 搬運策略 (Localization)
如何將英文市場的優質內容本地化？

請提供：
1. **可搬運內容**：哪些英文影片的內容值得本地化？
2. **本地化調整**：需要針對台灣/華語市場做哪些調整？
3. **在地案例替換**：可以用什麼本地案例替換國外案例？
4. **文化適配**：有哪些文化差異需要注意？
5. **合規建議**：如何避免版權問題，做出原創性內容
6. **加值方向**：如何在搬運基礎上增加獨特價值
"""
    },
    "comprehensive": {
        "name": "📊 綜合評比 (Comprehensive)",
        "description": "整合所有競品的優缺點分析",
        "prompt": """
## 📊 綜合評比 (Comprehensive)
整合所有競品影片的優缺點分析

請提供：
1. **競品矩陣**：用表格列出各影片的優缺點比較
2. **內容覆蓋度**：哪些主題被多次提到？哪些被忽略？
3. **觀眾反應分析**：從觀看數推測觀眾偏好
4. **最佳實踐**：綜合各競品的最佳做法
5. **市場缺口總結**：整體市場還缺什麼內容？
6. **優先順序建議**：如果只能做一支影片，應該選什麼主題？
"""
    }
}

# 側邊欄配置
with st.sidebar:
    st.header("🔑 API 金鑰設定")
    GEMINI_API_KEY = st.text_input("Gemini API Key", type="password")
    YOUTUBE_API_KEY = st.text_input("YouTube Data API Key", type="password", help="需至 Google Cloud Console 啟用 YouTube Data API v3")
    
    st.markdown("---")
    st.markdown("**分析模型設定**")
    MODEL_VERSION = st.selectbox(
        "策略分析模型", 
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        help="用於意圖分析與策略生成"
    )
    st.caption(f"💡 字幕爬取固定使用 `{TRANSCRIPT_MODEL}`")
    
    st.markdown("---")
    st.markdown("**搜尋設定**")
    MAX_RESULTS_PER_KEYWORD = st.slider("每個關鍵字抓取影片數", 3, 10, 5)
    MAX_CONCURRENT_AI = st.slider("同時爬取影片數", 1, 5, 3, help="太高可能觸發 API 限制")
    
    st.markdown("---")
    st.markdown("**🌐 英文市場功能**")
    ENABLE_ENGLISH = st.checkbox("啟用英文市場比對", value=False, help="將關鍵字翻譯成英文，搜尋英文影片")
    
    st.markdown("---")
    st.markdown("**流程進度**")
    step1_done = "search_results" in st.session_state and (st.session_state.search_results.get('zh') or st.session_state.search_results.get('en'))
    step2_done = "video_analyses" in st.session_state and (st.session_state.video_analyses.get('zh') or st.session_state.video_analyses.get('en'))
    step3_done = "strategy_results" in st.session_state and st.session_state.strategy_results
    
    st.markdown(f"{'✅' if step1_done else '⬜'} STEP 1: 搜尋與意圖分析")
    st.markdown(f"{'✅' if step2_done else '⬜'} STEP 2: AI 爬取影片內容")
    st.markdown(f"{'✅' if step3_done else '⬜'} STEP 3: 策略模組分析")

# ==========================================
# 2. 核心功能函式庫
# ==========================================

def get_youtube_suggestions(keyword, lang="zh-TW"):
    """抓取 YouTube 搜尋下拉選單的自動完成關鍵字"""
    try:
        url = "http://suggestqueries.google.com/complete/search"
        params = {
            "client": "firefox",
            "ds": "yt",
            "q": keyword,
            "hl": lang
        }
        response = requests.get(url, params=params, timeout=2)
        data = response.json()
        if data and len(data) > 1:
            return data[1]
        return []
    except Exception:
        return []

def translate_keyword_to_english(api_key, keyword, model_version="gemini-2.5-flash"):
    """使用 AI 將關鍵字翻譯成英文"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)
    
    prompt = f"""
    請將以下中文關鍵字翻譯成最適合在 YouTube 搜尋的英文關鍵字。
    
    中文關鍵字：{keyword}
    
    要求：
    1. 翻譯要符合英文 YouTube 的搜尋習慣
    2. 如果有多種翻譯方式，選擇搜尋量最大的版本
    3. 只回覆英文關鍵字，不要其他解釋
    4. 如果關鍵字本身就是英文或專有名詞，保持原樣
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return keyword  # 翻譯失敗就用原本的

def batch_translate_keywords(api_key, keywords_list, model_version="gemini-2.5-flash"):
    """批次翻譯關鍵字"""
    translations = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_kw = {
            executor.submit(translate_keyword_to_english, api_key, kw, model_version): kw 
            for kw in keywords_list
        }
        
        for future in concurrent.futures.as_completed(future_to_kw):
            original_kw = future_to_kw[future]
            try:
                translated = future.result()
                translations[original_kw] = translated
            except Exception:
                translations[original_kw] = original_kw
    
    return translations

def search_youtube_api(api_key, query, max_results=5, region_code="TW", relevance_language=None):
    """使用 YouTube Data API 獲取影片列表與詳細數據"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        search_params = {
            'q': query,
            'part': 'id,snippet',
            'maxResults': max_results,
            'type': 'video',
            'order': 'relevance',
            'regionCode': region_code
        }
        
        if relevance_language:
            search_params['relevanceLanguage'] = relevance_language
        
        search_response = youtube.search().list(**search_params).execute()

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
                'source_keyword': query,
                'language': relevance_language or 'zh'
            })
        
        return results

    except Exception as e:
        st.error(f"YouTube API 錯誤 ({query}): {e}")
        return []

def search_multiple_keywords(api_key, keywords_list, max_results_per_keyword, lang="zh"):
    """批次搜尋多個關鍵字"""
    all_results = []
    seen_ids = set()
    
    region_code = "TW" if lang == "zh" else "US"
    relevance_language = "zh-Hant" if lang == "zh" else "en"
    
    for keyword in keywords_list:
        results = search_youtube_api(
            api_key, keyword, max_results_per_keyword, 
            region_code=region_code, 
            relevance_language=relevance_language
        )
        for video in results:
            if video['id'] not in seen_ids:
                seen_ids.add(video['id'])
                video['market'] = lang  # 標記市場
                all_results.append(video)
    
    return all_results

# ==========================================
# 3. AI 分析函式
# ==========================================

def extract_video_content_via_ai(api_key, video_info):
    """用 AI 直接爬取單支 YouTube 影片的內容摘要"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(TRANSCRIPT_MODEL)
    
    video_url = video_info['url']
    video_title = video_info['title']
    market = video_info.get('market', 'zh')
    
    lang_instruction = "請用繁體中文回答" if market == "zh" else "請用繁體中文回答（影片是英文的，但分析請用中文）"
    
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
    7. **獨特價值**：這支影片相比其他同類影片的獨特之處
    
    {lang_instruction}，格式清晰。
    """
    
    try:
        response = model.generate_content(prompt)
        return {
            'video_id': video_info['id'],
            'title': video_title,
            'url': video_url,
            'view_count': video_info['view_count'],
            'source_keyword': video_info.get('source_keyword', ''),
            'market': market,
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
            'market': market,
            'ai_analysis': f"爬取失敗: {str(e)}",
            'success': False
        }

def batch_extract_videos(api_key, videos_list, max_workers=3):
    """批次爬取多支影片"""
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_video = {
            executor.submit(extract_video_content_via_ai, api_key, video): video 
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
                    'market': video.get('market', 'zh'),
                    'ai_analysis': f"執行錯誤: {str(e)}",
                    'success': False
                })
    
    return results

def analyze_search_intent_bilingual(api_key, zh_keywords, en_keywords, zh_videos, en_videos, model_version):
    """雙語市場意圖分析"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)
    
    # 整理中文市場數據
    zh_summary = ""
    if zh_videos:
        zh_summary = "\n### 🇹🇼 繁體中文市場\n"
        for keyword in zh_keywords:
            keyword_videos = [v for v in zh_videos if v.get('source_keyword') == keyword]
            if keyword_videos:
                zh_summary += f"\n**關鍵字：「{keyword}」**\n"
                for v in keyword_videos[:3]:
                    zh_summary += f"- {v['title']} (觀看數: {v['view_count']:,})\n"
    
    # 整理英文市場數據
    en_summary = ""
    if en_videos:
        en_summary = "\n### 🇺🇸 英文市場\n"
        for keyword in en_keywords:
            keyword_videos = [v for v in en_videos if v.get('source_keyword') == keyword]
            if keyword_videos:
                en_summary += f"\n**關鍵字：「{keyword}」**\n"
                for v in keyword_videos[:3]:
                    en_summary += f"- {v['title']} (觀看數: {v['view_count']:,})\n"

    prompt = f"""
    你是一個跨語言搜尋意圖分析專家。
    
    使用者研究的中文關鍵字：{', '.join(zh_keywords)}
    {'對應的英文關鍵字：' + ', '.join(en_keywords) if en_keywords else ''}
    
    以下是搜尋結果：
    {zh_summary}
    {en_summary}
    
    請分析：
    
    ## 1. 【搜尋意圖分析】
    - 這些關鍵字背後的使用者需求是什麼？
    - 使用者最想解決什麼問題？
    
    ## 2. 【市場現況】
    - 中文市場目前的內容主要集中在哪些角度？
    {'- 英文市場的內容主要集中在哪些角度？' if en_videos else ''}
    
    ## 3. 【中英差距分析】{'（重點！）' if en_videos else '（未啟用英文搜尋）'}
    {'- 英文市場有但中文市場缺乏的內容主題' if en_videos else '- 建議啟用英文市場搜尋以獲得更完整分析'}
    {'- 英文市場的內容深度/專業度差異' if en_videos else ''}
    {'- 最值得「搬運」到中文市場的內容方向' if en_videos else ''}
    
    ## 4. 【內容機會總結】
    - 綜合以上分析，最有潛力的內容方向是？
    
    請用繁體中文回答，格式清晰。
    """
    
    response = model.generate_content(prompt)
    return response.text

def generate_strategy_module(api_key, module_key, all_analyses, keywords_info, user_goal, model_version, has_english=False):
    """生成單一策略模組的報告"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_version)
    
    module = STRATEGY_MODULES[module_key]
    
    # 整理影片分析內容
    zh_analyses = [a for a in all_analyses if a.get('market') == 'zh']
    en_analyses = [a for a in all_analyses if a.get('market') == 'en']
    
    combined_context = ""
    
    if zh_analyses:
        combined_context += "### 🇹🇼 繁體中文市場競品\n\n"
        for idx, analysis in enumerate(zh_analyses, 1):
            combined_context += f"""
**[中文 {idx}] {analysis['title']}**
- 來源關鍵字：{analysis.get('source_keyword', 'N/A')}
- 觀看數：{analysis['view_count']:,}
- 網址：{analysis['url']}

{analysis['ai_analysis']}

---
"""
    
    if en_analyses:
        combined_context += "\n### 🇺🇸 英文市場競品\n\n"
        for idx, analysis in enumerate(en_analyses, 1):
            combined_context += f"""
**[英文 {idx}] {analysis['title']}**
- 來源關鍵字：{analysis.get('source_keyword', 'N/A')}
- 觀看數：{analysis['view_count']:,}
- 網址：{analysis['url']}

{analysis['ai_analysis']}

---
"""

    # 針對搬運策略的特殊處理
    localization_context = ""
    if module_key == "localization":
        if not en_analyses:
            return f"# {module['name']}\n\n⚠️ 未啟用英文市場搜尋，無法生成搬運策略。請在側邊欄啟用「英文市場比對」功能後重新執行。"
        localization_context = """
特別注意：請重點分析英文市場的影片，找出值得本地化到繁體中文市場的內容。
"""

    prompt = f"""
    你是一位頂尖的 YouTube 內容策略顧問。
    
    研究關鍵字：{', '.join(keywords_info.get('zh', []))}
    {'對應英文關鍵字：' + ', '.join(keywords_info.get('en', [])) if keywords_info.get('en') else ''}
    
    以下是競品影片的詳細分析：
    
    {combined_context}
    
    【使用者的創作目標】
    {user_goal}
    
    {localization_context}
    
    請根據以上競品分析，專注於以下策略方向提出建議：
    
    {module['prompt']}
    
    請用繁體中文回答，內容要具體可執行，格式清晰專業。
    """
    
    try:
        response = model.generate_content(prompt)
        return f"# {module['name']}\n\n{response.text}"
    except Exception as e:
        return f"# {module['name']}\n\n❌ 生成失敗: {str(e)}"

def batch_generate_strategies(api_key, selected_modules, all_analyses, keywords_info, user_goal, model_version, has_english=False):
    """並行生成多個策略模組"""
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected_modules)) as executor:
        future_to_module = {
            executor.submit(
                generate_strategy_module, 
                api_key, module_key, all_analyses, keywords_info, user_goal, model_version, has_english
            ): module_key 
            for module_key in selected_modules
        }
        
        for future in concurrent.futures.as_completed(future_to_module):
            module_key = future_to_module[future]
            try:
                result = future.result()
                results[module_key] = result
            except Exception as e:
                results[module_key] = f"# {STRATEGY_MODULES[module_key]['name']}\n\n❌ 執行錯誤: {str(e)}"
    
    return results

# ==========================================
# 4. 輔助函式
# ==========================================

def generate_all_analyses_md(video_analyses):
    """將所有影片分析整合成一份 Markdown"""
    zh_analyses = [a for a in video_analyses if a.get('market') == 'zh']
    en_analyses = [a for a in video_analyses if a.get('market') == 'en']
    
    content = f"# YouTube 競品影片分析報告\n\n"
    content += f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    content += f"共分析 {len(video_analyses)} 支影片（中文 {len(zh_analyses)} 支，英文 {len(en_analyses)} 支）\n\n"
    content += "---\n\n"
    
    if zh_analyses:
        content += "## 🇹🇼 繁體中文市場\n\n"
        for idx, analysis in enumerate(zh_analyses, 1):
            status = "✅ 成功" if analysis['success'] else "❌ 失敗"
            content += f"### {idx}. {analysis['title']}\n\n"
            content += f"- **狀態**: {status}\n"
            content += f"- **來源關鍵字**: {analysis.get('source_keyword', 'N/A')}\n"
            content += f"- **網址**: {analysis['url']}\n"
            content += f"- **觀看數**: {analysis['view_count']:,}\n\n"
            content += f"#### 分析內容\n\n{analysis['ai_analysis']}\n\n"
            content += "---\n\n"
    
    if en_analyses:
        content += "## 🇺🇸 英文市場\n\n"
        for idx, analysis in enumerate(en_analyses, 1):
            status = "✅ 成功" if analysis['success'] else "❌ 失敗"
            content += f"### {idx}. {analysis['title']}\n\n"
            content += f"- **狀態**: {status}\n"
            content += f"- **來源關鍵字**: {analysis.get('source_keyword', 'N/A')}\n"
            content += f"- **網址**: {analysis['url']}\n"
            content += f"- **觀看數**: {analysis['view_count']:,}\n\n"
            content += f"#### 分析內容\n\n{analysis['ai_analysis']}\n\n"
            content += "---\n\n"
    
    return content

# ==========================================
# 5. Streamlit 主程式邏輯
# ==========================================

st.title("🎯 YouTube 戰略內容切入分析儀 v3")
st.caption("支援多關鍵字搜尋 → 中英雙語市場比對 → AI 爬取字幕 → 模組化策略生成")

# Session State 初始化
if "confirmed_keywords" not in st.session_state:
    st.session_state.confirmed_keywords = []
if "english_keywords" not in st.session_state:
    st.session_state.english_keywords = {}  # {zh_keyword: en_keyword}
if "suggestions_cache" not in st.session_state:
    st.session_state.suggestions_cache = {}
if "search_results" not in st.session_state:
    st.session_state.search_results = {'zh': [], 'en': []}
if "intent_analysis" not in st.session_state:
    st.session_state.intent_analysis = ""
if "video_analyses" not in st.session_state:
    st.session_state.video_analyses = {'zh': [], 'en': []}
if "strategy_results" not in st.session_state:
    st.session_state.strategy_results = {}
if "user_goal" not in st.session_state:
    st.session_state.user_goal = "我想做一支能蹭到流量，但在專業度上超越他們的影片"

# ============================================================
# STEP 1: 關鍵字輸入與搜尋
# ============================================================
st.header("STEP 1｜關鍵字搜尋與市場意圖分析")

with st.container(border=True):
    st.subheader("1-1. 輸入與管理關鍵字")
    
    col_input, col_action = st.columns([3, 1])
    
    with col_input:
        new_keywords_input = st.text_area(
            "新增關鍵字（每行一個，或用逗號分隔）",
            placeholder="AI 影片生成\nAI 剪輯工具\nYouTube 自動化",
            height=80,
            key="new_keywords_input"
        )
    
    with col_action:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ 加入關鍵字列表", type="primary"):
            if new_keywords_input:
                new_kws = []
                for line in new_keywords_input.replace('，', ',').split('\n'):
                    for kw in line.split(','):
                        kw = kw.strip()
                        if kw and kw not in st.session_state.confirmed_keywords:
                            new_kws.append(kw)
                
                if new_kws:
                    st.session_state.confirmed_keywords.extend(new_kws)
                    st.success(f"已加入 {len(new_kws)} 個關鍵字")
                    st.rerun()
                else:
                    st.warning("沒有新的關鍵字可加入")
    
    # 顯示目前關鍵字列表
    if st.session_state.confirmed_keywords:
        st.markdown("**📋 目前關鍵字列表：**")
        
        cols = st.columns(6)
        keywords_to_remove = []
        
        for idx, kw in enumerate(st.session_state.confirmed_keywords):
            with cols[idx % 6]:
                col_tag, col_x = st.columns([4, 1])
                with col_tag:
                    en_kw = st.session_state.english_keywords.get(kw, "")
                    if en_kw and ENABLE_ENGLISH:
                        st.markdown(f"`{kw}`\n`🇺🇸 {en_kw}`")
                    else:
                        st.markdown(f"`{kw}`")
                with col_x:
                    if st.button("✕", key=f"del_{idx}", help=f"移除 {kw}"):
                        keywords_to_remove.append(kw)
        
        if keywords_to_remove:
            for kw in keywords_to_remove:
                st.session_state.confirmed_keywords.remove(kw)
                if kw in st.session_state.english_keywords:
                    del st.session_state.english_keywords[kw]
            st.rerun()
        
        col_clear, col_translate = st.columns(2)
        with col_clear:
            if st.button("🗑️ 清空全部關鍵字"):
                st.session_state.confirmed_keywords = []
                st.session_state.english_keywords = {}
                st.session_state.suggestions_cache = {}
                st.rerun()
        
        with col_translate:
            if ENABLE_ENGLISH:
                untranslated = [kw for kw in st.session_state.confirmed_keywords if kw not in st.session_state.english_keywords]
                if untranslated:
                    if st.button(f"🌐 翻譯關鍵字為英文 ({len(untranslated)} 個)"):
                        if GEMINI_API_KEY:
                            with st.spinner("正在翻譯關鍵字..."):
                                translations = batch_translate_keywords(GEMINI_API_KEY, untranslated)
                                st.session_state.english_keywords.update(translations)
                            st.rerun()
                        else:
                            st.error("請先設定 Gemini API Key")
                else:
                    st.success("✅ 所有關鍵字已翻譯")
    else:
        st.info("尚未加入任何關鍵字，請在上方輸入")

with st.container(border=True):
    st.subheader("1-2. 取得 YouTube 建議關鍵字")
    st.caption("勾選建議關鍵字會自動加入列表")
    
    if st.session_state.confirmed_keywords:
        keywords_without_suggestions = [
            kw for kw in st.session_state.confirmed_keywords 
            if kw not in st.session_state.suggestions_cache
        ]
        
        col_btn1, col_btn2, col_info = st.columns([1, 1, 2])
        
        with col_btn1:
            if st.button("🔍 取得新關鍵字的建議", disabled=not keywords_without_suggestions):
                with st.spinner(f"正在取得 {len(keywords_without_suggestions)} 個關鍵字的建議..."):
                    for kw in keywords_without_suggestions:
                        suggestions = get_youtube_suggestions(kw)
                        st.session_state.suggestions_cache[kw] = suggestions
                st.rerun()
        
        with col_btn2:
            if st.button("🔄 重新取得全部建議"):
                with st.spinner("正在重新取得所有建議..."):
                    st.session_state.suggestions_cache = {}
                    for kw in st.session_state.confirmed_keywords:
                        suggestions = get_youtube_suggestions(kw)
                        st.session_state.suggestions_cache[kw] = suggestions
                st.rerun()
        
        with col_info:
            if keywords_without_suggestions:
                st.caption(f"⚡ {len(keywords_without_suggestions)} 個關鍵字尚未取得建議")
            else:
                st.caption("✅ 所有關鍵字都已取得建議")
        
        if st.session_state.suggestions_cache:
            st.markdown("---")
            
            for base_kw, suggestions in st.session_state.suggestions_cache.items():
                if suggestions:
                    available_suggestions = [
                        s for s in suggestions 
                        if s not in st.session_state.confirmed_keywords
                    ]
                    
                    if available_suggestions:
                        st.markdown(f"**{base_kw}** 的延伸建議：")
                        cols = st.columns(4)
                        for i, sug in enumerate(available_suggestions[:8]):
                            with cols[i % 4]:
                                if st.button(f"➕ {sug}", key=f"add_sug_{base_kw}_{i}"):
                                    if sug not in st.session_state.confirmed_keywords:
                                        st.session_state.confirmed_keywords.append(sug)
                                        st.rerun()
                    else:
                        st.caption(f"**{base_kw}**：所有建議都已加入列表")
    else:
        st.warning("請先在上方加入關鍵字")

with st.container(border=True):
    st.subheader("1-3. 執行搜尋")
    
    if st.session_state.confirmed_keywords:
        search_info = f"🎯 將搜尋 {len(st.session_state.confirmed_keywords)} 個中文關鍵字"
        if ENABLE_ENGLISH and st.session_state.english_keywords:
            search_info += f" + {len(st.session_state.english_keywords)} 個英文關鍵字"
        st.info(search_info)
        
        if st.button("🚀 執行批次搜尋與意圖分析", type="primary"):
            if not GEMINI_API_KEY or not YOUTUBE_API_KEY:
                st.error("請先在左側設定 API Key")
            else:
                # 搜尋中文市場
                with st.spinner(f"正在搜尋中文市場..."):
                    zh_results = search_multiple_keywords(
                        YOUTUBE_API_KEY, 
                        st.session_state.confirmed_keywords, 
                        MAX_RESULTS_PER_KEYWORD,
                        lang="zh"
                    )
                
                # 搜尋英文市場（如果啟用）
                en_results = []
                if ENABLE_ENGLISH and st.session_state.english_keywords:
                    with st.spinner(f"正在搜尋英文市場..."):
                        en_keywords = list(st.session_state.english_keywords.values())
                        en_results = search_multiple_keywords(
                            YOUTUBE_API_KEY, 
                            en_keywords, 
                            MAX_RESULTS_PER_KEYWORD,
                            lang="en"
                        )
                
                st.session_state.search_results = {'zh': zh_results, 'en': en_results}
                st.session_state.video_analyses = {'zh': [], 'en': []}
                st.session_state.strategy_results = {}
                
                if zh_results or en_results:
                    with st.spinner("正在分析搜尋意圖..."):
                        en_keywords = list(st.session_state.english_keywords.values()) if ENABLE_ENGLISH else []
                        analysis = analyze_search_intent_bilingual(
                            GEMINI_API_KEY, 
                            st.session_state.confirmed_keywords,
                            en_keywords,
                            zh_results, 
                            en_results,
                            MODEL_VERSION
                        )
                        st.session_state.intent_analysis = analysis
                    st.rerun()
                else:
                    st.warning("找不到相關影片")
    else:
        st.warning("請先加入至少一個關鍵字")

# 顯示意圖分析結果
if st.session_state.intent_analysis:
    with st.container(border=True):
        st.subheader("📊 市場意圖分析報告")
        st.markdown(st.session_state.intent_analysis)
        
        st.download_button(
            "📥 下載意圖分析報告",
            st.session_state.intent_analysis,
            f"intent_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown"
        )

# ============================================================
# STEP 2: 選擇競品 & AI 爬取
# ============================================================
zh_results = st.session_state.search_results.get('zh', [])
en_results = st.session_state.search_results.get('en', [])

if zh_results or en_results:
    st.markdown("---")
    st.header("STEP 2｜選擇競品 & AI 爬取影片內容")
    st.caption(f"💡 字幕爬取使用 `{TRANSCRIPT_MODEL}` 模型")
    
    with st.container(border=True):
        st.subheader("2-1. 選擇要分析的競品影片")
        
        selected_videos = []
        
        # 中文市場影片
        if zh_results:
            st.markdown("### 🇹🇼 繁體中文市場")
            st.caption(f"共 {len(zh_results)} 支影片")
            
            videos_by_keyword = {}
            for video in zh_results:
                kw = video.get('source_keyword', '其他')
                if kw not in videos_by_keyword:
                    videos_by_keyword[kw] = []
                videos_by_keyword[kw].append(video)
            
            for keyword, videos in videos_by_keyword.items():
                with st.expander(f"🔑 {keyword} ({len(videos)} 支)", expanded=True):
                    cols = st.columns(3)
                    for idx, video in enumerate(videos):
                        with cols[idx % 3]:
                            st.image(video['thumbnail'], use_container_width=True)
                            title_display = video['title'][:35] + "..." if len(video['title']) > 35 else video['title']
                            st.markdown(f"**{title_display}**")
                            st.caption(f"👀 {video['view_count']:,} | [觀看]({video['url']})")
                            if st.checkbox("納入", key=f"vid_zh_{video['id']}"):
                                selected_videos.append(video)
        
        # 英文市場影片
        if en_results:
            st.markdown("### 🇺🇸 英文市場")
            st.caption(f"共 {len(en_results)} 支影片")
            
            videos_by_keyword = {}
            for video in en_results:
                kw = video.get('source_keyword', '其他')
                if kw not in videos_by_keyword:
                    videos_by_keyword[kw] = []
                videos_by_keyword[kw].append(video)
            
            for keyword, videos in videos_by_keyword.items():
                with st.expander(f"🔑 {keyword} ({len(videos)} 支)", expanded=True):
                    cols = st.columns(3)
                    for idx, video in enumerate(videos):
                        with cols[idx % 3]:
                            st.image(video['thumbnail'], use_container_width=True)
                            title_display = video['title'][:35] + "..." if len(video['title']) > 35 else video['title']
                            st.markdown(f"**{title_display}**")
                            st.caption(f"👀 {video['view_count']:,} | [觀看]({video['url']})")
                            if st.checkbox("納入", key=f"vid_en_{video['id']}"):
                                selected_videos.append(video)
        
        zh_selected = len([v for v in selected_videos if v.get('market') == 'zh'])
        en_selected = len([v for v in selected_videos if v.get('market') == 'en'])
        st.markdown(f"### ✅ 已選擇 {len(selected_videos)} 個競品（中文 {zh_selected}，英文 {en_selected}）")
    
    with st.container(border=True):
        st.subheader("2-2. AI 爬取影片內容")
        
        if selected_videos:
            if st.button("🤖 開始 AI 爬取", type="primary"):
                if not GEMINI_API_KEY:
                    st.error("請先設定 Gemini API Key")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    status_text.info(f"正在使用 {TRANSCRIPT_MODEL} 爬取 {len(selected_videos)} 支影片...")
                    
                    analyses = batch_extract_videos(
                        GEMINI_API_KEY, 
                        selected_videos,
                        max_workers=MAX_CONCURRENT_AI
                    )
                    
                    progress_bar.progress(100)
                    
                    # 分類結果
                    zh_analyses = [a for a in analyses if a.get('market') == 'zh']
                    en_analyses = [a for a in analyses if a.get('market') == 'en']
                    st.session_state.video_analyses = {'zh': zh_analyses, 'en': en_analyses}
                    
                    success_count = sum(1 for a in analyses if a['success'])
                    status_text.success(f"✅ 完成！成功 {success_count}/{len(analyses)} 支")
                    st.rerun()
        else:
            st.warning("請先勾選至少一個影片")
    
    # 顯示爬取結果
    all_analyses = st.session_state.video_analyses.get('zh', []) + st.session_state.video_analyses.get('en', [])
    if all_analyses:
        with st.container(border=True):
            st.subheader("📋 影片分析結果")
            
            zh_analyses = st.session_state.video_analyses.get('zh', [])
            en_analyses = st.session_state.video_analyses.get('en', [])
            
            success_count = sum(1 for a in all_analyses if a['success'])
            st.caption(f"成功 {success_count}/{len(all_analyses)} 支")
            
            if zh_analyses:
                st.markdown("#### 🇹🇼 中文影片分析")
                for analysis in zh_analyses:
                    status_icon = "✅" if analysis['success'] else "❌"
                    with st.expander(f"{status_icon} [{analysis.get('source_keyword', '')}] {analysis['title'][:40]}"):
                        st.markdown(f"**網址**: {analysis['url']}")
                        st.markdown(f"**觀看數**: {analysis['view_count']:,}")
                        st.markdown("---")
                        st.markdown(analysis['ai_analysis'])
            
            if en_analyses:
                st.markdown("#### 🇺🇸 英文影片分析")
                for analysis in en_analyses:
                    status_icon = "✅" if analysis['success'] else "❌"
                    with st.expander(f"{status_icon} [{analysis.get('source_keyword', '')}] {analysis['title'][:40]}"):
                        st.markdown(f"**網址**: {analysis['url']}")
                        st.markdown(f"**觀看數**: {analysis['view_count']:,}")
                        st.markdown("---")
                        st.markdown(analysis['ai_analysis'])
            
            st.markdown("---")
            all_analyses_md = generate_all_analyses_md(all_analyses)
            st.download_button(
                "📥 下載全部影片分析（合併）",
                all_analyses_md,
                f"all_video_analyses_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
                type="primary"
            )

# ============================================================
# STEP 3: 策略模組生成
# ============================================================
all_analyses = st.session_state.video_analyses.get('zh', []) + st.session_state.video_analyses.get('en', [])
if all_analyses:
    st.markdown("---")
    st.header("STEP 3｜策略模組生成")
    
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
        st.subheader("3-2. 選擇策略模組")
        st.caption("勾選要生成的策略類型，每個模組會由獨立 AI 同時處理")
        
        has_english = len(st.session_state.video_analyses.get('en', [])) > 0
        
        selected_modules = []
        
        cols = st.columns(3)
        for idx, (key, module) in enumerate(STRATEGY_MODULES.items()):
            with cols[idx % 3]:
                # 搬運策略需要英文資料
                disabled = (key == "localization" and not has_english)
                help_text = module['description']
                if key == "localization" and not has_english:
                    help_text += "（需啟用英文市場搜尋）"
                
                if st.checkbox(
                    module['name'], 
                    key=f"module_{key}",
                    disabled=disabled,
                    help=help_text
                ):
                    selected_modules.append(key)
        
        st.markdown(f"**已選擇 {len(selected_modules)} 個策略模組**")
        
        if not has_english:
            st.info("💡 啟用「英文市場比對」功能可解鎖「搬運策略」模組")
    
    with st.container(border=True):
        st.subheader("3-3. 生成策略")
        st.caption(f"使用 `{MODEL_VERSION}` 模型，{len(selected_modules)} 個 AI 將同時運作")
        
        if selected_modules:
            if st.button("🚀 生成策略報告", type="primary"):
                with st.spinner(f"正在同時執行 {len(selected_modules)} 個策略分析..."):
                    keywords_info = {
                        'zh': st.session_state.confirmed_keywords,
                        'en': list(st.session_state.english_keywords.values()) if st.session_state.english_keywords else []
                    }
                    
                    results = batch_generate_strategies(
                        GEMINI_API_KEY,
                        selected_modules,
                        all_analyses,
                        keywords_info,
                        user_goal,
                        MODEL_VERSION,
                        has_english
                    )
                    st.session_state.strategy_results = results
                    st.rerun()
        else:
            st.warning("請先選擇至少一個策略模組")
    
    # 顯示策略結果
    if st.session_state.strategy_results:
        with st.container(border=True):
            st.subheader("🎯 策略報告")
            
            # 建立 tabs 顯示各策略
            tab_names = [STRATEGY_MODULES[key]['name'] for key in st.session_state.strategy_results.keys()]
            tabs = st.tabs(tab_names)
            
            for tab, (key, content) in zip(tabs, st.session_state.strategy_results.items()):
                with tab:
                    st.markdown(content)
                    st.download_button(
                        f"📥 下載 {STRATEGY_MODULES[key]['name']}",
                        content,
                        f"strategy_{key}_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                        mime="text/markdown",
                        key=f"dl_strategy_{key}"
                    )

# ============================================================
# 全部下載區
# ============================================================
if st.session_state.strategy_results:
    st.markdown("---")
    st.header("📦 一鍵下載全部")
    
    with st.container(border=True):
        full_report = f"# YouTube 戰略內容分析完整報告\n\n"
        full_report += f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        full_report += f"研究關鍵字（中文）：{', '.join(st.session_state.confirmed_keywords)}\n"
        if st.session_state.english_keywords:
            full_report += f"研究關鍵字（英文）：{', '.join(st.session_state.english_keywords.values())}\n"
        full_report += "\n---\n\n"
        
        full_report += "# PART 1: 市場意圖分析\n\n"
        full_report += st.session_state.intent_analysis + "\n\n"
        full_report += "---\n\n"
        
        all_analyses = st.session_state.video_analyses.get('zh', []) + st.session_state.video_analyses.get('en', [])
        full_report += "# PART 2: 競品影片分析\n\n"
        full_report += generate_all_analyses_md(all_analyses)
        full_report += "\n---\n\n"
        
        full_report += "# PART 3: 策略報告\n\n"
        for key, content in st.session_state.strategy_results.items():
            full_report += content + "\n\n---\n\n"
        
        st.download_button(
            "📥 下載完整報告（含所有分析）",
            full_report,
            f"youtube_full_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            type="primary"
        )
        
        st.caption("包含：市場意圖分析 + 所有影片分析 + 全部策略報告")
