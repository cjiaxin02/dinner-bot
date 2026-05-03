import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client
from linebot.models import LocationMessage, LocationSendMessage
from linebot.models import FlexSendMessage
from datetime import datetime, timedelta
from linebot.models import PostbackEvent # <--- 確保這行有加進去
# 同時為了處理 Postback 的資料解析，補上這行
from urllib.parse import parse_qsl
import math # 記得在檔案最上方加上這行

def get_distance(lat1, lon1, lat2, lon2):
    # Haversine 公式：計算球面上兩點距離
    R = 6371  # 地球半徑 (km)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

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
    if user_text.startswith("清單:"):
        # 解析分頁參數，例如 "清單:全部:10" 代表從第 10 筆開始抓
        parts = user_text.split(":")
        offset = int(parts[-1]) if parts[-1].isdigit() else 0
        base_cmd = "清單:全部" if "全部" in user_text else f"清單:分類:{parts[2]}"

        query = supabase.table("restaurants").select("*").eq("user_id", user_id)
        if "分類:" in user_text:
            query = query.eq("category", parts[2])
        
        # 抓取 11 筆，若有第 11 筆代表有「下一頁」
        res = query.order("created_at", desc=True).range(offset, offset + 10).execute()
        shops = res.data

        bubbles = []
        # 前 10 筆正常顯示
        for s in shops[:10]:
            # --- 1. 核心修正：確保 tag_list 無論如何都會被定義 ---
            tags_str = s.get('tags') or ""  # 避免 NoneType 報錯
            tag_list = tags_str.split() if tags_str else [] 
            
            # 建立標籤組的內容清單
            tag_contents = []
            for tag in tag_list[:3]:  # 取前三個標籤
                tag_contents.append({
                    "type": "text",
                    "text": tag,
                    "size": "xxs",
                    "color": "#ffffff",
                    "backgroundColor": "#7ba376",
                    "margin": "xs",
                    "paddingAll": "2px",
                    "flex": 0
                })

            # --- 2. 組裝卡片 ---
            bubbles.append({
                "type": "bubble",
                "size": "micro",
                "body": {
                    "type": "box", 
                    "layout": "vertical", 
                    "contents": [
                        {"type": "text", "text": s['name'], "weight": "bold", "size": "md"},
                        {"type": "text", "text": f"📍 {s['category']}", "size": "xs", "color": "#4b7a47", "margin": "xs"},
                        # 插入標籤容器
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "md",
                            "contents": tag_contents  # 這裡會用到上面的 tag_contents
                        },
                        {"type": "text", "text": s['address'] or "無地址資訊", "size": "xxs", "color": "#aaaaaa", "wrap": True, "margin": "md"}
                    ]
                },
                "footer": {
                    "type": "box", 
                    "layout": "vertical", 
                    "contents": [
                        {"type": "button", "style": "link", "height": "sm", "action": {"type": "uri", "label": "導航", "uri": f"https://www.google.com/maps/search/?api=1&query={s['lat']},{s['lon']}"}}
                    ]
                }
            })

        # 如果有第 11 筆，加入「查看更多」卡片
        if len(shops) > 10:
            bubbles.append({
                "type": "bubble",
                "size": "micro",
                "body": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": "還有更多餐廳...", "align": "center", "gravity": "center"}
                    ]
                },
                "footer": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "button", "style": "primary", "color": "#4b7a47", "action": {"type": "message", "label": "下一頁", "text": f"{base_cmd}:{offset + 10}"}}
                    ]
                }
            })

        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="餐廳清單", contents={"type": "carousel", "contents": bubbles}))

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
            # 1. 將狀態切換為 awaiting_user_location
            supabase.table("user_status").update({"current_step": "awaiting_user_location"}).eq("user_id", user_id).execute()
            
            # 2. 提示使用者傳送「現在」的位置
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="肚子餓了嗎？請傳送妳『現在的位置資訊』，我幫妳找找方圓 1 公里內好吃的！")
            )
            return
        elif user_text == "我的清單":
            # 1. 撈取該用戶現有的所有不重複分類
            res = supabase.table("restaurants").select("category").eq("user_id", user_id).execute()
            categories = list(set([r['category'] for r in res.data if r['category']]))
            
            # 2. 組裝篩選按鈕 (Flex Message)
            filter_buttons = [
                {"type": "button", "action": {"type": "message", "label": "📋 顯示全部", "text": "清單:全部"}, "style": "primary", "color": "#4b7a47"}
            ]
            
            # 動態加入妳有的分類
            for cat in categories[:5]: # 取前五個
                filter_buttons.append({
                    "type": "button", "action": {"type": "message", "label": f"🔍 {cat}", "text": f"清單:分類:{cat}"}, "style": "secondary"
                })
    
            filter_flex = {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical", "spacing": "md", "contents": [
                        {"type": "text", "text": "📒 我的美食帳本", "weight": "bold", "size": "xl"},
                        {"type": "text", "text": "請選擇篩選方式：", "size": "sm", "color": "#888888"},
                        {"type": "box", "layout": "vertical", "spacing": "sm", "contents": filter_buttons}
                    ]
                }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="查看清單", contents=filter_flex))
            return
        
    elif current_step == "awaiting_category":
        if user_text == "動作:自定義分類":
            # 狀態維持在等待分類，但提示使用者直接輸入文字
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請直接輸入妳想設定的大分類名稱（例如：主食、甜點、飲料）：")
            )
            return
            
        elif user_text.startswith("分類:") or user_status.get("current_step") == "awaiting_category":
            # 如果是點擊按鈕，去掉前綴；如果是直接輸入，就直接用 user_text
            category = user_text.split(":")[1] if user_text.startswith("分類:") else user_text
            
            supabase.table("user_status").update({
                "current_step": "awaiting_tags",
                "temp_category": category
            }).eq("user_id", user_id).execute()
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"已設定為【{category}】！\n最後一步：請輸入「小標籤」，若不填請輸入「無」。")
            )
            return

    elif current_step == "awaiting_tags":
        tags = user_text if user_text != "無" else ""
        user_data = supabase.table("user_status").select("*").eq("user_id", user_id).single().execute().data
        
        # 正式入庫，這次加上了 user_id
        supabase.table("restaurants").insert({
            "user_id": user_id,  # <--- 重要：記錄是誰存的
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
        # 1. 從餐廳表撈出該用戶存過、不重複的前幾個大分類
        existing_cats_res = supabase.table("restaurants") \
            .select("category") \
            .eq("user_id", user_id) \
            .execute()
        
        # 使用 set 取得不重複的分類，並過濾掉 None
        user_categories = list(set([r['category'] for r in existing_cats_res.data if r['category']]))
        # 只取前 5 個預設+妳新增過的，留位置給「新增分類」按鈕
        display_cats = user_categories[:5] 
        
    
        # 2. 動態組裝按鈕清單
        buttons = []
        for cat in display_cats:
            buttons.append({
                "type": "button",
                "action": {"type": "message", "label": f"🍚 {cat}", "text": f"分類:{cat}"},
                "style": "primary", "color": "#4b7a47", "margin": "sm"
            })
        
        # 永遠保留「新增分類」按鈕
        buttons.append({
            "type": "button",
            "action": {"type": "message", "label": "➕ 新增其他分類", "text": "動作:自定義分類"},
            "style": "secondary", "margin": "sm"
        })
    
        # 3. 組裝完整的 Flex Message
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
                    {"type": "text", "text": "請選擇分類（建議最多5個分類）：", "size": "sm", "color": "#888888", "margin": "md"},
                    {"type": "box", "layout": "vertical", "margin": "lg", "contents": buttons}
                ]
            }
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="請選擇分類", contents=category_flex))
    
    if current_step == "awaiting_user_location":
        user_lat = event.message.latitude
        user_lon = event.message.longitude
        
        # 1. 從資料庫撈出該使用者的「所有」餐廳
        res = supabase.table("restaurants").select("*").eq("user_id", user_id).execute()
        all_restaurants = res.data
        
        # 2. 過濾出一公里內的店家
        nearby_shops = []
        for shop in all_restaurants:
            dist = get_distance(user_lat, user_lon, shop['lat'], shop['lon'])
            if dist <= 1.0: # 1.0 公里
                shop['dist'] = round(dist, 2) # 順便記錄距離
                nearby_shops.append(shop)
        
        # 3. 處理結果
        if not nearby_shops:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="哎呀！妳附近一公里內好像還沒有存過任何餐廳耶。快去『新增餐廳』吧！")
            )
        else:
            # 隨機挑選最多 5 家 (資工系常用 random.sample)
            import random
            display_count = min(len(nearby_shops), 5)
            selected_shops = random.sample(nearby_shops, display_count)
            
            # [ 下一步：我們要用 Flex Message 把它畫成精美的推薦卡 ]
            bubbles = []
            for s in selected_shops:
                # 1. 處理標籤邏輯：將字串切成陣列
                tag_list = s['tags'].split() if s['tags'] else []
                tag_contents = []
                
                # 動態產生標籤的 JSON 組件
                for tag in tag_list:
                    tag_contents.append({
                        "type": "box", "layout": "horizontal", "contents": [
                            {"type": "text", "text": f"#{tag}", "size": "xxs", "color": "#4b7a47"}
                        ],
                        "backgroundColor": "#E8F5E9", "paddingAll": "2px", "cornerRadius": "4px", "margin": "xs"
                    })
    
                # 2. 組裝單個餐廳的卡片 (Bubble)
                bubble = {
                  "type": "bubble",
                  "size": "micro", # 使用微型卡片，這樣一次可以滑動看 5 家
                  "body": {
                    "type": "box", "layout": "vertical", "contents": [
                      {"type": "text", "text": s['name'], "weight": "bold", "size": "sm", "wrap": True},
                      {"type": "text", "text": f"{s['dist']} km | {s['category']}", "size": "xxs", "color": "#888888", "margin": "xs"},
                      # 這裡放入剛才動態生成的標籤盒
                      {"type": "box", "layout": "horizontal", "contents": tag_contents, "margin": "md", "flex": 1, "wrap": True}
                    ]
                  },
                  "footer": {
                    "type": "box", "layout": "vertical", "contents": [
                      {
                        "type": "button", "style": "primary", "color": "#4b7a47", "height": "sm",
                        "action": {
                          "type": "postback", 
                          "label": "前往用餐", 
                          "data": f"action=eat&res_id={s['id']}&res_name={s['name']}"
                        }
                      }
                    ]
                  }
                }
                bubbles.append(bubble)
    
            # 3. 封裝成 Carousel (輪播介面)
            carousel = {"type": "carousel", "contents": bubbles}
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="為妳挑選的餐廳", contents=carousel))

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    # 解析傳回來的資料：action=eat&res_id=123&res_name=店名
    data = dict(parse_qsl(event.postback.data))
    
    if data.get("action") == "eat":
        res_id = data.get("res_id")
        res_name = data.get("res_name")
        
        # 1. 檢查這家餐廳最近一次的用餐紀錄
        last_meal = supabase.table("meals") \
            .select("created_at") \
            .eq("restaurant_id", res_id) \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        can_eat = True
        if last_meal.data:
            # 轉換時間格式 (Supabase 回傳的是 ISO 格式字串)
            last_time = datetime.fromisoformat(last_meal.data[0]['created_at'].replace('Z', '+00:00'))
            now = datetime.now(last_time.tzinfo)
            
            # 檢查是否過了 4.5 小時
            if now - last_time < timedelta(hours=4.5):
                can_eat = False
                wait_time = timedelta(hours=4.5) - (now - last_time)
                minutes = int(wait_time.total_seconds() // 60)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"🚫 這家店剛吃過喔！冷卻中...\n還要再等 {minutes} 分鐘才能再次選擇。")
                )
        
        if can_eat:
            # 2. 記錄這次用餐
            supabase.table("meals").insert({
                "restaurant_id": res_id,
                "user_id": user_id
            }).execute()
            
            # 3. 抓取餐廳座標來生成 Google Maps 連結
            res_info = supabase.table("restaurants").select("lat, lon").eq("id", res_id).single().execute().data
            maps_url = f"https://www.google.com/maps/search/?api=1&query={res_info['lat']},{res_info['lon']}"
            
            line_bot_api.reply_message(
                event.reply_token,
                [
                    TextSendMessage(text=f"🍴 出發前往『{res_name}』！\n這家店已經為妳上鎖 4.5 小時囉。"),
                    TextSendMessage(text=f"導航連結：{maps_url}")
                ]
            )
    # 在 handle_postback 裡面加入這兩個 action 判斷
    elif data.get("action") == "confirm_del":
        # 噴出確認視窗，避免手滑
        confirm_flex = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "確定要刪除嗎？", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": f"餐廳：{data.get('res_name')}\n刪除後資料將無法找回。", "size": "sm", "color": "#ff0000", "wrap": True, "margin": "md"}
                ]
            },
            "footer": {
                "type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    {"type": "button", "style": "primary", "color": "#FF5555", "action": {"type": "postback", "label": "確定刪除", "data": f"action=real_del&res_id={data.get('res_id')}"}},
                    {"type": "button", "style": "secondary", "action": {"type": "message", "label": "取消", "text": "取消"}}
                ]
            }
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="確認刪除", contents=confirm_flex))

    elif data.get("action") == "real_del":
        # 真正執行刪除動作
        res_id = data.get("res_id")
        supabase.table("restaurants").delete().eq("id", res_id).eq("user_id", user_id).execute()
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🗑️ 已成功將該餐廳從清單中移除。"))

from linebot.models import UnfollowEvent

@handler.add(UnfollowEvent)
def handle_unfollow(event):
    user_id = event.source.user_id
    
    # 1. 刪除該使用者的狀態紀錄
    supabase.table("user_status").delete().eq("user_id", user_id).execute()
    
    # 2. 刪除該使用者的餐廳清單 (選選：看妳是否要幫她保留資料)
    # 如果想徹底清除，就執行這行：
    supabase.table("restaurants").delete().eq("user_id", user_id).execute()
    
    # 3. 刪除用餐紀錄
    supabase.table("meals").delete().eq("user_id", user_id).execute()
    
    print(f"User {user_id} has unfollowed. Data cleared.")

if __name__ == "__main__":
    app.run()
