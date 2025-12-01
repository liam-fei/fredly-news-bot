# =============================================
# Fredly Daily News Telegram Auto TTS - Replit Cloud
# English ~20 min, casual conversation style
# Fully automatic daily at 07:00 Dubai time
# =============================================

import feedparser
from openai import OpenAI
from telegram.ext import Application
import schedule
import time
from pathlib import Path
from datetime import datetime, timedelta
import requests
import asyncio
import os   # ← 这行必须在最上面

# ========== 改这里！用环境变量读取密钥 ==========
# ---------------- CONFIG ----------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# 多个RSS源，覆盖政治、经济、娱乐、科技、体育
RSS_FEEDS = {
    '综合新闻': [
        'http://feeds.bbci.co.uk/news/rss.xml',  # BBC
        'http://rss.cnn.com/rss/edition.rss',  # CNN
        'https://www.theguardian.com/world/rss',  # The Guardian
    ],
    '商业经济': [
        'https://feeds.bloomberg.com/markets/news.rss',  # Bloomberg
        'https://www.cnbc.com/id/100003114/device/rss/rss.html',  # CNBC
    ],
    '科技': [
        'https://techcrunch.com/feed/',  # TechCrunch
        'https://www.wired.com/feed/rss',  # Wired
    ],
    '娱乐': [
        'https://variety.com/feed/',  # Variety
        'https://www.hollywoodreporter.com/feed/',  # Hollywood Reporter
    ],
    '体育': [
        'https://www.espn.com/espn/rss/news',  # ESPN
    ]
}

OUTPUT_DIR = Path('./outputs')
OUTPUT_DIR.mkdir(exist_ok=True)
TARGET_MINUTES = 20  # target approx 20 minutes audio
ARTICLES_PER_CATEGORY = 5  # 每个类别获取5篇文章

client = OpenAI(api_key=OPENAI_API_KEY)
# 增加Telegram超时设置，处理大文件上传
from telegram.request import HTTPXRequest
request = HTTPXRequest(
    connection_pool_size=8,
    read_timeout=60.0,  # 60秒读取超时
    write_timeout=60.0,  # 60秒写入超时
    connect_timeout=30.0  # 30秒连接超时
)
application = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()

# ---------------- HELPERS ----------------

def fetch_latest_articles():
    """从多个RSS源获取文章，覆盖各个领域"""
    all_articles = []
    
    for category, feeds in RSS_FEEDS.items():
        print(f'\n📂 获取【{category}】新闻...')
        category_articles = []
        
        for feed_url in feeds:
            try:
                d = feedparser.parse(feed_url)
                if d.entries:
                    # 获取该feed的前几篇文章
                    for entry in d.entries[:ARTICLES_PER_CATEGORY]:
                        category_articles.append({
                            'category': category,
                            'title': entry.get('title', ''),
                            'link': entry.get('link', ''),
                            'summary': entry.get('summary', entry.get('description', ''))[:500]  # 限制摘要长度
                        })
                    print(f'  ✅ 获取 {min(len(d.entries), ARTICLES_PER_CATEGORY)} 篇')
            except Exception as e:
                print(f'  ⚠️  跳过一个源: {str(e)[:50]}')
                continue
        
        # 限制每个类别的文章数
        all_articles.extend(category_articles[:ARTICLES_PER_CATEGORY])
    
    print(f'\n📊 总共获取 {len(all_articles)} 篇文章')
    return all_articles


def build_prompt(entries):
    prompt = f"""You are Sara, a professional English female news anchor delivering a {TARGET_MINUTES}-minute daily news briefing. Please start with: "Good morning, this is Sara with your Fredly Daily Briefing for {datetime.now().strftime('%B %d, %Y')}." 

IMPORTANT INSTRUCTIONS:
- DO NOT include transition sounds, music descriptions, or sound effects (like "transition sound", "upbeat music", etc.)
- Focus on NEWS CONTENT ONLY
- Use natural, smooth transitions between topics with simple phrases like "Moving on to...", "In other news...", "Next up..."
- Deliver in a clear, engaging conversational tone
- Cover politics, business, technology, entertainment, and sports
- Target length: approximately {TARGET_MINUTES} minutes when read aloud at natural pace

Here are today's stories organized by category:

"""
    
    # 按类别组织文章
    categories = {}
    for article in entries:
        cat = article.get('category', '其他')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(article)
    
    # 构建分类内容
    for category, articles in categories.items():
        prompt += f"\n【{category}】\n"
        for i, article in enumerate(articles, 1):
            prompt += f"{i}. {article['title']}\n   {article['summary']}\n\n"
    
    prompt += f"""\nNow compose a complete {TARGET_MINUTES}-minute news script covering all these stories. 
- Start with a brief greeting
- Cover each major story with enough detail
- NO sound effects or music cues
- Use simple transitions
- End with a brief sign-off
- Make it exactly around {TARGET_MINUTES} minutes when read aloud"""
    
    return prompt


def generate_script(prompt):
    resp = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": "You are a professional news anchor. Write clear, engaging news scripts WITHOUT any sound effects, music cues, or production notes. Focus purely on the news content and natural spoken transitions."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=6000  # 增加token限制以生成更长内容
    )
    content = resp.choices[0].message.content
    return content.strip() if content else ""


def generate_tts(script_text, out_path: Path):
    # Using OpenAI TTS endpoint (gpt-4o-mini-tts)
    headers = {'Authorization': f'Bearer {OPENAI_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': 'gpt-4o-mini-tts', 'voice': 'shimmer', 'input': script_text}
    r = requests.post('https://api.openai.com/v1/audio/speech', headers=headers, json=payload, stream=True)
    if r.status_code == 200:
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return out_path
    else:
        raise RuntimeError(f'TTS failed: {r.status_code} {r.text}')


async def send_to_telegram_async(mp3_path: Path):
    try:
        async with application:
            await application.initialize()
            with open(mp3_path, 'rb') as f:
                await application.bot.send_audio(
                    chat_id=CHAT_ID, 
                    audio=f, 
                    caption=f'Fredly Daily Briefing - {datetime.now().strftime("%Y-%m-%d")}'
                )
            print(f'✅ Audio sent successfully to chat {CHAT_ID}')
    except Exception as e:
        print(f'❌ Failed to send to Telegram: {e}')
        print('提示：请确保你已经在Telegram中启动了与机器人的对话')
        print(f'1. 在Telegram中搜索你的bot')
        print(f'2. 点击"Start"或发送 /start')
        raise

def send_to_telegram(mp3_path: Path):
    asyncio.run(send_to_telegram_async(mp3_path))

# ---------------- MAIN FLOW ----------------

def run_daily_briefing():
    try:
        print(f'\n{"="*60}')
        print(f'[{datetime.now()}] 开始每日新闻播报流程')
        print(f'{"="*60}')
        
        print('\n📰 正在获取最新文章...')
        entries = fetch_latest_articles()
        if not entries:
            print('⚠️  未找到文章，所有RSS源都无法访问')
            return

        print(f'✅ 成功获取 {len(entries)} 篇文章（覆盖多个领域）')
        
        prompt = build_prompt(entries)
        print('\n🤖 正在生成新闻脚本...')
        script_text = generate_script(prompt)
        print(f'✅ 脚本生成完成（约 {len(script_text)} 字符）')

        date_str = datetime.now().strftime('%Y-%m-%d')
        mp3_path = OUTPUT_DIR / f'fredly_briefing_{date_str}.mp3'

        print('\n🎙️  正在生成TTS音频...')
        generate_tts(script_text, mp3_path)
        print(f'✅ 音频文件已生成: {mp3_path}')

        print('\n📤 正在发送到Telegram...')
        send_to_telegram(mp3_path)
        
        print(f'\n{"="*60}')
        print('✅ 每日播报完成！')
        print(f'{"="*60}\n')
    except Exception as e:
        print(f'\n❌ 播报过程出错: {e}')
        import traceback
        traceback.print_exc()

# ---------------- SCHEDULER ----------------
schedule.every().day.at("03:00").do(run_daily_briefing)

# ========== 启动 Flask + 首次运行 + 定时循环 ==========
from keep_alive import keep_alive
keep_alive()

# 启动信息（只打印一次）
print("\n" + "="*60)
print("Fredly Daily News Bot 已启动！")
print("⏰ 每天迪拜时间 07:00 自动播报")
print("🔄 后台运行中... (日志已静默)")
print("="*60 + "\n")

# 可选：测试时运行一次
if os.getenv("RUN_ON_START", "false").lower() == "true":
    print("测试模式：立即运行一次播报...")
    run_daily_briefing()

# 进入后台循环（不再 print）
while True:
    schedule.run_pending()
    time.sleep(60)
