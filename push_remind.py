import os
from linebot import LineBotApi
from linebot.models import TextSendMessage
from supabase import create_client

# 初始化
line_bot_api = LineBotApi('妳的Channel_AccessToken')
supabase = create_client('URL', 'KEY')

def send_reminders():
    # 1. 撈出所有使用者 ID (或是只有妳自己)
    users = supabase.table("user_status").select("user_id").execute()
    
    for u in users.data:
        # 這裡甚至可以先幫她抽好一家店
        line_bot_api.push_message(
            u['user_id'], 
            TextSendMessage(text="🔔 報時！現在是吃飯時間，需要我幫妳推薦附近的餐廳嗎？")
        )

if __name__ == "__main__":
    send_reminders()
