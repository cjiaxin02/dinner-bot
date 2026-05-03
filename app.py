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

    elif current_step == "awaiting_category" and user_text.startswith("分類:"):
        category = user_text.split(":")[1]
        
        # 紀錄分類並進入「等待標籤」狀態
        supabase.table("user_status").update({
            "current_step": "awaiting_tags",
            "temp_category": category
        }).eq("user_id", user_id).execute()
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"已設定為【{category}】！\n最後一步：請輸入「小標籤」（例如：有插座 環境美），多個標籤請用空格隔開。\n若不想填寫，請直接回傳「無」。")
        )

    elif current_step == "awaiting_tags":
        tags = user_text if user_text != "無" else ""
        
        # 1. 從暫存區撈出剛才存的所有資訊
        user_data = supabase.table("user_status").select("*").eq("user_id", user_id).single().execute().data
        
        # 2. 正式寫入餐廳主表
        supabase.table("restaurants").insert({
            "name": user_data["temp_name"],
            "category": user_data["temp_category"],
            "tags": tags,
            "lat": user_data["temp_lat"],
            "lon": user_data["temp_lon"],
            "address": user_data["temp_address"]
        }).execute()
        
        # 3. 歸零狀態，清空暫存區
        supabase.table("user_status").update({
            "current_step": "idle",
            "temp_name": None, "temp_lat": None, "temp_lon": None, 
            "temp_address": None, "temp_category": None
        }).eq("user_id", user_id).execute()
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"🎉 萬歲！『{user_data['temp_name']}』已成功存入妳的美食資料庫！")
        )

# --- 4. 處理「位置訊息」 ( handle_location ) ---
@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    user_status = get_user_status(user_id)
    current_step = user_status.get("current_step")

    # 邏輯：當使用者正處於「新增餐廳」的流程中
    if current_step == "awaiting_location":
        lat = event.message.latitude
        lon = event.message.longitude
        addr = event.message.address
        title = event.message.title if event.message.title else "這家神祕餐廳"

        # 1. 更新資料庫暫存區，並跳轉至下一步驟
        supabase.table("user_status").update({
            "current_step": "awaiting_category",
            "temp_lat": lat,
            "temp_lon": lon,
            "temp_address": addr,
            "temp_name": title
        }).eq("user_id", user_id).execute()

        # 2. 噴出大分類選擇圖卡
        category_flex = {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "📍 位置已記錄", "color": "#ffffff", "weight": "bold", "size": "sm"}
                ], "backgroundColor": "#4b7a47"
            },
            "body": {
                "type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "xl"},
                    {"type": "text", "text": "請選擇這家店的大分類：", "size": "sm", "color": "#888888", "margin": "md"},
                    {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                        {"type": "button", "action": {"type": "message", "label": "🍚 主食", "text": "分類:主食"}, "style": "primary", "color": "#E67E22"},
                        {"type": "button", "action": {"type": "message", "label": "🍰 甜點", "text": "分類:甜點"}, "style": "primary", "color": "#F1C40F"},
                        {"type": "button", "action": {"type": "message", "label": "🥤 飲料", "text": "分類:飲料"}, "style": "primary", "color": "#2ECC71"},
                        {"type": "button", "action": {"type": "message", "label": "🏪 超商", "text": "分類:超商"}, "style": "secondary"}
                    ]}
                ]
            }
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="請選擇分類", contents=category_flex))

if __name__ == "__main__":
    app.run()
