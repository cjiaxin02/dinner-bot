import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client
from linebot.models import LocationMessage, LocationSendMessage
from linebot.models import FlexSendMessage

app = Flask(__name__)

# 從環境變數讀取金鑰 (Render 設定區)
# 這樣寫可以確保如果讀不到鑰匙，會給它一個空的字串 "" 而不是 None
line_bot_api = LineBotApi(os.environ.get('CHANNEL_ACCESS_TOKEN', ''))
handler = WebhookHandler(os.environ.get('CHANNEL_SECRET', ''))
supabase_url = os.environ.get('SUPABASE_URL', '')
supabase_key = os.environ.get('SUPABASE_KEY', '')
supabase = create_client(supabase_url, supabase_key)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text
    
    # 1. 無論狀態為何，只要輸入「選單」就強制重置並顯示選單
    if user_text == "選單":
        # 重置資料庫狀態，防止卡死
        supabase.table("user_status").update({"current_step": "idle"}).eq("user_id", user_id).execute()
        
        # ... 這裡放妳原本的 Flex Message 選單代碼 ...
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(...))
        return # 結束這個 function，不要往下跑了

    # 2. 只有在不是「選單」的情況下，才去抓取狀態
    res = supabase.table("user_status").select("*").eq("user_id", user_id).execute()
    user_data = res.data[0] if res.data else {}
    current_step = user_data.get("current_step", "idle")

    # 3. 根據狀態處理對話
    if current_step == "awaiting_category" and user_text.startswith("分類:"):
        # ... 處理分類的代碼 ...
        pass
    elif current_step == "awaiting_tags":
        # ... 處理標籤的代碼 ...
        pass

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    lat = event.message.latitude
    lon = event.message.longitude
    addr = event.message.address

    # 1. 把位置存入暫存區，並將步驟設為 'awaiting_category'
    supabase.table("user_status").upsert({
        "user_id": user_id,
        "current_step": "awaiting_category",
        "temp_lat": lat,
        "temp_lon": lon,
        "temp_address": addr
    }).execute()

    # 2. 噴出大分類按鈕 (Flex Message)
    category_menu = {
        "type": "bubble",
        "body": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📍 位置已記錄", "weight": "bold", "size": "sm"},
                {"type": "text", "text": "請選擇餐廳大分類", "weight": "bold", "size": "xl", "margin": "md"},
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm",
                 "contents": [
                     {"type": "button", "style": "primary", "color": "#E67E22", "action": {"type": "message", "label": "🍚 主食", "text": "分類:主食"}},
                     {"type": "button", "style": "primary", "color": "#F1C40F", "action": {"type": "message", "label": "🍰 甜點", "text": "分類:甜點"}},
                     {"type": "button", "style": "primary", "color": "#2ECC71", "action": {"type": "message", "label": "🥤 飲料", "text": "分類:飲料"}},
                     {"type": "button", "style": "secondary", "action": {"type": "message", "label": "➕ 新增分類", "text": "新增分類"}}
                 ]}
            ]
        }
    }
    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="選擇分類", contents=category_menu))

if __name__ == "__main__":
    app.run()
