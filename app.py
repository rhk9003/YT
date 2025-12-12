import streamlit as st
import google.generativeai as genai
import requests
import json
import re
from urllib.parse import urlparse, parse_qs

# 設定頁面配置
st.set_page_config(page_title="YouTube 內容策略分析 (AI 全託管版)", page_icon="🤖", layout="wide")

# --- 側邊欄：設定 ---
st.sidebar.title("🔧 系統設定")
api_key = st.sidebar.text_input("輸入 Google Gemini API Key", type="password")

# 顯示 SDK 版本以供除錯
try:
    sdk_version = genai.__version__
except:
    sdk_version = "未知"
st.sidebar.caption(f"目前 SDK 版本: {sdk_version}")

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
    index=0,
    help="建議使用 gemini-2.0-flash 或 pro 系列，搜尋能力較強"
)

# 初始化 Gemini
if api_key:
    genai.configure(api_key=api_key)

def extract_video_id(url):
    """從各種 YouTube URL 格式中提取 video_id"""
    # 處理常見格式:
    # https://www.youtube.com/watch?v=VIDEO_ID
    # https://youtu.be/VIDEO_ID
    # https://www.youtube.com/shorts/VIDEO_ID
    
    # 簡單的正則表達式提取 (比 urllib 更能處理怪異輸入)
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def ask_gemini_rest_api(prompt, model_ver, api_key):
    """備用方案：直接使用 REST API 呼叫"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_ver}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "tools": [{
                "google_search": {}
            }]
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            try:
                return result['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                return "API 回傳了意料之外的格式，請檢查 Logs。"
        else:
            return f"REST API 錯誤 (Status {response.status_code}): {response.text}"
            
    except Exception as e:
        return f"REST API 連線失敗: {str(e)}"

def ask_gemini(prompt, model_ver):
    """將任務完全交給 Gemini 處理 (啟用 Google Search)"""
    try:
        tools = [{"google_search": {}}]
        model = genai.GenerativeModel(model_ver, tools=tools)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "Unknown field" in error_msg or "google_search" in error_msg:
            if api_key:
                return ask_gemini_rest_api(prompt, model_ver, api_key)
            else:
                return "API Key 未設定，無法使用備用方案。"
        return f"AI 發生錯誤: {error_msg}"

# --- 主介面 ---
st.title("🤖 YouTube 內容策略分析 (AI 全託管版)")
st.caption("目前模式：AI 聯網搜尋 (ID 精準鎖定版)")
st.markdown("---")

# 狀態管理
if 'step1_result' not in st.session_state:
    st.session_state.step1_result = ""
if 'auto_filled_urls' not in st.session_state:
    st.session_state.auto_filled_urls = ""

# === 第一階段：關鍵字搜索與市場意圖分析 ===
st.header("第一階段：關鍵字搜尋與意圖偵察")

keywords = st.text_input("輸入目標關鍵字 (例如：『生產力工具』、『AI 繪圖教學』)")

if st.button("🚀 呼叫 AI 進行搜尋與分析", key="search_btn"):
    if not api_key:
        st.error("請先在側邊欄輸入 API Key")
    elif not keywords:
        st.warning("請輸入關鍵字")
    else:
        with st.spinner(f"Gemini ({model_name}) 正在網路上搜尋 '{keywords}'..."):
            
            prompt_step1 = f"""
            請利用你的 Google Search 搜尋能力，執行以下任務：

            1. **搜尋動作**：請搜尋 YouTube 上關於「{keywords}」的熱門影片。
            2. **列出清單**：請列出目前搜尋排名最前 5 名的影片標題，並**務必附上真實有效的 YouTube 影片網址連結**。
               * **重要**：請確保連結是可點擊的真實網址（例如 https://www.youtube.com/watch?v=...）。
               * **禁止**：絕對不要生成 "unavailable" 連結。如果找不到，請不要列出。
            3. **意圖分析**：分析搜尋這個關鍵字的人，背後真正的心理需求和動機。
            4. **內容缺口**：推論目前的熱門內容沒有回答到的面向。

            請以 Markdown 格式清楚輸出。
            """
            
            response = ask_gemini(prompt_step1, model_name)
            st.session_state.step1_result = response

            # 自動提取網址
            found_urls = re.findall(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s\)\>\"\]]+)', response)
            valid_urls = [u for u in found_urls if 'unavailable' not in u]
            unique_urls = list(set(valid_urls))
            
            if unique_urls:
                st.session_state.auto_filled_urls = "\n".join(unique_urls)
                st.toast(f"已自動擷取 {len(unique_urls)} 個有效影片網址！", icon="✅")
            
if st.session_state.step1_result:
    st.markdown("### 🧠 AI 搜尋與分析報告")
    st.write(st.session_state.step1_result)

st.markdown("---")

# === 第二階段：競品深度解構 ===
st.header("第二階段：競品內容深度解構")
st.markdown("請貼上您想分析的影片網址，系統將提取 **Video ID** 進行精準搜尋。")

video_urls_input = st.text_area(
    "貼上影片網址 (可多個)", 
    value=st.session_state.auto_filled_urls,
    height=100, 
    help="AI 會嘗試去讀取這些連結的相關資訊"
)

if st.button("🧬 呼叫 AI 進行架構解構", key="analyze_btn"):
    if not api_key:
        st.error("請先輸入 API Key")
    elif not video_urls_input:
        st.warning("請貼上影片網址")
    else:
        # 1. 先在 Python 端提取 ID，不要讓 AI 去猜
        input_urls = video_urls_input.strip().split('\n')
        target_info = []
        for url in input_urls:
            vid = extract_video_id(url)
            if vid:
                target_info.append(f"- URL: {url} (Video ID: {vid})")
        
        target_info_str = "\n".join(target_info)

        with st.spinner(f"Gemini ({model_name}) 正在網路上精確鎖定這些影片 ID..."):
            
            # 修改點：強制 AI 搜尋 Video ID，這是防止幻覺的關鍵
            prompt_step2 = f"""
            任務目標：對以下 YouTube 影片進行「逆向工程」內容分析。
            
            目標影片清單 (包含 ID)：
            {target_info_str}

            ---
            **執行步驟 (務必嚴格遵守)**：
            
            1. **第一步：強制身分驗證 (ID Search)**
               * 請針對每一個影片 ID (例如 49HLhRPL5f0) 使用 Google Search 進行搜尋。
               * 搜尋關鍵字範例：`site:youtube.com "{vid}"` 或直接搜尋 ID。
               * **必須**準確找出該 ID 對應的「影片標題」與「頻道名稱」。(提示：ID 49HLhRPL5f0 通常對應 AI 或學習相關影片，絕非 Pan Piano)。
               * 如果搜尋 ID 後發現無法對應到特定影片，請標註「無法識別」。
            
            2. **第二步：內容分析**
               * 根據你搜尋到的標題、說明欄摘要、網路討論，進行分析：
               * **主要切入點 (Angle)**
               * **敘述架構 (Structure)**
               * **手法分析 (Techniques)**
               * **延伸策略建議 (Strategy)**
            
            請以 Markdown 格式輸出報告。
            """
            
            final_analysis = ask_gemini(prompt_step2, model_name)
            
            st.success("分析完成！")
            st.markdown("### 📝 AI 影片架構解構報告")
            st.write(final_analysis)
