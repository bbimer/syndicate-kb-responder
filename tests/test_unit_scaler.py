import pytest
from src.indexer.unit_econ_scaler import (
    resolve_target_deposit,
    scale_markdown_table,
    scale_unit_econ_text,
)


def test_resolve_target_deposit():
    assert resolve_target_deposit("500_2000") == 1000.0
    assert resolve_target_deposit("1000_2000") == 1500.0
    assert resolve_target_deposit("50k_plus") == 10000.0
    assert resolve_target_deposit("2000") == 2000.0
    assert resolve_target_deposit(750) == 750.0
    assert resolve_target_deposit(None) == 1000.0


def test_scale_markdown_table_drop_whale():
    sample_table = (
        "| Статья расходов / Доходность | Чек $10,000 (Ритейл LP v3) | Чек $10,000 (Syndicate) | Чек $100,000 (Ритейл LP v3) | Чек $100,000 (Syndicate) |\n"
        "| :--- | :--- | :--- | :--- | :--- |\n"
        "| **Комиссионный доход (Gross Fee)** | +$1,250 (12.5%) | +$550 (5.5% Maker Rebate) | +$12,500 (12.5%) | +$5,500 (Maker Rebate) |\n"
        "| **Сбор фандинга / Дельта-доход** | $0.00 | +$1,850 (Funding 18.5%) | $0.00 | +$18,500 (Funding) |\n"
        "| **Убыток LVR / Impermanent Loss** | -$2,400 (-24.0%) | **$0.00 (Дельта = 0)** | -$24,000 (-24.0%) | **$0.00 (Дельта = 0)** |\n"
    )

    scaled = scale_markdown_table(sample_table, target_deposit=1000.0, base_deposit=10000.0)

    # Check that $100,000 columns are dropped
    assert "$100,000" not in scaled
    # Check that $10,000 header became $1,000
    assert "Чек $1,000 (Ритейл LP v3)" in scaled
    assert "Чек $1,000 (Syndicate)" in scaled
    # Check that values are scaled by 0.1
    assert "+$125 (12.5%)" in scaled
    assert "+$55 (5.5% Maker Rebate)" in scaled
    assert "+$185 (Funding 18.5%)" in scaled
    assert "-$240 (-24.0%)" in scaled
    assert "$0.00" in scaled
    # Percentages remain invariant
    assert "12.5%" in scaled
    assert "18.5%" in scaled
    assert "-24.0%" in scaled


def test_scale_unit_econ_text():
    text = (
        "### 1.4. Unit-экономика на чеки $10,000 и $100,000\n"
        "Сравнение удержания позиции розничным LP против дельта-нейтрального алгоритма:\n\n"
        "| Параметр | Чек $10,000 | Чек $100,000 |\n"
        "| :--- | :--- | :--- |\n"
        "| Профит | +$2,000 | +$20,000 |\n"
    )

    res = scale_unit_econ_text(text, deposit_est="1000_2000")
    assert "Unit-экономика на чек $1,500" in res
    assert "$100,000" not in res
    assert "Чек $1,500" in res
    assert "+$300" in res  # $2000 * (1500/10000) = $300
