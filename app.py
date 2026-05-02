import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client

app = Flask(__name__)

# 從環境變數讀取金鑰 (Render 設定區)
line_bot_api = LineBotApi(os.environ.get('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('CHANNEL_SECRET'))
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')
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
    user_id = event.source.user_id
    
    # 測試：把說話紀錄存進 Supabase (這會用到妳之前創的 user_status 表)
    # 如果還沒創好表，這部分會報錯，但沒關係，我們先測試回話
    try:
        supabase.table("user_status").upsert({"user_id": user_id, "user_name": "Dorothy"}).execute()
        reply = f"妳說了：{user_text}\n(資料庫已更新！)"
    except:
        reply = f"妳說了：{user_text}\n(資料庫連線測試中...)"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()
