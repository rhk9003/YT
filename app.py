import requests  # 記得加在最上面

def get_youtube_suggestions(keyword):
    """
    抓取 YouTube 搜尋下拉選單的自動完成關鍵字 (不消耗 API Quota)
    """
    try:
        url = "http://suggestqueries.google.com/complete/search"
        params = {
            "client": "firefox",  # 使用 firefox client 會回傳乾淨的 JSON
            "ds": "yt",           # ds=yt 代表資料來源是 YouTube (沒寫就是 Google Search)
            "q": keyword,
            "hl": "zh-TW"         # 指定語言
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        # data[1] 包含建議關鍵字列表
        if data and len(data) > 1:
            return data[1]
        return []
    except Exception as e:
        return []
