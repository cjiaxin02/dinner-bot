import os
from linebot import LineBotApi
from linebot.models import TextSendMessage
from supabase import create_client # 記得要用資料庫了

# 1. 初始化金鑰
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')
supabase = create_client(supabase_url, supabase_key)

def send_to_all_users():
    try:
        # 2. 從資料庫抓取所有不重複的 user_id
        # 假設妳的用戶資料存在 user_status 表
        res = supabase.table("user_status").select("user_id").execute()
        user_list = [u['user_id'] for u in res.data]
        
        msg = "🔔 吃飯時間到了！\n快跟我說妳在哪裡，讓我幫妳挑選附近的好餐廳吧！"
        
        # 3. 逐一推播 (或是使用 multicast)
        for uid in user_list:
            try:
                line_bot_api.push_message(uid, TextSendMessage(text=msg))
                print(f"成功發送給: {uid}")
            except Exception as e:
                print(f"發送給 {uid} 失敗: {e}")
                
    except Exception as e:
        print(f"資料庫讀取失敗: {e}")

if __name__ == "__main__":
    send_to_all_users()
