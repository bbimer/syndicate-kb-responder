"""Unit economics scaler for retail leads ($500–$2,000).

Scales institutional $10,000 baseline tables down to the lead's estimated deposit
($1,000 / $1,500), strips $100,000 whale columns, and preserves invariant percentages.
"""

from __future__ import annotations
import re
from typing import Union, Optional


def resolve_target_deposit(deposit_est: Optional[Union[str, int, float]]) -> float:
    """Resolve target deposit from lead profile string or number."""
    if not deposit_est:
        return 1000.0
    
    if isinstance(deposit_est, (int, float)):
        return float(deposit_est) if deposit_est > 0 else 1000.0
    
    clean = str(deposit_est).strip().lower()
    if clean == "500_2000":
        return 1000.0
    elif clean == "1000_2000":
        return 1500.0
    elif "50k" in clean:
        return 10000.0
    
    # Try to extract numbers from string like "1000", "$1,500", "500-2000"
    num_match = re.search(r'[\d,]+(?:\.\d+)?', clean)
    if num_match:
        try:
            val = float(num_match.group(0).replace(',', ''))
            return val if val > 0 else 1000.0
        except ValueError:
            pass
            
    return 1000.0


def _scale_dollar_value(val_str: str, ratio: float) -> str:
    """Scales a single dollar amount while preserving signs, bolding, and formatting."""
    def repl(m: re.Match) -> str:
        prefix = m.group(1)  # e.g. '+$', '-$', '$', '**+$'
        raw_num = m.group(2).replace(',', '')
        if not raw_num:
            return m.group(0)
        try:
            num = float(raw_num)
        except ValueError:
            return m.group(0)

        # Don't scale small constants like $0 or $1-$4
        if num < 5.0:
            return m.group(0)
        
        scaled = num * ratio
        if scaled.is_integer() or scaled >= 100.0:
            scaled_str = f"{int(round(scaled)):,}"
        elif scaled >= 10.0:
            scaled_str = f"{scaled:,.1f}"
        else:
            scaled_str = f"{scaled:,.2f}"
            
        suffix = m.group(3) if m.group(3) else ""
        return f"{prefix}{scaled_str}{suffix}"

    pattern = re.compile(r'(\*{0,2}[+-]?\$)(\d[\d,]*(?:\.\d+)?)(\*{0,2})')
    return pattern.sub(repl, val_str)


def scale_markdown_table(table_text: str, target_deposit: float = 1000.0, base_deposit: float = 10000.0) -> str:
    """Scales a markdown table from $10,000 base down to target deposit,

    stripping $100,000 columns when present.
    """
    ratio = target_deposit / base_deposit
    lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return table_text

    # Parse header cells
    header_raw = lines[0]
    header_cells = [c.strip() for c in header_raw.split('|')[1:-1]]

    # Identify columns to drop (e.g. $100,000 whale columns)
    drop_indices = set()
    for idx, cell in enumerate(header_cells):
        if re.search(r'\$100[,.]?000', cell):
            drop_indices.add(idx)

    # Process all rows
    processed_rows = []
    for line_idx, line in enumerate(lines):
        cells = [c.strip() for c in line.split('|')[1:-1]]
        
        # Filter dropped columns
        kept_cells = [cell for idx, cell in enumerate(cells) if idx not in drop_indices]
        
        if line_idx == 0:
            # Header line: replace $10,000 with scaled deposit
            scaled_header = []
            for cell in kept_cells:
                new_cell = re.sub(r'\$10[,.]?000', f"${int(target_deposit):,}", cell)
                scaled_header.append(new_cell)
            processed_rows.append("| " + " | ".join(scaled_header) + " |")
        elif line_idx == 1:
            # Separator line
            processed_rows.append("| " + " | ".join(kept_cells) + " |")
        else:
            # Data line: scale dollar amounts in kept cells
            scaled_data = []
            for cell in kept_cells:
                scaled_data.append(_scale_dollar_value(cell, ratio))
            processed_rows.append("| " + " | ".join(scaled_data) + " |")

    return "\n".join(processed_rows)


def scale_unit_econ_text(text: str, deposit_est: Optional[Union[str, int, float]] = "500_2000") -> str:
    """Processes Layer 4 content: scales markdown tables and text references."""
    target_deposit = resolve_target_deposit(deposit_est)
    ratio = target_deposit / 10000.0

    # Replace headers like "Unit-экономика на чеки $10,000 и $100,000"
    out = re.sub(
        r'на\s+чеки?\s+\$10[,.]?000\s*(?:и\s+\$100[,.]?000)?',
        f'на чек ${int(target_deposit):,}',
        text,
        flags=re.I
    )

    # Find and scale markdown tables
    table_pattern = re.compile(r'(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)')
    def table_repl(match: re.Match) -> str:
        return scale_markdown_table(match.group(0), target_deposit=target_deposit, base_deposit=10000.0)

    out = table_pattern.sub(table_repl, out)
    return out
