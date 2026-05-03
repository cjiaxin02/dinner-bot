import os
from linebot import LineBotApi
from linebot.models import TextSendMessage

# 從環境變數讀取金鑰 (保護資安)
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
# 這裡填入妳自己的 LINE User ID (或是從資料庫抓取)
user_id = os.environ.get('MY_LINE_USER_ID') 

def send_reminder():
    try:
        msg = "🔔 Dorothy，吃飯時間到了！\n快打開機器人，讓我想想今天吃什麼好料的？"
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
        print("推播成功！")
    except Exception as e:
        print(f"推播失敗: {e}")

if __name__ == "__main__":
    send_reminder()
