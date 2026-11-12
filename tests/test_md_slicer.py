import os
import sqlite3
import pytest
from pathlib import Path
from src.indexer.md_ast_slicer import KnowledgeBaseIndexer


SAMPLE_MODULE_M01 = """
## ВВЕДЕНИЕ: УНИВЕРСАЛЬНОЕ ОРУЖИЕ КЛОУЗЕРА
Вводный текст...

## РАЗДЕЛ I: АРХИТЕКТУРА L1 И СТАНДАРТ ТОКЕНОВ (EIP-20)
### 1.1. МЕТАФОРА: Переводчик на человеческий
Метафора ячейки в банке...

### 1.2. КЕЙС: Анатомия EIP-20
Институциональный прецедент кражи токенов...

### 1.3. ТЕХНИЧЕСКИЙ ПРУФ: Сравнительный анализ
```solidity
contract BadCode { function exploit() public {} }
```
Текст пруфа...

### 1.4. UNIT-ЭКОНОМИКА: Числовой расчет
Таблица потерь ритейла:
| Чек $10,000 | Чек $100,000 |
| +$1,000 | +$10,000 |

### 1.5. ТЕХНИЧЕСКИЙ ПРУФ: Пре-флайт симуляция
```python
def simulate(): pass
```

### 1.6. СКРИПТ ЗАКРЫТИЯ: Боевой скрипт закрытия
#### Вектор А (Розница / чек $1k–$5k): Разрушение иллюзии
* **Слова менеджера:** Вы говорите, что смарт-контракт надежен?
#### Вектор Б (Фонд): Институциональный заход
* **Слова менеджера:** Для крупных чеков...

## РАЗДЕЛ VI: ПСИХОЛОГИЯ КЛИЕНТА, UNIT-ЭКОНОМИКА И КАТАЛОГ БОЕВЫХ КАРТОЧЕК
#### Боевая карточка 1: «У проекта официальный аудит, смарт-контракт абсолютно безопасен»
* **Суть ответа:** Аудиторы CertiK проверяли и Luna.
* **Скрипт клоузера:** Показываем эксплойт.

#### Боевая карточка 2: «Скоро разлок монет, команда готовит памп»
* **Суть ответа:** Анлок давит на стакан.

## РАЗДЕЛ VII: ИНСТИТУЦИОНАЛЬНЫЙ ГЛОССАРИЙ ТЕРМИНОВ
1. **Approve Race Condition:** Уязвимость двойного списания.
   - *Инвариант:* Детерминированная атака.
2. **Depeg Risk:** Риск потери паритета.

## РАЗДЕЛ VIII: АНАЛИТИЧЕСКИЕ ДОСЬЕ ПЕРВИЧНЫХ ИСТОЧНИКОВ
Мусорные транскрипты YouTube, которые должны быть вырезаны...
"""

SAMPLE_MODULE_M02 = """
## РАЗДЕЛ I: АРХИТЕКТУРА МАТЧИНГА
### 1.1. Метафора & Интуиция: Стакан против пула
Объяснение инварианта...

### 1.2. Институциональный прецедент: FTX
История краха...

### 1.3. Технический пруф: Модель Авелланеды
```cpp
void match() {}
```

### 1.4. Unit-экономика на чеки $10,000 и $100,000
| Чек $10,000 | Чек $100,000 |

### 1.5. Боевой скрипт закрытия
* **Клиент:** Зачем мне софт?
* **Клоузер:** Потому что LP сливает 80% депозита.

## РАЗДЕЛ VI: БОЕВОЙ АРСЕНАЛ ВОЗРАЖЕНИЙ
### КАРТОЧКА 1: «Маркет-мейкеры обеспечивают ликвидность»
* **Суть ответа:** ММ защищают только себя.

## РАЗДЕЛ VII: ИНЖЕНЕРНЫЙ ГЛОССАРИЙ
1. **CLOB:** Централизованная книга заявок.

## РАЗДЕЛ VIII: SOURCE DOSSIERS
YouTube transcripts to discard...
"""

SAMPLE_CLOSER = """
# БОЕВОЙ ПЛЕЙБУК КЛОУЗЕРА
## МОДУЛЬ 4. БОЕВЫЕ ОТВЕТЫ НА ГЛАВНЫЕ ВОЗРАЖЕНИЯ (СМЫСЛОВАЯ БАЗА)

* **«Зачем тебе делиться со мной, если у тебя есть и капитал, и ферма?»**  
  *Суть ответа:* Мой основной капитал ($50k+) лежит в дельта-нейтрале...
* **«Почему ты не наделаешь 50 профилей в антидетекте AdsPower?»**  
  *Суть ответа:* Браузерный антидетект палится нативным iOS App Attest...
"""


def test_parse_module_and_strip_tech_proof(tmp_path):
    db_file = tmp_path / "test_kb.db"
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    
    m01_file = kb_dir / "M01.md"
    m01_file.write_text(SAMPLE_MODULE_M01, encoding="utf-8")
    
    indexer = KnowledgeBaseIndexer(db_file, kb_dir)
    indexer.init_db()
    
    c, b, g = indexer.parse_module_file(m01_file, "M01")
    assert c == 1  # Section I
    assert b == 2  # Battlecards 1 and 2
    assert g == 2  # Glossary 1 and 2

    # Check that Section VIII was excluded
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT clean_text FROM chapters WHERE module = 'M01'")
    clean_text = cur.fetchone()[0]
    
    # Layer 3 (solidity code and python code) should be stripped
    assert "contract BadCode" not in clean_text
    assert "def simulate" not in clean_text
    assert "Мусорные транскрипты" not in clean_text
    
    # Layer 1, 2, 4, and Vector A from Layer 5 should be present
    assert "Метафора ячейки в банке" in clean_text
    assert "Институциональный прецедент кражи" in clean_text
    assert "Таблица потерь ритейла" in clean_text
    assert "Вектор А" in clean_text
    # Vector B is deprioritized
    assert "Вектор Б" not in clean_text
    conn.close()


def test_parse_m02_card_format(tmp_path):
    db_file = tmp_path / "test_kb.db"
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    
    m02_file = kb_dir / "M02.md"
    m02_file.write_text(SAMPLE_MODULE_M02, encoding="utf-8")
    
    indexer = KnowledgeBaseIndexer(db_file, kb_dir)
    indexer.init_db()
    
    c, b, g = indexer.parse_module_file(m02_file, "M02")
    assert c == 1
    assert b == 1
    assert g == 1

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT objection, answer FROM battlecards WHERE module = 'M02'")
    row = cur.fetchone()
    assert row[0] == "Маркет-мейкеры обеспечивают ликвидность"
    assert "ММ защищают только себя" in row[1]
    conn.close()


def test_parse_closer_playbook(tmp_path):
    db_file = tmp_path / "test_kb.db"
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    
    closer_file = kb_dir / "M01_Fast_Track_Closer.md"
    closer_file.write_text(SAMPLE_CLOSER, encoding="utf-8")
    
    indexer = KnowledgeBaseIndexer(db_file, kb_dir)
    indexer.init_db()
    
    cnt = indexer.parse_closer_playbook(closer_file)
    assert cnt == 2

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT card_num, objection, answer FROM battlecards WHERE module = 'FAST_TRACK'")
    rows = cur.fetchall()
    assert len(rows) == 2
    assert "AdsPower" in rows[1][1]
    assert "App Attest" in rows[1][2]
    conn.close()
