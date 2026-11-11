"""
Terminal Dashboard renderer using Rich to mirror the Excel sheet layout from Screenshot 2.
"""
from typing import List, Dict, Any
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Group
from engine.matrix import PricingMatrix

def create_rich_grid(matrix: PricingMatrix, section: str = "current") -> Table:
    """
    Constructs a Rich Table mirroring the columns and rows of Screenshot 2.
    """
    table = Table(
        title=f"Dual Butterfly (PE-CE BTFLY) Pricing Matrix - [{'Current Expiry' if section == 'current' else 'Next Expiry (Nxt)'}]",
        title_style="bold yellow",
        show_header=True,
        header_style="bold cyan on #1a1a2e",
        border_style="bright_blue",
        padding=(0, 1)
    )

    table.add_column("Strike", justify="center", style="bold white on #252a34", width=8)

    combos = matrix.combos_current if section == "current" else matrix.combos_next

    for _, _, label in combos:
        # Two sub-columns per combo: BCmp and SCmp
        table.add_column(f"{label}\nBCmp", justify="right", style="bold red")
        table.add_column(f"{label}\nSCmp", justify="right", style="bold green")

    if section == "current":
        table.add_column("NIFTY - Str\nBuy", justify="right", style="bold magenta")
        table.add_column("1-2\nRatio", justify="right", style="bold yellow")

    rows = matrix.to_table_data(section=section)

    for r in rows:
        strike = r["Strike"]
        is_atm = r.get("is_atm", False)
        offset = r.get("offset_from_atm", 0)

        if is_atm:
            strike_val = f"[bold black on #fbbf24] {strike} ATM [/bold black on #fbbf24]"
        elif offset > 0:
            strike_val = f"[white]{strike}[/white] [dim]+{offset}[/dim]"
        else:
            strike_val = f"[white]{strike}[/white] [dim]{offset}[/dim]"

        row_vals = [strike_val]

        for _, _, label in combos:
            bcmp = r.get(f"{label}_BCmp", "-")
            scmp = r.get(f"{label}_SCmp", "-")

            bcmp_str = f"{bcmp:.2f}" if isinstance(bcmp, (int, float)) else str(bcmp)
            scmp_str = f"{scmp:.2f}" if isinstance(scmp, (int, float)) else str(scmp)

            row_vals.append(bcmp_str)
            row_vals.append(scmp_str)

        if section == "current":
            strd = r.get("Straddle", "-")
            ratio = r.get("1-2", "-")
            strd_str = f"{strd:.2f}" if isinstance(strd, (int, float)) else str(strd)
            ratio_str = f"{ratio:.2f}" if isinstance(ratio, (int, float)) else str(ratio)
            row_vals.append(strd_str)
            row_vals.append(ratio_str)

        if is_atm:
            table.add_row(*row_vals, style="bold on #1a2318")
        else:
            table.add_row(*row_vals)

    return table

def render_dashboard(matrix: PricingMatrix, spot: float = 0.0, feed_type: str = "Simulator", section: str = "current") -> Panel:
    grid = create_rich_grid(matrix, section=section)
    
    header_text = Text()
    header_text.append("FRACTAL CLIENT / EXCEL PRICING ENGINE  ", style="bold bright_green")
    header_text.append(f"|  Feed: {feed_type}  ", style="bold yellow")
    if spot > 0:
        header_text.append(f"|  NIFTY Spot: {spot:.2f}  ", style="bold bright_cyan")
    header_text.append(f"|  6-Leg PE-CE BTFLY Matrix ({section.upper()})", style="italic")

    group = Group(
        Panel(header_text, style="white on #0f172a"),
        grid
    )
    return Panel(group, border_style="green", expand=True)
