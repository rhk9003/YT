import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import google.generativeai as genai
import time
import json
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# =================================================
# 1. Page Config & Session State
# =================================================
st.set_page_config(
    page_title="YouTube 戰略雷達 v4.1 (Debug版)",
    page_icon="🎬",
    layout="wide"
)

# 初始化 Session State 以保存搜尋結果供第二階段使用
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'landscape_analysis' not in st.session_state:
    st.session_state.landscape_analysis = None

st.title("🎬 YouTube 戰略雷達 v4.1 (Debug Mode)")
st.markdown("""
### Private Content Weapon: YT Narrative Strategy
**Phase 1: 搜尋意圖偵察 (Landscape) → Phase 2: 競品深度解構 (Deep Dive)**
""")

# =================================================
# 2. Sidebar & API Setup
# =================================================
with st.sidebar:
    st.header("🔑 API 設定")
    YOUTUBE_API_KEY = st.text_input("YouTube Data API Key", type="password", help="需啟用 YouTube Data API v3")
    GEMINI_API_KEY = st.text_input("Gemini API Key", type="password")

    st.divider()
    st.header("🧠 模型設定")
    MODEL_NAME = st.selectbox(
        "分析模型",
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro-preview"],
        index=0,
        help="建議：Flash 用於第一階段快速掃描，Pro 用於第二階段深度腳本分析"
    )

    st.divider()
    st.header("🔍 搜尋參數")
    MAX_RESULTS = st.slider("抓取影片數", 5, 20, 10)
    REGION_CODE = st.text_input("地區 (Region)", value="TW")
    RELEVANCE_LANG = st.text_input("語言 (Relevance)", value="zh-Hant")

# =================================================
# 3. Core Logic Functions
# =================================================

def get_video_transcripts(video_id):
    """嘗試抓取影片字幕，優先抓繁中，其次簡中/英文，若無則回傳空字串"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # 優先順序：手動繁中 -> 手動中文 -> 自動繁中 -> 自動中文 -> 英文
        try:
            transcript = transcript_list.find_transcript(['zh-TW', 'zh-Hant', 'zh', 'en'])
        except:
            # 如果找不到指定語言，就抓原本生成的任何語言
            transcript = transcript_list.find_generated_transcript(['zh-TW', 'zh-Hant', 'zh', 'en'])
        
        formatter = TextFormatter()
        return formatter.format_transcript(transcript.fetch())
    except Exception:
        return "" # 無法抓取字幕（可能未提供或被停用）

def fetch_youtube_data(api_key, keyword, max_results):
    """第一階段：搜尋並獲取基本資料 + 字幕 (含錯誤捕捉)"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # 1. 搜尋影片 ID
        search_response = youtube.search().list(
            q=keyword,
            part='id,snippet',
            maxResults=max_results,
            type='video',
            regionCode=REGION_CODE,
            relevanceLanguage=RELEVANCE_LANG
        ).execute()

        video_ids = [item['id']['videoId'] for item in search_response['items']]
        
        if not video_ids:
            st.warning("⚠️ 找不到任何相關影片，請嘗試更換關鍵字或放寬搜尋條件。")
            return None

        videos_data = []

        # 2. 獲取影片詳細數據 (統計數據)
        stats_response = youtube.videos().list(
            part='statistics,contentDetails,snippet',
            id=','.join(video_ids)
        ).execute()

        # 3. 整合數據並並行抓取字幕
        # 使用 ThreadPool 加速字幕下載
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_vid = {executor.submit(get_video_transcripts, vid): vid for vid in video_ids}
            
            transcripts_map = {}
            for future in as_completed(future_to_vid):
                vid = future_to_vid[future]
                transcripts_map[vid] = future.result()

        for item in stats_response['items']:
            vid = item['id']
            snippet = item['snippet']
            stats = item['statistics']
            
            # 處理過長的描述
            full_desc = snippet.get('description', '')
            
            videos_data.append({
                "VideoID": vid,
                "Title": snippet.get('title'),
                "Channel": snippet.get('channelTitle'),
                "PublishDate": snippet.get('publishedAt')[:10],
                "Views": int(stats.get('viewCount', 0)),
                "Likes": int(stats.get('likeCount', 0)),
                "Comments": int(stats.get('commentCount', 0)),
                "URL": f"https://www.youtube.com/watch?v={vid}",
                "Description": full_desc,
                "HasCC": "✅" if transcripts_map.get(vid) else "❌",
                "Transcript_Full": transcripts_map.get(vid, "")
            })

        return pd.DataFrame(videos_data)

    except Exception as e:
        st.error(f"❌ YouTube API 連線錯誤：{str(e)}")
        st.info("💡 常見原因：\n1. API Key 未啟用 'YouTube Data API v3'\n2. API Key 複製錯誤\n3. 每日配額已滿")
        return None

def analyze_landscape(api_key, model_name, keyword, df):
    """Phase 1 分析：搜尋意圖與戰場概況"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    # 準備簡化版資料給 AI (不含完整字幕，避免 Token 爆炸)
    summary_data = df[["Title", "Channel", "Views", "Description"]].to_string(index=False)

    prompt = f"""
    你是一位 YouTube 內容策略專家。請針對關鍵字「{keyword}」的搜尋結果進行「戰場偵察」。
    
    搜尋結果數據：
    {summary_data}

    請以 JSON 格式回傳分析結果，包含以下欄位：
    {{
        "Search_Intent": "使用者搜尋這個詞，背後真正的心理需求是什麼？（娛樂/學習/解決問題/憤怒宣洩...）",
        "Content_Saturation": "目前的內容是否飽和？主要是哪類形式（Talking head/Vlog/教學錄屏...）？",
        "Audience_Gap": "觀眾可能還想看什麼，但目前的影片沒有滿足的？",
        "Thumbnail_Strategy": "觀察標題，目前的點擊誘餌（Clickbait）主要是利用什麼心理？"
    }}
    請直接回傳 JSON，不要 markdown。
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}

def analyze_deep_dive(api_key, model_name, selected_rows):
    """Phase 2 分析：針對選定影片的深度戰術"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    # 組合 Prompt，包含具體字幕內容
    context_text = ""
    for idx, row in selected_rows.iterrows():
        # 截斷過長的字幕以節省 Token (每部影片取前 3000 字)
        transcript_snippet = row['Transcript_Full'][:3000] + "..." if len(row['Transcript_Full']) > 3000 else row['Transcript_Full']
        context_text += f"""
        ---
        影片標題：{row['Title']}
        觀看次數：{row['Views']}
        頻道：{row['Channel']}
        影片字幕/內容摘要：
        {transcript_snippet}
        ---
        """

    prompt = f"""
    你現在是我的首席內容策劃。我挑選了以上幾部競爭對手/參考影片。
    我要做一支影片來切入這個市場。
    請根據上述影片的具體內容（字幕邏輯），為我生成三種不同維度的「進攻策略」：

    參考資料：
    {context_text}

    請回傳 JSON 格式：
    {{
        "Strategy_1_Relate": {{
            "Concept": "相關切入（蹭熱度/順勢）",
            "Angle": "如何利用這些影片建立的認知基礎，順著講但提供更好吸收的版本？",
            "Hook": "建議的開場白（Hook）"
        }},
        "Strategy_2_Extend": {{
            "Concept": "延伸切入（補完/深挖）",
            "Angle": "這些影片忽略了什麼細節？或是哪個觀點可以再往下挖深一層？",
            "Hook": "建議的開場白（Hook）"
        }},
        "Strategy_3_Transcend": {{
            "Concept": "超越切入（反觀點/降維打擊）",
            "Angle": "如何提出一個完全不同、甚至推翻上述影片邏輯的新觀點？",
            "Hook": "建議的開場白（Hook）"
        }},
        "Common_Weakness": "這幾部影片在敘事或邏輯上共同的弱點是什麼？"
    }}
    請直接回傳 JSON，不要 markdown。
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}

# =================================================
# 4. Main UI Flow
# =================================================

# --- Input Section ---
st.subheader("📡 Phase 1: 戰場掃描 (Landscape Scan)")
col1, col2 = st.columns([3, 1])
with col1:
    keyword_input = st.text_input("輸入目標關鍵字", placeholder="例如：AI 行銷工具, 減脂餐, 投資心法")
with col2:
    search_btn = st.button("🚀 執行偵察", type="primary", use_container_width=True)

# --- Phase 1 Execution ---
if search_btn and keyword_input and YOUTUBE_API_KEY and GEMINI_API_KEY:
    with st.spinner("正在爬取 YouTube 資料、下載字幕並進行初步分析..."):
        # 1. 爬取 (如果失敗會回傳 None)
        df_result = fetch_youtube_data(YOUTUBE_API_KEY, keyword_input, MAX_RESULTS)
        
        if df_result is not None:
            st.session_state.search_results = df_result
            
            # 2. 分析
            analysis = analyze_landscape(GEMINI_API_KEY, MODEL_NAME, keyword_input, df_result)
            st.session_state.landscape_analysis = analysis
        else:
            # 如果爬取失敗，清空之前的結果避免混淆
            st.session_state.search_results = None
            st.session_state.landscape_analysis = None

# --- Phase 1 Display ---
if st.session_state.search_results is not None:
    df = st.session_state.search_results
    analysis = st.session_state.landscape_analysis
    
    # 顯示整體戰略分析
    if analysis and "error" not in analysis:
        st.success("✅ 戰場偵察完成")
        with st.expander("📊 搜尋意圖與戰場報告", expanded=True):
            ac1, ac2 = st.columns(2)
            with ac1:
                st.markdown(f"**🎯 搜尋意圖**\n\n{analysis.get('Search_Intent', 'N/A')}")
                st.markdown(f"**📉 觀眾缺口**\n\n{analysis.get('Audience_Gap', 'N/A')}")
            with ac2:
                st.markdown(f"**🔥 內容飽和度**\n\n{analysis.get('Content_Saturation', 'N/A')}")
                st.markdown(f"**🎣 封面與標題策略**\n\n{analysis.get('Thumbnail_Strategy', 'N/A')}")
    elif analysis:
        st.error(f"AI 分析發生錯誤: {analysis.get('error')}")

    st.divider()
    
    # --- Phase 2 Input: Selection ---
    st.subheader("⚔️ Phase 2: 戰術鎖定 (Tactical Targeting)")
    st.info("請勾選您想「對標」、「模仿」或「超越」的影片（建議選 1-3 部具有代表性或高流量的影片）：")

    # 製作一個供選擇的 DataFrame view (隱藏太長的欄位)
    display_df = df[["HasCC", "Title", "Channel", "Views", "PublishDate", "URL"]].copy()
    display_df.insert(0, "Select", False)
    
    # 使用 Data Editor 讓使用者勾選
    edited_df = st.data_editor(
        display_df,
        column_config={
            "Select": st.column_config.CheckboxColumn("鎖定", help="勾選以進行深度分析", default=False),
            "URL": st.column_config.LinkColumn("連結"),
            "HasCC": st.column_config.TextColumn("字幕", help="是否有抓到字幕內容")
        },
        disabled=["HasCC", "Title", "Channel", "Views", "PublishDate", "URL"],
        hide_index=True,
        use_container_width=True
    )

    # 找出被勾選的原始資料
    selected_indices = [i for i, row in edited_df.iterrows() if row['Select']]
    selected_rows = df.iloc[selected_indices]

    if not selected_rows.empty:
        st.write(f"已鎖定 {len(selected_rows)} 部影片，準備進行深度腳本分析...")
        
        if st.button("⚡ 生成進攻腳本策略"):
            # 檢查是否有字幕資料
            cc_count = selected_rows[selected_rows['Transcript_Full'] != ""].shape[0]
            if cc_count == 0:
                st.warning("⚠️ 警告：您選的影片都沒有抓到字幕/逐字稿，AI 分析將僅基於標題與描述，準確度會下降。")
            
            with st.spinner("Gemini 正在閱讀影片逐字稿並擬定作戰計畫..."):
                strategy = analyze_deep_dive(GEMINI_API_KEY, MODEL_NAME, selected_rows)
            
            if strategy and "error" not in strategy:
                st.markdown("### 📝 作戰計畫書")
                
                tab1, tab2, tab3, tab4 = st.tabs(["🤝 順勢相關", "🔍 延伸補完", "💥 降維超越", "⚠️ 共同弱點"])
                
                with tab1:
                    s1 = strategy.get("Strategy_1_Relate", {})
                    st.markdown(f"#### {s1.get('Concept')}")
                    st.info(f"**切入點**：{s1.get('Angle')}")
                    st.markdown(f"> **🪝 Killer Hook**: {s1.get('Hook')}")
                    
                with tab2:
                    s2 = strategy.get("Strategy_2_Extend", {})
                    st.markdown(f"#### {s2.get('Concept')}")
                    st.success(f"**切入點**：{s2.get('Angle')}")
                    st.markdown(f"> **🪝 Killer Hook**: {s2.get('Hook')}")

                with tab3:
                    s3 = strategy.get("Strategy_3_Transcend", {})
                    st.markdown(f"#### {s3.get('Concept')}")
                    st.warning(f"**切入點**：{s3.get('Angle')}")
                    st.markdown(f"> **🪝 Killer Hook**: {s3.get('Hook')}")

                with tab4:
                    st.markdown(f"#### 🛡️ 對手防禦缺口")
                    st.error(strategy.get("Common_Weakness", "無明顯弱點"))

                # 顯示 JSON 供複製
                with st.expander("查看原始 JSON"):
                    st.json(strategy)

            elif strategy:
                st.error(f"分析失敗: {strategy.get('error')}")

    # --- 讓使用者下載原始資料 ---
    st.divider()
    csv_buffer = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        "📥 下載搜尋結果與字幕 (CSV)",
        data=csv_buffer,
        file_name=f"yt_strategy_{int(time.time())}.csv",
        mime="text/csv"
    )

elif st.session_state.search_results is None and search_btn:
    # 這裡通常是 API 錯誤發生後會走到的地方，因為 df_result 為 None
    pass
