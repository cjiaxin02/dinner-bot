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
    user_text = event.message.text
    
    # 當使用者傳送「選單」或剛加入好友時
    if user_text == "選單" or user_text == "開始使用":
        flex_menu = {
          "type": "bubble",
          "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
              {"type": "text", "text": "🍽️ 美食小助手", "weight": "bold", "size": "xl"},
              {"type": "text", "text": "今天要怎麼犒賞自己？", "size": "sm", "color": "#aaaaaa"},
              {"type": "separator", "margin": "md"},
              {
                "type": "button",
                "action": {"type": "message", "label": "✨ 發現了好吃的店!", "text": "新增餐廳"},
                "style": "primary", "margin": "md", "color": "#4b7a47"
              },
              {
                "type": "button",
                "action": {"type": "message", "label": "⏰ 吃飯時間到了", "text": "肚子餓了"},
                "style": "secondary", "margin": "sm"
              },
              {
                "type": "button",
                "action": {"type": "message", "label": "📒 查看與修訂清單", "text": "我的清單"},
                "style": "link", "margin": "sm"
              }
            ]
          }
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="請選擇功能", contents=flex_menu))
    else:
        # 其他文字處理...
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="輸入「選單」開啟功能"))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    lat = event.message.latitude  # 緯度
    lon = event.message.longitude # 經度
    address = event.message.address # 地址
    
    # 這裡之後會用來寫入資料庫
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"收到位置：{address}\n座標：({lat}, {lon})\n接下來請告訴我大分類？")
    )

if __name__ == "__main__":
    app.run()
