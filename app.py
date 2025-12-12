import streamlit as st
import google.generativeai as genai
# 修改點：換回輕量級的 youtube_search，解決 proxies 報錯問題
from youtube_search import YoutubeSearch
import time

# 設定頁面配置
st.set_page_config(page_title="YouTube 內容策略分析 (精準排名版)", page_icon="▶️", layout="wide")

# --- 側邊欄：設定 ---
st.sidebar.title("🔧 系統設定")
api_key = st.sidebar.text_input("輸入 Google Gemini API Key", type="password")

# 更新模型下拉選單
model_options = [
    "gemini-2.0-flash",
    "gemini-2.5-pro",
    "gemini-3-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash"
]

model_name = st.sidebar.selectbox(
    "選擇模型", 
    options=model_options,
    index=0
)

# 初始化 Gemini
if api_key:
    genai.configure(api_key=api_key)

# --- 核心功能函式 ---

def get_real_youtube_ranking(keyword, limit=5):
    """
    使用 youtube-search 獲取真實的 YouTube 站內搜尋排名。
    這比 Google Search site:youtube.com 更準確反映 YouTube 演算法偏好。
    """
    try:
        # 使用 YoutubeSearch 輕量套件
        results = YoutubeSearch(keyword, max_results=limit).to_dict()
        
        parsed_results = []
        for v in results:
            # 組合完整網址 (套件回傳的是 url_suffix)
            link = f"https://www.youtube.com{v['url_suffix']}"
            
            parsed_results.append({
                "title": v['title'],
                "link": link,
                "id": v['id'],
                "duration": v.get('duration', 'N/A'),
                "views": v.get('views', 'N/A'),
                "channel": v.get('channel', 'Unknown')
            })
        return parsed_results
    except Exception as e:
        st.error(f"YouTube 搜尋連線失敗: {str(e)}")
        return []

def ask_gemini(prompt, model_ver):
    """呼叫 Gemini 進行分析 (啟用 Google Search 以備不時之需)"""
    try:
        tools = [{"google_search": {}}]
        model = genai.GenerativeModel(model_ver, tools=tools)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 分析發生錯誤: {str(e)}"

# --- 主介面 ---
st.title("▶️ YouTube 內容策略分析 (精準排名版)")
st.caption("目前模式：Python 原生搜尋 (確保 YouTube 真實排名) + AI 深度分析")
st.markdown("---")

# 狀態管理
if 'search_data' not in st.session_state:
    st.session_state.search_data = []
if 'analysis_step1' not in st.session_state:
    st.session_state.analysis_step1 = ""

# === 第一階段：精準搜尋與意圖分析 ===
st.header("第一階段：YouTube 站內排名偵察")

keywords = st.text_input("輸入目標關鍵字 (例如：『生產力工具』、『AI 繪圖教學』)")

if st.button("🚀 搜尋並分析", key="search_btn"):
    if not api_key:
        st.error("請先在側邊欄輸入 API Key")
    elif not keywords:
        st.warning("請輸入關鍵字")
    else:
        # 1. 使用 Python 抓取真實排名
        with st.spinner(f"正在連線 YouTube 伺服器獲取 '{keywords}' 的真實排名..."):
            raw_results = get_real_youtube_ranking(keywords)
            
            if raw_results:
                st.session_state.search_data = raw_results
                
                # 顯示排名結果 (除錯與確認用)
                st.subheader("📊 真實搜尋排名 TOP 5")
                result_text_block = ""
                for idx, item in enumerate(raw_results):
                    display_text = f"{idx+1}. [{item['title']}]({item['link']}) - {item['channel']} ({item['views']})"
                    st.markdown(display_text)
                    result_text_block += f"{idx+1}. 標題：{item['title']}\n   頻道：{item['channel']}\n   觀看數：{item['views']}\n   網址：{item['link']}\n\n"
                
                # 2. 將真實數據餵給 Gemini 進行分析
                with st.spinner("Gemini 正在分析這些熱門影片背後的搜尋意圖..."):
                    prompt_step1 = f"""
                    我正在針對關鍵字「{keywords}」進行 YouTube 市場調查。
                    以下是根據 YouTube 演算法抓取到的「真實排名」前 5 名影片資料：

                    {result_text_block}

                    請根據這些「已經被市場驗證成功」的影片標題與主題，幫我進行深入推論：
                    1. **搜尋意圖分析**：搜尋這個字的人，背後真正的心理需求和動機是什麼？(是想解決問題？尋找娛樂？還是學習技能？)
                    2. **現有內容特徵**：這前五名影片有什麼共同點？(例如：都是短影片？都是長教學？都用誇張封面？)
                    3. **內容缺口 (Content Gap)**：根據現有熱門內容，推論有沒有什麼是搜尋者可能想看到，但目前這前五名似乎沒有直接回答或涵蓋到的面向？

                    請以 Markdown 格式清楚輸出。
                    """
                    
                    analysis = ask_gemini(prompt_step1, model_name)
                    st.session_state.analysis_step1 = analysis
            else:
                st.warning("無法獲取搜尋結果，請稍後再試。")

if st.session_state.analysis_step1:
    st.markdown("### 🧠 Gemini 意圖與缺口分析報告")
    st.write(st.session_state.analysis_step1)

st.markdown("---")

# === 第二階段：競品深度解構 ===
st.header("第二階段：競品內容深度解構")

# 自動填入第一階段抓到的網址
default_urls = ""
if st.session_state.search_data:
    default_urls = "\n".join([item['link'] for item in st.session_state.search_data])

st.markdown("系統已自動帶入第一階段的熱門影片網址，您也可以手動修改或加入其他影片。")
video_urls_input = st.text_area(
    "目標影片網址", 
    value=default_urls,
    height=150, 
    help="AI 將會針對這些影片 ID 進行深度分析"
)

if st.button("🧬 進行 DNA 解構分析", key="analyze_btn"):
    if not api_key:
        st.error("請先輸入 API Key")
    elif not video_urls_input:
        st.warning("請貼上影片網址")
    else:
        with st.spinner(f"Gemini ({model_name}) 正在網路上精確鎖定並解構這些影片..."):
            
            prompt_step2 = f"""
            任務目標：對以下 YouTube 影片進行「逆向工程」內容分析。
            
            目標影片網址清單：
            {video_urls_input}

            ---
            **執行指令**：
            請利用你的 Google Search 能力，針對清單中的每一個影片進行研究（搜尋其標題、摘要、評論、字幕討論等資訊），然後綜合回答以下問題：
            
            1. **主要切入點 (Angle)**：這些熱門影片大多是從什麼角度切入主題的？(例如：恐懼行銷、手把手教學、趨勢分析、個人經驗談？)
            2. **敘述架構 (Structure)**：歸納它們的腳本邏輯。它們是如何開場？中間如何鋪陳？最後如何結尾？
            3. **手法分析 (Techniques)**：它們使用了哪些吸引觀眾的技巧？(例如：反直覺的觀點、大量數據佐證、情感共鳴？)
            4. **延伸策略建議 (Strategy)**：如果我要以這些影片為競爭目標，製作一支「延伸」且「超越」它們內容的影片，我該準備哪些差異化的主題或內容？請給我 3 個具體的影片企劃方向。

            **注意**：請確保你的分析是基於這些具體影片的真實資訊，而非泛泛而談。
            """
            
            final_analysis = ask_gemini(prompt_step2, model_name)
            
            st.success("分析完成！")
            st.markdown("### 📝 AI 影片架構解構報告")
            st.write(final_analysis)
