"""
파이프라인 결과를 터미널에 단계별로 출력한다.
터미널 출력(사람용)과 results.jsonl(분석용)은 분리한다.
"""

from typing import Optional
from rich.console import Console
from rich.rule import Rule

from datatypes import PerceptionResult

console = Console()


def report_segment(
    result: PerceptionResult,
    trigger_name: Optional[str],
    trigger_reason: Optional[str],
    level: str,
    agent_output: Optional[dict],
) -> None:
    ts = f"{int(result.timestamp // 60):02d}:{int(result.timestamp % 60):02d}"
    console.print(Rule(f"[bold]{ts}[/bold]", style="dim"))

    # PERCEPTION
    zones = "  ".join(f"{z}={n}" for z, n in result.zone_counts.items())
    console.print(
        f" [bold cyan]PERCEPTION[/bold cyan]  "
        f"total=[bold]{result.total}[/bold]  "
        f"density=[bold]{result.density:.0f}[/bold]  "
        f"avg_speed={result.avg_speed:.2f}"
    )
    console.print(f"            zones: {zones}")

    # TRIGGER — level은 trigger/rules.py가 매 세그먼트 계산하는 규칙 기반 값이라
    # 트리거 발생 여부와 무관하게 항상 노출한다.
    if trigger_name:
        console.print(
            f" [bold yellow]TRIGGER    [/bold yellow]"
            f" [yellow]{trigger_name}[/yellow] ({trigger_reason})  level=[bold]{level}[/bold]"
        )
    else:
        # 미선택은 객관적 정상 라벨이 아니다. 논문에서도 미선택 299개 중
        # 105개가 강제 평가 시 caution/anomaly로 출력됐다.
        console.print(f" [bold dim]TRIGGER    [/bold dim] — (미선택)  level=[bold]{level}[/bold]")

    # 선택적 LLM 판정 단계와 호출 생략 여부를 표시한다.
    if agent_output:
        console.print(
            f" [bold magenta]LLM        [/bold magenta]"
            f" 호출됨 (트리거: {trigger_name})"
        )
        assess     = agent_output.get("assessment", "?")
        reasoning  = (agent_output.get("reasoning") or "")[:80]
        judgment   = agent_output.get("congestion_level", "?")
        action     = agent_output.get("action", "?")
        console.print(f'   [dim]├ assess   {assess} — "{reasoning}"[/dim]')
        console.print(f"   [dim]├ judgment {judgment}[/dim]")
        console.print(f"   [dim]└ action   {action}[/dim]")
    else:
        console.print(f" [bold dim]LLM        [/bold dim] skip")

    console.print()
