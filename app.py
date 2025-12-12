import streamlit as st
import google.generativeai as genai
import requests
import json
import re  # 新增 regex 用於提取網址

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

# 修改點 1: 更新模型下拉選單，加入使用者指定之最新模型清單
# 依據您提供的清單包含 3-pro, 2.5-pro, 2.0-flash 等
model_options = [
    "gemini-3-pro",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
    "gemini-1.5-flash"
]

model_name = st.sidebar.selectbox(
    "選擇模型", 
    options=model_options,
    index=0,
    help="請選擇要使用的 Gemini 模型版本"
)

# 初始化 Gemini
if api_key:
    genai.configure(api_key=api_key)

def ask_gemini_rest_api(prompt, model_ver, api_key):
    """備用方案：直接使用 REST API 呼叫，繞過 SDK 版本問題"""
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
            # 解析回應文字
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
    
    # 優先嘗試 SDK 方法
    try:
        # 設定工具：啟用 Google Search
        tools = [
            {"google_search": {}}
        ]
        
        # 初始化模型
        model = genai.GenerativeModel(model_ver, tools=tools)
        
        # 生成內容
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        error_msg = str(e)
        # 如果是特定的 SDK 版本錯誤，自動切換到 REST API
        if "Unknown field for FunctionDeclaration" in error_msg or "google_search" in error_msg:
            # st.warning("檢測到 SDK 版本舊問題，正在切換至 REST API 模式...") # 可選：顯示切換訊息
            if api_key:
                return ask_gemini_rest_api(prompt, model_ver, api_key)
            else:
                return "API Key 未設定，無法使用備用方案。"
        
        return f"AI 發生錯誤: {error_msg}"

# --- 主介面 ---
st.title("🤖 YouTube 內容策略分析 (AI 全託管版)")
st.caption("目前模式：AI 聯網搜尋 (SDK/REST 混合雙引擎)")
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
        with st.spinner(f"Gemini ({model_name}) 正在網路上搜尋 '{keywords}' 的相關影片並進行分析..."):
            
            prompt_step1 = f"""
            請利用你的 Google Search 搜尋能力，執行以下任務：

            1. **搜尋動作**：請搜尋 YouTube 上關於「{keywords}」的熱門影片。
            2. **列出清單**：請列出目前搜尋排名最前 5 名的影片標題，並**務必附上 YouTube 影片網址連結**。
            3. **意圖分析**：根據你搜尋到的這些結果，分析搜尋這個關鍵字的人，背後真正的心理需求和動機是什麼？
            4. **內容缺口**：推論有沒有什麼是搜尋者想看到，但目前的熱門內容似乎沒有直接回答到的面向？

            請以 Markdown 格式清楚輸出。
            """
            
            response = ask_gemini(prompt_step1, model_name)
            st.session_state.step1_result = response

            # 修改點 2: 自動提取網址邏輯
            # 使用 Regex 尋找回應中的 YouTube 連結
            found_urls = re.findall(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s\)\>\"\]]+)', response)
            # 去除重複並轉為字串
            unique_urls = list(set(found_urls))
            if unique_urls:
                st.session_state.auto_filled_urls = "\n".join(unique_urls)
                st.toast(f"已自動擷取 {len(unique_urls)} 個影片網址到第二階段！", icon="✅")
            
if st.session_state.step1_result:
    st.markdown("### 🧠 AI 搜尋與分析報告")
    st.write(st.session_state.step1_result)

st.markdown("---")

# === 第二階段：競品深度解構 ===
st.header("第二階段：競品內容深度解構")
st.markdown("請貼上您想分析的影片網址，AI 將透過網路搜尋該影片的摘要、介紹與評論來進行分析。")

# 修改點 2 (續): 將 value 綁定到自動擷取的 session_state
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
        with st.spinner(f"Gemini ({model_name}) 正在網路上閱讀這些影片的相關資訊..."):
            
            prompt_step2 = f"""
            我對以下這幾部 YouTube 影片感興趣，請利用 Google Search 搜尋這些影片的內容資訊（包含標題、說明欄、網路上的摘要或評論）：

            {video_urls_input}

            ---
            任務需求：
            請根據你搜尋到的資訊，幫我進行「逆向工程」分析：
            
            1. **主要切入點 (Angle)**：分析這些影片是從什麼角度切入主題的？
            2. **敘述架構 (Structure)**：推測它們的內容邏輯與鋪陳方式。
            3. **手法分析 (Techniques)**：它們使用了哪些吸引觀眾的技巧？
            4. **延伸策略建議 (Strategy)**：如果我要製作一支延伸且超越它們的影片，我該準備哪些差異化的主題？

            請注意：你不需要觀看影片檔案，請根據網路上能搜尋到的文字資訊進行最優化的推論。
            """
            
            final_analysis = ask_gemini(prompt_step2, model_name)
            
            st.success("分析完成！")
            st.markdown("### 📝 AI 影片架構解構報告")
            st.write(final_analysis)
