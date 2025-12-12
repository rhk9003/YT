import streamlit as st
import google.generativeai as genai

# 設定頁面配置
st.set_page_config(page_title="YouTube 內容策略分析 (AI 全託管版)", page_icon="🤖", layout="wide")

# --- 側邊欄：設定 ---
st.sidebar.title("🔧 系統設定")
api_key = st.sidebar.text_input("輸入 Google Gemini API Key", type="password")

# 根據您的清單，預設使用 gemini-2.0-flash，這通常支援搜尋且速度快
model_name = st.sidebar.text_input(
    "模型名稱", 
    value="gemini-2.0-flash", 
    help="可用模型範例: gemini-2.0-flash, gemini-2.5-pro, gemini-3-pro"
)

# 初始化 Gemini
if api_key:
    genai.configure(api_key=api_key)

def ask_gemini(prompt, model_ver):
    """將任務完全交給 Gemini 處理"""
    try:
        # 設定工具：啟用 Google Search
        # 注意：這需要 google-generativeai>=0.8.3
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
        if "Unknown field for FunctionDeclaration" in error_msg:
            return "系統錯誤：套件版本過舊。請點選右下角 'Manage app' -> 'Reboot app' 來更新環境。"
        return f"AI 思考時發生錯誤 (可能是 API Key 問題或模型不支援搜尋): {error_msg}"

# --- 主介面 ---
st.title("🤖 YouTube 內容策略分析 (AI 全託管版)")
st.caption("本版本捨棄傳統爬蟲程式，改由 Gemini 直接聯網搜尋與分析。")
st.markdown("---")

# 狀態管理
if 'step1_result' not in st.session_state:
    st.session_state.step1_result = ""

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
            2. **列出清單**：請列出目前搜尋排名最前 5 名的影片標題，並盡可能附上連結（如果搜尋得到）。
            3. **意圖分析**：根據你搜尋到的這些結果，分析搜尋這個關鍵字的人，背後真正的心理需求和動機是什麼？
            4. **內容缺口**：推論有沒有什麼是搜尋者想看到，但目前的熱門內容似乎沒有直接回答到的面向？

            請以 Markdown 格式清楚輸出。
            """
            
            response = ask_gemini(prompt_step1, model_name)
            st.session_state.step1_result = response
            
if st.session_state.step1_result:
    st.markdown("### 🧠 AI 搜尋與分析報告")
    st.write(st.session_state.step1_result)

st.markdown("---")

# === 第二階段：競品深度解構 ===
st.header("第二階段：競品內容深度解構")
st.markdown("由於我們不使用程式爬取字幕，請貼上您想分析的影片網址，**AI 將透過網路搜尋該影片的摘要、介紹與評論來進行分析**。")

video_urls_input = st.text_area("貼上影片網址 (可多個)", height=100, help="AI 會嘗試去讀取這些連結的相關資訊")

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
