import asyncio
import json
import time
from typing import List, Dict, Any
from src.retrieval.fts_router import FTSRouter
from src.generator.deepseek_client import DeepSeekClient
from config.settings import settings

CASES = [
    {
        "id": 1,
        "type": "hook",
        "author": "@F",
        "chat": "КРИПТОНАВТ | Чат",
        "module": "M04_ORDERBOOK_EXECUTION",
        "quote": "Меня в тайгере бесит медленная загрузка графиков. Чтоб несколько монет промониторить надо прямо ждать сидеть",
        "theme": "Лаги терминала TigerTrade, сетевые задержки и ручной мониторинг"
    },
    {
        "id": 2,
        "type": "hook",
        "author": "@oohh_wlad",
        "chat": "КРИПТОНАВТ | Чат",
        "module": "M02_EXCHANGE_MM",
        "quote": "Нужно было стоп за лой поставить \nВыбило🥺",
        "theme": "Выбивание стопов маркет-мейкером, ловля ликвидности за локальными экстремумами"
    },
    {
        "id": 3,
        "type": "hook",
        "author": "@glebkascalp",
        "chat": "КРИПТОНАВТ | Чат",
        "module": "M04_ORDERBOOK_EXECUTION",
        "quote": "Махи руками на этой мете рынка не помогают (((",
        "theme": "Бессилие ручного скальпинга в текущей институциональной мете алгоритмов"
    },
    {
        "id": 4,
        "type": "hook",
        "author": "@willfalcon",
        "chat": "КРИПТОНАВТ | Чат",
        "module": "M01_TOKENOMICS_MEV",
        "quote": "Завтра по ней разлок,клифф ддя инвесторов, аккуратнее",
        "theme": "Предупреждение о клиффе и дампе фондов (согласие + институциональное усиление)"
    },
    {
        "id": 5,
        "type": "hook",
        "author": "@glebkascalp",
        "chat": "КРИПТОНАВТ | Чат",
        "module": "M02_EXCHANGE_MM",
        "quote": "отскок взял,перехай не стал ждать бо боюсь дядей в стакане",
        "theme": "Страх крупных игроков/ММ в стакане, фейковые плотности и спуфинг"
    },
    {
        "id": 6,
        "type": "hook",
        "author": "@F",
        "chat": "КРИПТОНАВТ | Чат",
        "module": "M07_QUANT_STACK",
        "quote": "Стопы. Фомо. Это всё дестабилизирует. Нет смысла в этом состоянии торговать. Я вот пока не нашёл способа для переключения",
        "theme": "Психологическое выгорание, тильт, череда стопов и поиск системного выхода"
    },
    {
        "id": 7,
        "type": "hook",
        "author": "@nedozabanen",
        "chat": "КРИПТОНАВТ | Чат",
        "module": "M02_EXCHANGE_MM",
        "quote": "в одного трудно будет трейдинг нагнуть, надо команду искать, это стопицот процентов, сами убедились наверное - пару лет назад было проще",
        "theme": "Одиночный трейдинг против институционалов, усложнение рынка"
    },
    {
        "id": 8,
        "type": "shield",
        "stage": "In_DM",
        "author": "Реальный лид в ЛС",
        "module": "M04_ORDERBOOK_EXECUTION",
        "quote": "Привет! Видел твой ответ в чате. А сколько стоит ваш софт и как его подключить к бирже?",
        "theme": "Запрос на покупку/подключение HFT-софта (стадия In_DM: квалификация, ноль упоминаний $20)"
    },
    {
        "id": 9,
        "type": "shield",
        "stage": "Legend_&_Media",
        "author": "Реальный лид в ЛС",
        "module": "M01_TOKENOMICS_MEV",
        "quote": "Слушай, если это реально дает стабильный спред 1.5–3%, почему вы сами весь объем не крутите, а делитесь в чатах?",
        "theme": "Сомнение в мотивации делиться связкой (ферма iPhone, Secure Enclave, лимит 4 круга, рефка)"
    },
    {
        "id": 10,
        "type": "shield",
        "stage": "Test_20",
        "author": "Реальный лид в ЛС",
        "module": "M03_DERIVATIVES_FUNDING",
        "quote": "Звучит логично, но кругом столько скама. Вдруг я заведу эти 20 баксов и их просто уведут?",
        "theme": "Страх потери средств на микро-тесте (свой Bybit/OKX, своя 2FA, 10 минут, +$0.70 чистыми)"
    }
]

async def main():
    router = FTSRouter(settings.db_path)
    client = DeepSeekClient()
    results = []

    print(f"Starting generation of 10 reference cases using DeepSeek v4.1 with prefix caching...")
    total_cost = 0.0

    for c in CASES:
        t0 = time.perf_counter()
        context = router.retrieve_context(c["quote"], module=c.get("module"), deposit_est="500_2000")
        
        if c["type"] == "hook":
            res = await client.generate_hook(c["quote"], context)
        else:
            res = await client.generate_shield(c["quote"], context, stage=c["stage"], deposit_est="500_2000")

        elapsed = time.perf_counter() - t0
        total_cost += res.cost_usd

        item = {
            "id": c["id"],
            "type": c["type"],
            "author": c["author"],
            "chat": c.get("chat", "ЛС"),
            "stage": c.get("stage", "Public_Chat"),
            "theme": c["theme"],
            "module": c.get("module"),
            "quote": c["quote"],
            "response": res.text,
            "telemetry": {
                "prompt_tokens": res.prompt_tokens,
                "cached_tokens": res.cached_tokens,
                "completion_tokens": res.completion_tokens,
                "cost_usd": res.cost_usd,
                "latency_sec": res.latency_sec
            }
        }
        results.append(item)
        print(f"[{c['id']}/10] {c['type'].upper()} ({c['author']}) - Tokens: {res.completion_tokens} | Cost: ${res.cost_usd:.5f} | Latency: {res.latency_sec:.2f}s | Cached: {res.cached_tokens}")
        # small delay to prevent rate limits
        await asyncio.sleep(0.5)

    with open("reference_10_responses.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nAll 10 reference cases generated successfully! Total Cost: ${total_cost:.5f}")

if __name__ == "__main__":
    asyncio.run(main())
