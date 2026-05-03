import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client
from linebot.models import LocationMessage, LocationSendMessage
from linebot.models import FlexSendMessage

app = Flask(__name__)

# --- 1. 初始化連線 ---
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))
supabase: Client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['x-line-signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 2. 輔助函式：取得/初始化使用者狀態 ---
def get_user_status(user_id):
    res = supabase.table("user_status").select("*").eq("user_id", user_id).execute()
    if not res.data:
        # 第一次見面，幫他註冊
        profile = line_bot_api.get_profile(user_id)
        new_user = {"user_id": user_id, "user_name": profile.display_name, "current_step": "idle"}
        supabase.table("user_status").insert(new_user).execute()
        return new_user
    return res.data[0]

# --- 3. 處理「文字訊息」 ( handle_message ) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text
    user_status = get_user_status(user_id)
    current_step = user_status.get("current_step")

    # A. 優先級最高：系統指令
    if user_text == "選單" or user_text == "取消":
        # 強制將狀態重置為 idle
        supabase.table("user_status").update({"current_step": "idle"}).eq("user_id", user_id).execute()
        
        flex_menu = {
          "type": "bubble",
          "header": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": "🍽️ 美食小助手", "weight": "bold", "size": "xl", "color": "#ffffff"}
            ], "backgroundColor": "#4b7a47"
          },
          "body": {
            "type": "box", "layout": "vertical", "contents": [
              {"type": "text", "text": "今天想吃什麼？", "size": "sm", "color": "#888888"},
              {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                  {
                    "type": "button", "style": "primary", "color": "#4b7a47",
                    "action": {"type": "message", "label": "✨ 發現了好吃的店!", "text": "新增餐廳"}
                  },
                  {
                    "type": "button", "style": "secondary",
                    "action": {"type": "message", "label": "⏰ 吃飯時間到了", "text": "肚子餓了"}
                  },
                  {
                    "type": "button", "style": "link",
                    "action": {"type": "message", "label": "📒 查看與修訂清單", "text": "我的清單"}
                  }
                ]
              }
            ]
          }
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="請選擇功能", contents=flex_menu))
        return

    # B. 根據狀態分流處理對話
    if current_step == "idle":
        if user_text == "新增餐廳":
            # 將狀態切換為 awaiting_location
            supabase.table("user_status").update({"current_step": "awaiting_location"}).eq("user_id", user_id).execute()
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="太棒了！請點選左下角「＋」號，選擇「傳送位置資訊」，告訴我這家店在哪裡～")
            )
            return
        elif user_text == "肚子餓了":
            # [ 待填入：啟動抽籤邏輯 ]
            pass

    elif current_step == "awaiting_category":
        # [ 待填入：處理分類選擇 ]
        pass

    elif current_step == "awaiting_tags":
        # [ 待填入：處理標籤輸入並正式入庫 ]
        pass

# --- 4. 處理「位置訊息」 ( handle_location ) ---
@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    user_status = get_user_status(user_id)
    current_step = user_status.get("current_step")

    if current_step == "awaiting_location":
        # [ 待填入：紀錄餐廳位置暫存並詢問分類 ]
        pass
    elif current_step == "awaiting_user_location":
        # [ 待填入：計算距離並抽籤 ]
        pass

if __name__ == "__main__":
    app.run()
