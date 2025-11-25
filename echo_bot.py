import sys
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# =========================================================
# !!! 请将此处的占位符替换为您从 BotFather 获得的真实 Token !!!
BOT_TOKEN = '8282877020:AAFHjkzZc_JE504rvzYFABaqm3TMwCN0YUA' 
# =========================================================


# --- 1. 定义处理函数 ---
# 异步函数 (async def) 是新版本的标准写法

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /start 命令"""
    user_name = update.message.from_user.first_name or "勇士"
    
    # context.bot.name 在新版本中通过 Application 获取，这里使用 update.effective_user
    await update.message.reply_text(f'欢迎您，{user_name}！欢迎来到王与奴的世界')
    await update.message.reply_text('请尝试发送一条消息给我，我会复读您的话。')

async def echo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理所有文本消息，实现复读功能"""
    user_text = update.message.text
    # 注意：所有回复操作现在需要 await 关键字
    await update.message.reply_text(f'您发来消息说：“{user_text}”？')


# --- 2. 主函数：启动 Bot (使用 Application) ---

def main() -> None:
    """启动 Bot，设置 Handler 并运行"""
    
    # 核心组件：Application 负责处理所有 Bot 逻辑
    try:
        application = Application.builder().token(BOT_TOKEN).build()
    except Exception:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("致命错误：BOT TOKEN 无效！请检查您复制的 Token 是否正确。")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return

    # 注册 Handler
    # filters.TEXT 和 filters.COMMAND 是新版本中替代旧版 Filters 的写法
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_message))

    # 启动 Bot
    print("---------------------------------------")
    print("✅ 核心连接成功！Bot 正在运行...")
    print("请在 Telegram 中找到您的 Bot 并发送 /start。")
    print("按 Ctrl+C 停止 Bot。")
    print("---------------------------------------")
    
    # 运行 Bot，阻塞式启动
    application.run_polling(poll_interval=3)

if __name__ == '__main__':
    # 修复 Python < 3.10 在 Windows 上的 asyncio 兼容性问题
    try:
        main()
    except RuntimeError:
        # 这是 Windows 终端常见的静默错误，通过设置策略可以避免
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            main()