import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.constants import ParseMode
import google.generativeai as genai
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY, CHECK_INTERVAL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

KWORK_URLS = [
    "https://kwork.ru/projects?c=41",
    "https://kwork.ru/projects?c=17",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

seen_ids: set = set()

def parse_projects(html):
    soup = BeautifulSoup(html, "html.parser")
    projects = []
    for card in soup.select(".project-card, .wants-card, [data-id]"):
        pid = card.get("data-id") or card.get("id", "")
        title_el = card.select_one(".wants-card__header-title, .project-card__title, h2 a")
        desc_el = card.select_one(".wants-card__description, .project-card__description")
        budget_el = card.select_one(".wants-card__price, .project-card__price, .price")
        link_el = card.select_one("a[href]")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        desc = desc_el.get_text(strip=True) if desc_el else ""
        budget = budget_el.get_text(strip=True) if budget_el else "не указан"
        href = link_el["href"] if link_el else ""
        link = f"https://kwork.ru{href}" if href.startswith("/") else href
        projects.append({"id": pid or title[:30], "title": title, "desc": desc, "budget": budget, "link": link})
    return projects

def analyze_project(project):
    prompt = f"""Ты помощник UX/UI дизайнера и контент-маркетолога на фрилансе.

Проект с Кворка:
Название: {project['title']}
Описание: {project['desc']}
Бюджет клиента: {project['budget']}

Задача:
1. Оцени релевантность (0-10). Если меньше 5 — напиши только "нерелевантно".
2. Если релевантно — напиши живой отклик от лица Екатерины (опытный UX/UI дизайнер и контент-маркетолог, работает в сфере медицинской мебели и оборудования).
3. Предложи цену в рублях.

Формат:
РЕЛЕВАНТНОСТЬ: [цифра]/10
ЦЕНА: [сумма] ₽
ОТКЛИК:
[текст]"""
    response = model.generate_content(prompt)
    return response.text

async def check_and_notify():
    bot = Bot(token=TELEGRAM_TOKEN)
    async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        for url in KWORK_URLS:
            try:
                r = await client.get(url)
                projects = parse_projects(r.text)
                logger.info(f"Найдено проектов: {len(projects)}")
                for p in projects:
                    if p["id"] in seen_ids:
                        continue
                    seen_ids.add(p["id"])
                    analysis = analyze_project(p)
                    if "нерелевантно" in analysis.lower():
                        continue
                    msg = (f"🆕 *Новый проект*\n*{p['title']}*\n"
                           f"💰 Бюджет: {p['budget']}\n"
                           f"🔗 [Открыть]({p['link']})\n\n{analysis}")
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg[:4096],
                                           parse_mode=ParseMode.MARKDOWN,
                                           disable_web_page_preview=True)
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Ошибка: {e}")

async def main():
    logger.info("Бот запущен ✅")
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ Кворк-помощник запущен!")
    while True:
        await check_and_notify()
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
