import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import random
import asyncio

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# =========================================================
# !!! 请替换为您的真实 Token !!!
BOT_TOKEN = '8282877020:AAFHjkzZc_JE504rvzYFABaqm3TMwCN0YUA'  
# =========================================================

# --- I. 游戏数据与常量 ---

# 1. 核心卡牌数据定义 (CARD_DATA)
# [等级, 派系, 特殊效果]
CARD_DATA = {
    'Citizen': [1, 'King', None],  
    'Assassin': [2, 'Neutral', 'Assassin'],  
    'Butcher': [2, 'Neutral', 'Butcher'],  
    'Royal Guard': [2, 'King', 'RoyalGuard'],  
    'King': [3, 'King', 'KeyCard'],  
    'Ultimate Sentinel': [3, 'King', 'UltimateSentinel'], # 等级 3，具有复杂逻辑
    'Queen': [3, 'King', 'Queen'],  
    'Slave': [0, 'Slave', 'Slave'],  
    'Guard': [2, 'Slave', None],
}

# --- 0. 卡牌表情符号映射 (EMOJI) ---
CARD_EMOJIS = {
    'Citizen': '🧑‍🌾',        # 市民
    'Assassin': '🔪',        # 刺客
    'Butcher': '🥩',         # 屠夫
    'Royal Guard': '🛡️',     # 皇家护卫 (死时保护 King)
    'King': '👑',            # 国王 (关键牌)
    'Ultimate Sentinel': '⚔️', # 终极哨兵 (复杂战斗规则，死时保护 Queen)
    'Queen': '💐',           # 女王 (关键牌，死时带走对手牌，王权继承)
    'Slave': '⛓️',          # 奴隶 (击杀王/女王)
    'Guard': '💂',           # 卫兵
}
# -----------------------------------------------

# 2. 阵营卡组定义 (FACTION_DECKS)
FACTION_DECKS = {
    'KingOpening_King': ['Citizen', 'Citizen', 'Assassin', 'Butcher', 'Royal Guard', 'King'],
    'KingOpening_Slave': ['Citizen', 'Citizen', 'Slave', 'Slave', 'Guard', 'Assassin', 'Butcher'],
    
    'QueenOpening_King': ['Citizen', 'Citizen', 'Assassin', 'Butcher', 'Ultimate Sentinel', 'Queen'],  
    'QueenOpening_Slave': ['Citizen', 'Citizen', 'Slave', 'Slave', 'Guard', 'Assassin', 'Butcher'],  
}

# 3. 游戏状态和键盘
game_states = {} # 主游戏状态字典

RPS_KEYBOARD = [
    [
        InlineKeyboardButton("✂️ 剪刀", callback_data='rps_scissors'),
        InlineKeyboardButton("🪨 石头", callback_data='rps_rock'),
        InlineKeyboardButton("📄 布", callback_data='rps_paper')
    ]
]
RPS_MARKUP = InlineKeyboardMarkup(RPS_KEYBOARD)

KNS_KEYBOARD = [
    [InlineKeyboardButton("👑 选择国王方 (King Faction)", callback_data='kns_King')],
    [InlineKeyboardButton("⛓️ 选择奴隶方 (Slave Faction)", callback_data='kns_Slave')]
]
KNS_MARKUP = InlineKeyboardMarkup(KNS_KEYBOARD)

KING_OPENING_CHOICE_KEYBOARD = [
    [InlineKeyboardButton("👑 国王开局 (King Opening)", callback_data='select_opening_KingOpening')],
    [InlineKeyboardButton("💐 女王开局 (Queen Opening)", callback_data='select_opening_QueenOpening')],
]
KING_OPENING_CHOICE_MARKUP = InlineKeyboardMarkup(KING_OPENING_CHOICE_KEYBOARD)


# --- 4. 规则文本常量 (用于分步显示) ---

VICTORY_RULES_TEXT = (
    "📜 **一、胜利条件 (通用)**\n\n"
    "* **国王方 (King) 胜：** 奴隶方手牌耗尽，无法再击杀关键牌。\n"
    "* **奴隶方 (Slave) 胜：** 击杀国王方的关键牌（国王或女王）。\n"
)

BATTLE_RULES_TEXT = (
    "⚔️ **二、基础战斗规则**\n\n"
    "1. **等级比较：** Level 高者胜，败者阵亡进『废牌区』，胜者回『手牌』。\n"
    "2. **Level 相同：** 双方 **同归于尽**，均进『废牌区』。\n"
)

CARD_RULES_TEXT = (
    "⚜️ **三、卡牌独立规则 (按等级排序)**\n\n"
    
    "**L0 基础牌**\n"
    "* **⛓️ 奴隶 (Slave)：**\n"
    "    * **特殊能力：** 能够 **直接击杀** Level 3 的 **King** 或 **Queen**。\n"
    "    * **限制：** 极易被除奴隶外的其他卡牌击杀。\n\n"
    
    "**L1 基础牌与关键牌**\n"
    "* **🧑‍🌾 市民 (Citizen)：**\n"
    "    * **特殊能力：** 只能击败 **奴隶**。\n"
    "    * **限制：** 遇到非奴隶卡牌，市民必定阵亡。\n"
    "* **💐 女王 (Queen) (L1)：**\n"
    "    * **关键牌/特殊机制：** **不可主动打出。** 阵亡时带走对手牌（双方阵亡），并将 **King 卡牌** 立即加入手牌（王权继承）。\n\n"
        
    "**L2 战斗与护卫牌**\n"
    "* **🔪 刺客 (Assassin)：**\n"
    "    * **特殊能力：** **无视等级**，击杀对手的牌，但自身也阵亡（同归于尽式暗杀）。\n"
    "    * **注意：** 双方同时出刺客，则双方刺客阵亡。\n"
    "* **⚒️ 屠夫 (Butcher)：**\n"
    "    * **特殊能力：** **优先一切规则**。只要屠夫出战，**双方卡牌必然同归于尽**。\n"
    "* **🛡️ 皇家护卫 (Royal Guard) (King Opening 限定)：**\n"
    "    * **特殊能力：** 阵亡时，**下一回合** 赋予 **King** 『免死』保护（免死一次并回手）。\n"
    "* **💂 卫兵 (Guard) (L2/奴隶方)：**\n"
    "    * **特殊能力：** 无。\n\n"

    "**L3 关键牌与终极单位**\n"
    "* **👑 国王 (King)：**\n"
    "    * **关键牌：** 阵亡则游戏结束。\n"
    "    * **优势：** Level 3 提供了基础战斗优势。\n"
    "* **⚔️ 终极哨兵 (Ultimate Sentinel) (Queen Opening 限定)：**\n"
    "    * **战斗：** 击杀一切 **非屠夫** 卡牌（含 L0~L3），自身存活并回手。\n"
    "    * **vs 刺客：** 击杀刺客，自身 **存活**。\n"
    "    * **献祭：** 阵亡时，**下一回合** 赋予 **Queen** 『免死』保护。\n"
    "    * **限制 1：** **不能连续两回合打出**。\n"
    "    * **限制 2：** 若 **Queen 阵亡**，终极哨兵强制阵亡。\n"
)

# --- 规则主菜单配置 ---
RULES_MAIN_MENU_TEXT = "👑 **《王冠与锁链：秘闻录》游戏规则菜单** ⛓️"

RULES_MAIN_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📜 一、胜利条件", callback_data='rule_menu_victory')],
    [InlineKeyboardButton("⚔️ 二、基础战斗规则", callback_data='rule_menu_battle')],
    [InlineKeyboardButton("⚜️ 三、卡牌独立规则", callback_data='rule_menu_cards')],
])


# --- II. 辅助函数：卡牌与状态管理 ---

def get_card_info(card_name):
    """获取卡牌的等级和特殊效果"""
    info = CARD_DATA.get(card_name, [0, 'Unknown', None])
    return {'level': info[0], 'faction': info[1], 'effect': info[2]}

def generate_card_buttons(hand: list) -> list:
    """根据手牌生成出牌按钮，回调数据为 'card_selected_'"""
    buttons = []
    current_row = []
    
    # 使用 set 来获取唯一卡牌列表
    unique_hand = list(dict.fromkeys(hand))  
    
    for card in unique_hand:
        emoji = CARD_EMOJIS.get(card, '❓')
        # 优化显示：展示当前剩余张数
        button_text = f"{emoji} {card} ({hand.count(card)})" 
        current_row.append(InlineKeyboardButton(button_text, callback_data=f'card_selected_{card}'))  
        
        if len(current_row) >= 2:  
            buttons.append(current_row)
            current_row = []
            
    if current_row:
        buttons.append(current_row)
        
    return buttons

# --- III. 回合流程与战斗结算函数 (精简版，省略了完整的 process_rps_winner 和 execute_battle 实现) ---

async def start_new_turn(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """启动新的回合，提示玩家出牌，并私下分配出牌按钮 (更新保护状态清理)"""
    # 这里的 chat_id 是群聊ID (original_chat_id)
    state = game_states[chat_id]
    
    if state['status'] == 'finished':
          return
          
    state['status'] = 'playing_turn'
    state['current_turn'] += 1
    state['moves'] = {} # 重置出牌
    
    turn_message = f"--- **回合 {state['current_turn']} 开始！** ---\n"
    
    for user_id in [state['host_id'], state['opponent_id']]:
        player_data = state.get(user_id)
        if player_data is None:
            logging.error(f"Player data missing for user {user_id} in chat {chat_id}.")
            continue 
            
        player_name = player_data['name']  
        
        # 【更新逻辑】回合开始时，移除上一回合的保护状态 (冷却结束)
        if 'RoyalGuard_Protection' in player_data['special_status']:
            player_data['special_status'].remove('RoyalGuard_Protection')
            turn_message += f"**{player_name}** ({player_data['faction']})：🛡️ **皇家护卫保护已解除。**\n"
        
        if 'UltimateSentinel_Protection' in player_data['special_status']:
            player_data['special_status'].remove('UltimateSentinel_Protection')
            turn_message += f"**{player_name}** ({player_data['faction']})：⚔️ **终极哨兵保护已解除。**\n"
        # 【更新逻辑结束】
        
        if not player_data['hand']:
            # 如果手牌为空，跳过出牌提示
            turn_message += f"**{player_name}** ({player_data['faction']})：**手牌为空！** 跳过本回合。\n"
            continue

        hand_buttons = generate_card_buttons(player_data['hand'])
        
        # 额外提示：如果上一回合出了终极哨兵，本回合将无法再次出牌
        if player_data.get('last_played') == 'Ultimate Sentinel':
            turn_message += f"⚠️ **{player_name}**：**终极哨兵** 上回合已出动，本回合无法再次使用。\n"

        card_markup = InlineKeyboardMarkup(hand_buttons)
        
        try:
            # 强制使用私聊发送出牌按钮
            await context.bot.send_message(
                chat_id=user_id,  
                text=f"⚔️ **回合 {state['current_turn']}：** 请出牌！\n\n"
                     f"您当前的手牌：`{', '.join([f'{CARD_EMOJIS.get(c, "?")} {c}' for c in player_data['hand']])}`\n"
                     f"**点击卡牌选择出战！**",
                reply_markup=card_markup,
                parse_mode='Markdown'
            )
            state[user_id]['has_played'] = False
            turn_message += f"**{player_name}** ({player_data['faction']})：已通过私聊发送出牌提示。\n"
        except Exception as e:
             logging.error(f"未能私聊 {user_id} 发送出牌按钮：{e}")
             turn_message += f"⚠️ **{player_name}**：**无法发送私聊！** 请先在 Bot 私聊窗口发送 /start。"
            
    await context.bot.send_message(chat_id, turn_message, parse_mode='Markdown')

async def final_game_end(chat_id: int, context: ContextTypes.DEFAULT_TYPE, winner_faction: str, reason: str, winner_name: str) -> None:
    """游戏结束，发送最终结算消息"""
    state = game_states[chat_id]
    state['status'] = 'finished'
    
    final_message = (
        f"👑 **—— 命运的终章！——** ⛓️\n\n"
        f"🏆 **【胜利者】**：**{winner_name}** (属于 **{winner_faction}** 方)！\n"
        f"📜 **终局宣告：** _{reason}_\n\n"
        f"**恭喜！** 感谢参与这场中世纪的博弈。"
    )
    
    await context.bot.send_message(chat_id, final_message, parse_mode='Markdown')

async def process_rps_winner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """结算剪刀石头布的结果并决定阵营选择权 (完整实现请参考之前的代码)"""
    # 此处为占位符，请确保您的实际文件包含完整的逻辑
    query = update.callback_query
    if query:
        chat_id = query.message.chat_id
    else:
        return 
        
    state = game_states[chat_id]
    p1_id, p2_id = state['host_id'], state['opponent_id']
    
    # 假设这里已经处理完 RPS 逻辑，并确定了 winner_id
    winner_id = state.get('rps_winner_id', p1_id) # 临时默认值
    winner_name = state['host_name'] if winner_id == p1_id else state['opponent_name']
    
    state['status'] = 'choosing_faction'
    
    result_text = f"**RPS 结算：** {winner_name} 胜出！\n"
    result_text += f"🏆 **{winner_name}**，恭喜您获得 **阵营选择权！**\n\n"
    
    try:
        await context.bot.edit_message_text(
            result_text + "请点击下方按钮，选择您想掌控的阵营：",
            chat_id=chat_id,
            message_id=state['rps_message'].message_id,
            reply_markup=KNS_MARKUP,
            parse_mode='Markdown'
        )
    except Exception as e:
         logging.error(f"RPS 胜利后编辑消息失败: {e}")

async def execute_battle(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """执行战斗结算逻辑 (完整实现请参考之前的代码)"""
    # 此处为占位符，请确保您的实际文件包含完整的逻辑
    state = game_states[chat_id]
    await context.bot.send_message(chat_id, "⚔️ **战斗结算占位符：** 双方出牌已记录，等待完整结算逻辑执行。", parse_mode='Markdown')
    # 假设战斗已结算，并启动下一个回合
    await start_new_turn(chat_id, context)

# --- IV. 命令处理函数 ---

async def rule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """回复规则主菜单，玩家点击按钮查看详情。"""
    
    # 无论在群聊还是私聊，都发送主菜单
    await update.message.reply_text(
        RULES_MAIN_MENU_TEXT,
        reply_markup=RULES_MAIN_KEYBOARD,
        parse_mode='Markdown'
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /start 命令，通常用于首次使用Bot时"""
    user_name = update.message.from_user.first_name
    await update.message.reply_text(
        f"👑 **欢迎，{user_name}！** ⛓️\n\n"
        "我是《王冠与锁链：秘闻录》的 Bot。\n"
        "请在一个群聊中输入 **/create** 来创建一场新的对决！\n"
        "输入 **/rule** 查看详细游戏规则。",
        parse_mode='Markdown'
    )


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /create 命令，用于创建新游戏"""
    
    chat_id = update.message.chat_id
    
    if chat_id > 0: # 检查是否在群聊中
        await update.message.reply_text("请在 **群聊** 中使用 /create 命令来开始游戏。")
        return

    if chat_id in game_states and game_states[chat_id]['status'] not in ['finished', 'error']:
        await update.message.reply_text("本群已有一场正在进行的对决，请先结束当前对局 (或输入 /endgame)。")
        return

    # 初始化游戏状态
    host_id = update.message.from_user.id
    host_name = update.message.from_user.first_name
    
    game_states[chat_id] = {
        'status': 'waiting_opponent',
        'host_id': host_id,
        'host_name': host_name,
        'opponent_id': None,
        'opponent_name': None,
        'rps_moves': {},
        'rps_winner_id': None,
        'winner_faction_choice': None,
        'opening_chooser_id': None,
        'game_type': None, # KingOpening / QueenOpening
        'current_turn': 0,
        'moves': {}, # 本回合出牌记录
    }

    join_keyboard = [[InlineKeyboardButton("⚔️ 点击加入对决！", callback_data='join_rps')]]
    join_markup = InlineKeyboardMarkup(join_keyboard)

    await update.message.reply_text(
        f"**🏆 新的对决已创建！**\n"
        f"发起人：**{host_name}**\n\n"
        "请另一位玩家点击下方按钮加入挑战！",
        reply_markup=join_markup,
        parse_mode='Markdown'
    )


async def endgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /endgame 命令，用于强制结束当前游戏"""
    
    chat_id = update.message.chat_id
    
    if chat_id in game_states and game_states[chat_id]['status'] != 'finished':
        # 允许任何人结束游戏，但最好是发起人/管理员
        del game_states[chat_id]
        
        await update.message.reply_text(
            "🛑 **游戏已强制结束。** 当前对决状态已清除。\n"
            "输入 /create 重新开始新的对决。",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("本群当前没有正在进行的对决。")

# --- V. Callback Query Handler (已修复 chat.type 错误) ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理所有 Inline 键盘点击 (已集成规则导航)"""
    
    query = update.callback_query

    user_id = query.from_user.id
    user_name = query.from_user.first_name
    data = query.data
    
    # 确定 group_id
    group_id = None
    if query.message:
        group_id = query.message.chat_id
    
    # 规则菜单导航逻辑 (rule_menu_*)
    if data.startswith('rule_menu_'):
        
        # 确保只有点击按钮的用户可以操作
        # 修复点: query.message.chat_type -> query.message.chat.type
        if query.message.chat.type == 'private' and query.message.chat_id != user_id: 
             await query.answer("请在 Bot 私聊中进行规则导航。", show_alert=True)
             return
             
        section = data.split('_')[-1]
        back_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ 返回规则主菜单", callback_data='rule_menu_main')]
        ])
        
        if section == 'victory':
            text = VICTORY_RULES_TEXT
        elif section == 'battle':
            text = BATTLE_RULES_TEXT
        elif section == 'cards':
            text = CARD_RULES_TEXT
        elif section == 'main':
            text = RULES_MAIN_MENU_TEXT
            markup = RULES_MAIN_KEYBOARD
        else:
            await query.answer("规则部分未找到。", show_alert=True)
            return

        # 如果是主菜单，使用主菜单键盘；否则使用返回按钮
        markup = RULES_MAIN_KEYBOARD if section == 'main' else back_button
        
        try:
            await query.edit_message_text(
                text,
                reply_markup=markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Failed to edit rule message: {e}")
            await query.answer("无法编辑消息，请重新发送 /rule 命令。", show_alert=True)
        
        return
    
    # --- 剩余游戏逻辑 ---
    
    # 1. 初始检查和通用/错误弹窗
    if group_id is None:
        try:
            await query.answer("游戏状态未找到或已结束。", show_alert=True)
        except Exception:
            pass
        return
        
    # 如果游戏已结束，只有 join_rps 是有效操作
    if group_id not in game_states or game_states[group_id].get('status') in ['finished', 'error'] and data not in ['join_rps']:
        try:
             await query.answer("游戏已结束或未开始，请发送 /create 重新开始。", show_alert=True)
        except Exception:
             pass
        return

    state = game_states[group_id]
    
    # 2. 特殊处理：发起人点击“加入对决” (join_rps)
    if data == 'join_rps':
        
        if state['status'] != 'waiting_opponent':
            await query.answer("游戏已开始或状态错误。", show_alert=True)
            return
        
        if user_id == state['host_id']:
            logging.info(f"Host ({user_name}) attempted to join their own game in chat {group_id}.")
            
            try:
                await query.answer("👑 您是游戏发起者 (Host)，请等待另一位玩家点击按钮加入！", show_alert=True)
            except Exception as e:
                logging.error(f"Failed to show alert for host trying to join: {e}. Falling back to group reply.")
                try:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=f"**👑 {user_name} (发起人)，请注意：** 您不能加入自己创建的挑战。请等待其他玩家点击加入。",
                        reply_to_message_id=query.message.message_id, 
                        parse_mode='Markdown'
                    )
                except Exception as e_reply:
                    logging.error(f"Failed to send fallback reply in chat {group_id}: {e_reply}")
            return
            
        if state['opponent_id'] is not None and user_id != state['opponent_id']:
            await query.answer("本局游戏对手已确定，无法加入。", show_alert=True)
            return

        # 正常加入逻辑：
        state['opponent_id'] = user_id
        state['opponent_name'] = user_name
        state['status'] = 'playing_rps'
        
        # 步骤 1：编辑 /create 消息，宣布对手
        try:
            await query.answer(f"成功加入！您将与 {state['host_name']} 对决。")
            
            await query.edit_message_text(
                f"⚔️ **游戏开始！** {state['host_name']} VS {state['opponent_name']}\n"
                "两位玩家请准备进行【剪刀石头布】争夺阵营选择权！",
                reply_markup=None,
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Failed to edit /create message upon join_rps in chat {group_id}: {e}")

        # 步骤 2：在群聊中发送 RPS 按钮
        try:
            state['rps_message'] = await context.bot.send_message( 
                 chat_id=group_id,
                 text="请两位玩家 **点击下方按钮** 出牌 (剪刀/石头/布)：",
                 reply_markup=RPS_MARKUP,
                 parse_mode='Markdown'
            )
        except Exception as e:
             logging.error(f"Failed to send RPS buttons in chat {group_id}. Check bot permissions! Error: {e}")
             await context.bot.send_message(group_id, "⚠️ **警告：** 无法发送 RPS 按钮，请检查 Bot 是否被禁言。")

        return

    # 【通用】非发起人、非 'join_rps' 按钮，先回答查询，防止卡顿
    try:
        if data not in ['join_rps']:
            await query.answer() 
    except Exception as e:
        logging.error(f"Failed to answer callback query in general section: {e}")

    # 3. 剪刀石头布 (rps_*) 逻辑
    if data.startswith('rps_'):
        
        if group_id == user_id:
            await query.answer("请在群聊中点击 RPS 按钮。", show_alert=True)
            return
        
        if user_id not in [state['host_id'], state['opponent_id']]:
            await query.answer("您未加入本局游戏。")  
            return
        if state['status'] != 'playing_rps':
            await query.answer("RPS 已经结束。")
            return
        if user_id in state['rps_moves']:
              await query.answer("您已经出牌了。等待对手...")
              return

        move = data.split('_')[1]
        state['rps_moves'][user_id] = move
        
        await query.answer(f"您已出牌: {move.upper()}。等待对手...")  
        
        p1_id = state['host_id']
        p1_name = state['host_name']
        p2_id = state['opponent_id']
        p2_name = state['opponent_name']
        
        p1_status = f"**{p1_name}**：✅ 已出牌" if p1_id in state['rps_moves'] else f"**{p1_name}**：⏳ 等待中"
        p2_status = f"**{p2_name}**：✅ 已出牌" if p2_id in state['rps_moves'] else f"**{p2_name}**：⏳ 等待中"
        
        updated_text = (
            f"**⚔️ 剪刀石头布：**\n\n"
            f"{p1_status}\n"
            f"{p2_status}\n\n"
            "请点击下方按钮出牌："
        )
        
        
        if len(state['rps_moves']) == 2:
            try:
                await context.bot.edit_message_text(
                     updated_text + "\n\n**结果即将宣布...**",
                     chat_id=group_id,
                     message_id=query.message.message_id, 
                     reply_markup=InlineKeyboardMarkup([]), 
                     parse_mode='Markdown'
                )
                await process_rps_winner(update, context) 
                return
            except Exception as e:
                logging.error(f"RPS 结算编辑消息失败: {e}")
        else:
             try:
                 await context.bot.edit_message_text(
                      updated_text,
                      chat_id=group_id,
                      message_id=query.message.message_id,
                      reply_markup=RPS_MARKUP,  
                      parse_mode='Markdown'
                  )
             except Exception as e:
                 logging.error(f"RPS 中途编辑消息失败: {e}")
                 
        return 
        
    # 4. 阵营选择 (kns_*) 逻辑
    if data.startswith('kns_'):
        
        winner_id = state.get('rps_winner_id')
        
        if user_id != winner_id:
              await query.answer("您没有赢得剪刀石头布，不能选择阵营！", show_alert=True)
              return
        if state['status'] != 'choosing_faction':
            await query.answer("您已经做出选择。")
            return

        winner_name = state['host_name'] if user_id == state['host_id'] else state['opponent_name']
        
        choice_faction = data.split('_')[1]  
        state['winner_faction_choice'] = choice_faction
        
        loser_id = state['host_id'] if winner_id == state['opponent_id'] else state['opponent_id']
        loser_name = state['host_name'] if winner_id == state['opponent_id'] else state['opponent_name']
        
        if choice_faction == 'King':
            await query.edit_message_text(
                f"👑 **{winner_name}** 选择了 **国王方 (King Faction)**。\n"
                "请选择本局的开局模式：",
                reply_markup=KING_OPENING_CHOICE_MARKUP,
                parse_mode='Markdown'
            )
            state['status'] = 'choosing_opening'
            state['opening_chooser_id'] = winner_id 
            
        elif choice_faction == 'Slave':
            state['status'] = 'choosing_opening'
            state['opening_chooser_id'] = loser_id 
            
            await query.edit_message_text(
                f"⛓️ **{winner_name}** 选择了 **奴隶方 (Slave Faction)**。\n"
                f"👑 **选择权已转移给 {loser_name} (国王方)！**\n"
                f"请 **{loser_name}** 点击按钮，选择国王方的开局模式：",
                reply_markup=KING_OPENING_CHOICE_MARKUP,
                parse_mode='Markdown'
            )
            
        return

    # 5. 开局模式选择 (select_opening_*) 逻辑
    if data.startswith('select_opening_'):
        
        chooser_id = state.get('opening_chooser_id')
        
        if user_id != chooser_id or state['status'] != 'choosing_opening':
              await query.answer("当前不是您的操作阶段。")
              return
              
        game_type = data.split('_')[2]  
        winner_id = state['rps_winner_id']
        
        winner_faction = state['winner_faction_choice']
        loser_faction = 'Slave' if winner_faction == 'King' else 'King'  
        loser_id = state['host_id'] if winner_id == state['opponent_id'] else state['opponent_id']
        
        if game_type not in ['KingOpening', 'QueenOpening']:
              await query.answer("请选择国王方的开局模式（King Opening 或 Queen Opening）。", show_alert=True)
              return

        state['game_type'] = game_type
        
        # --- 分配卡组 ---
        state[winner_id] = {
            'name': state['host_name'] if winner_id == state['host_id'] else state['opponent_name'],
            'faction': winner_faction,
            'hand': FACTION_DECKS.get(f'{game_type}_{winner_faction}', []).copy(),  
            'discard': [],
            'special_status': [],
            'last_played': None # 记录上一回合打出的卡牌，用于终极哨兵限制
        }
        state[loser_id] = {
            'name': state['host_name'] if loser_id == state['host_id'] else state['opponent_name'],
            'faction': loser_faction,
            'hand': FACTION_DECKS.get(f'{game_type}_{loser_faction}', []).copy(),
            'discard': [],
            'special_status': [],
            'last_played': None # 记录上一回合打出的卡牌，用于终极哨兵限制
        }
        
        # --- 公布结果并开始游戏 ---
        await query.edit_message_text(
            f"✅ **开局模式与阵营确定！**\n"
            f"本局模式：**『{game_type}』**\n\n"
            f"**{state[winner_id]['name']}** 获得 **{winner_faction} 方**！\n"
            f"**{state[loser_id]['name']}** 获得 **{loser_faction} 方**！\n\n"
            "正在私下分配卡牌，游戏即将开始！",
            parse_mode='Markdown',
            reply_markup=None  
        )
        
        state['current_turn'] = 0  
        await start_new_turn(group_id, context) 
        return
        
    # 6. 卡牌选择逻辑 (card_selected_*)
    if data.startswith('card_selected_'):
        
        if state['status'] != 'playing_turn':
            await query.answer("现在不是出牌阶段！", show_alert=True)
            return
            
        card_name = data.split('_')[2]  
        player_data = state[user_id]
        
        if user_id != query.message.chat_id:  
            await query.answer("请在Bot的私聊窗口中出牌！", show_alert=True)
            return
            
        if user_id in state['moves']:
              await query.answer(f"您本回合已经出牌『{state['moves'][user_id]}』，请等待对手。")
              return

        if card_name not in player_data['hand']:
            await query.answer(f"❌ {card_name} 不在您的手牌中！", show_alert=True)
            return
            
        # 终极哨兵不能连续打出，提前检查并弹窗
        if card_name == 'Ultimate Sentinel' and player_data.get('last_played') == 'Ultimate Sentinel':
            await query.answer("❌ 终极哨兵不能连续两个回合打出！请取消并选择其他卡牌。", show_alert=True)
            return
            
        emoji = CARD_EMOJIS.get(card_name, '❓')
        
        confirm_button = [
            [InlineKeyboardButton(f"✅ 确认出牌：{emoji} {card_name}", callback_data=f'confirm_play_{card_name}')],
            [InlineKeyboardButton("❌ 取消出牌，重新选择", callback_data='cancel_play')] 
        ]
        confirm_markup = InlineKeyboardMarkup(confirm_button)
        
        await query.edit_message_text(
            f"您选择了 **『{card_name}』**。确认出战吗？\n"
            f"当前手牌剩余：{player_data['hand'].count(card_name)} 张。",
            reply_markup=confirm_markup,
            parse_mode='Markdown'
        )
        await query.answer("请确认您的出牌。")
        return

    # 7. 确认出牌逻辑 (confirm_play_*)
    if data.startswith('confirm_play_'):
        
        if state['status'] != 'playing_turn':
            await query.answer("现在不是出牌阶段！", show_alert=True)
            return
            
        card_name = data.split('_')[2]  
        player_data = state[user_id]
        
        if card_name not in player_data['hand']:
            await query.answer(f"❌ {card_name} 不在您的手牌中！", show_alert=True)
            return
            
        if user_id in state['moves']:
              await query.answer(f"您本回合已经出牌『{state['moves'][user_id]}』，请等待对手。")
              return

        # 终极哨兵不能连续打出检查 - 再次防止跳过 card_selected
        if card_name == 'Ultimate Sentinel' and player_data.get('last_played') == 'Ultimate Sentinel':
            await query.answer("❌ 终极哨兵不能连续两个回合打出！", show_alert=True)
            return

        # 真正记录出牌，从手牌移除
        player_data['hand'].remove(card_name)
        state['moves'][user_id] = card_name
        
        # 记录本回合出牌，用于下一回合检查连续出牌限制
        player_data['last_played'] = card_name 
        
        emoji = CARD_EMOJIS.get(card_name, '❓')

        await query.answer(f"✅ 确认出牌：{card_name}！等待对手...")  
        
        # 步骤 1: 私聊显示出什么牌
        await query.edit_message_text(
            f"✅ **您已出牌：** {emoji} **『{card_name}』**。等待对手出牌...",  
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([]), 
        )
        
        # 步骤 2: 群聊通知 (只通知已出牌，但不暴露卡牌)
        group_message = f"**{user_name}** 已完成出牌！"
        await context.bot.send_message(
            chat_id=group_id,  
            text=group_message,
            parse_mode='Markdown'
        )
        
        # 步骤 3: 检查是否可以结算战斗
        if len(state['moves']) == 2:
            await asyncio.sleep(1)  
            await execute_battle(group_id, context) 
            return

    # 8. 取消出牌逻辑 (cancel_play)
    if data == 'cancel_play':
        
        if state['status'] != 'playing_turn':
            await query.answer("现在不是出牌阶段！", show_alert=True)
            return

        player_data = state[user_id]
        
        hand_buttons = generate_card_buttons(player_data['hand'])
        card_markup = InlineKeyboardMarkup(hand_buttons)
        
        await query.edit_message_text(
            f"⚔️ **回合 {state['current_turn']}：** 请重新选择出牌！\n\n"
            f"您当前的手牌：`{', '.join([f'{CARD_EMOJIS.get(c, "?")} {c}' for c in player_data['hand']])}`\n"
            f"**点击卡牌选择出战！**",
            reply_markup=card_markup,
            parse_mode='Markdown'
        )
        await query.answer("您已取消出牌，请重新选择。")
        return


# --- 主函数：启动 Bot ---
def main() -> None:
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
    except Exception as e:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"致命错误：Bot Token 无效或连接失败。错误信息: {e}")
        return

    # 注册 Handler
    application.add_handler(CommandHandler("start", start_command))    
    application.add_handler(CommandHandler("create", create_command))  
    application.add_handler(CommandHandler("endgame", endgame_command))  
    application.add_handler(CommandHandler("rule", rule_command))  
    application.add_handler(CallbackQueryHandler(button_handler))

    # 启动 Bot
    print("---------------------------------------")
    print("✅ 核心连接成功！《王冠与锁链：秘闻录》Bot 正在运行...")
    print("请在 Telegram 群聊中发送 /create 开始游戏，发送 /rule 查看规则。")
    print("按 Ctrl+C 停止 Bot。")
    print("---------------------------------------")
    
    try:
        application.run_polling(poll_interval=1)
    except Exception as e:
        print(f"致命的轮询错误: {e}")


if __name__ == '__main__':
    main()