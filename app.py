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
    
        return # 結束這個 function，不要往下跑了

    # --- 優先級 B: 觸發功能入口 ---
    if user_text == "新增餐廳":
        # 1. 將狀態設為「等待位置」
        supabase.table("user_status").update({"current_step": "awaiting_location"}).eq("user_id", user_id).execute()
        # 2. 提示使用者傳送位置
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="太棒了！請點選左下角「＋」號，選擇「傳送位置資訊」，告訴我這家店在哪裡～")
        )
        return
    
    # 2. 只有在不是「選單」的情況下，才去抓取狀態
    res = supabase.table("user_status").select("*").eq("user_id", user_id).execute()
    user_data = res.data[0] if res.data else {}
    current_step = user_data.get("current_step", "idle")

    # 處理「大分類」的選擇
    if current_step == "awaiting_category" and user_text.startswith("分類:"):
        category = user_text.split(":")[1]
        
        # 將大分類存入暫存 (這裡需要妳在 SQL 增加 temp_category 欄位)
        supabase.table("user_status").update({
            "current_step": "awaiting_tags",
            "temp_category": category # 建議在 SQL 增加這個欄位
        }).eq("user_id", user_id).execute()
        
        # 這裡改用 Flex Message 送出「小標籤」按鈕
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"已設定為【{category}】！\n接下來請輸入「小標籤」，多個標籤請用空格隔開（例如：有插座 環境美），若不填請輸入「無」。")
        )

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
