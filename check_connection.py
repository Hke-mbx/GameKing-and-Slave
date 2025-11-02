import telegram

# =========================================================
# !!! 请替换成您的实际 Bot Token !!!
BOT_TOKEN = '8282877020:AAFHjkzZc_JE504rvzYFABaqm3TMwCN0YUA' 
# =========================================================

def check_bot_connection():
    """尝试使用提供的 Token 连接到 Telegram API 并获取 Bot 信息。"""
    print("--- Telegram 连接诊断开始 ---")
    
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        bot_info = bot.get_me()
        
        print("✅ 成功！Bot Token 有效，且网络连接畅通。")
        print(f"   Bot 用户名: @{bot_info.username}")
        return True

    except telegram.error.InvalidToken:
        print("❌ 致命错误：InvalidToken。您提供的 Bot Token 无效或有误。")
        return False
        
    except Exception as e:
        if "timeout" in str(e).lower() or "connection" in str(e).lower():
            print("❌ 警告：网络连接超时或失败。请检查您的网络连接。")
        else:
            print(f"❌ 未知错误: {e}")
            
        return False
    finally:
        print("--- 诊断结束 ---")


if __name__ == '__main__':
    check_bot_connection()
