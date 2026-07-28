<script>
  import { onMount, onDestroy } from 'svelte';
  import { Chart } from 'chart.js/auto';
  import { selectedSession } from './stores.js';
  import { fetchSessionMeta, fetchResultsEntries } from './api.js';

  let { session } = $props();

  let meta = $state(null);
  let entries = $state([]);
  let loadError = $state('');

  let lastModified = null;
  let pollId = null;

  let seriesCanvas = $state();
  let latencyCanvas = $state();
  let seriesChart = null;
  let latencyChart = null;

  const TRIGGER_LABELS = { surge: 'surge', stagnation: 'stagnation', hotspot: 'hotspot', conflict: 'conflict' };
  const LEVEL_LABELS = { low: 'low', medium: 'medium', high: 'high' };

  // 차트는 canvas라 CSS 변수를 직접 못 읽는다 — 렌더 시점에 실제 계산값을
  // 읽어와야 다크모드 전환에도 데이터/신호 색 토큰이 그대로 따라간다.
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // ── 레벨 분포 요약 ──
  let levelCounts = $derived.by(() => {
    const counts = { low: 0, medium: 0, high: 0 };
    for (const e of entries) {
      const lvl = e.aggregated?.level;
      if (lvl in counts) counts[lvl] += 1;
    }
    return counts;
  });
  let levelTotal = $derived(levelCounts.low + levelCounts.medium + levelCounts.high);

  function pct(n, total) {
    return total ? (100 * n) / total : 0;
  }

  // ── 동적 임계값: 가장 최근 세그먼트에 실제로 적용된 값(entries는 시간순) ──
  let latestThresholds = $derived(
    entries.length ? entries[entries.length - 1].dynamic_thresholds : null
  );

  function fmtNum(v, digits = 1) {
    return typeof v === 'number' ? v.toFixed(digits) : '-';
  }

  // ── 파생 통계 (카드 4개) ──
  let totalSegments = $derived(entries.length);
  let llmCallEntries = $derived(entries.filter((e) => e.agent !== null && e.agent !== undefined));
  let llmCallCount = $derived(llmCallEntries.length);
  let latencies = $derived(
    llmCallEntries
      .map((e) => e.agent.agent_elapsed_sec)
      .filter((v) => typeof v === 'number')
  );
  let avgLatency = $derived(
    latencies.length ? latencies.reduce((a, b) => a + b, 0) / latencies.length : null
  );
  let p95Latency = $derived(percentile(latencies, 0.95));
  let latestEntry = $derived(entries.length ? entries[entries.length - 1] : null);
  let activeTriggers = $derived(
    Object.keys(TRIGGER_LABELS).filter((type) => entries.some((e) => e.trigger === type))
  );
  let llmCallRate = $derived(totalSegments ? llmCallCount / totalSegments : null);

  function percentile(values, p) {
    if (values.length === 0) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const idx = Math.min(sorted.length - 1, Math.floor(p * sorted.length));
    return sorted[idx];
  }

  function fmtSec(v) {
    return typeof v === 'number' ? `${v.toFixed(3)}s` : '-';
  }

  function fmtPct(v) {
    return typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '-';
  }

  async function loadAll() {
    try {
      meta = await fetchSessionMeta(session.session_id);
      entries = await fetchResultsEntries(session.session_id);
      lastModified = meta.results_mtime_ms;
      loadError = '';
      renderCharts();
      if (!meta.ended_at) startPolling();
    } catch (e) {
      loadError = `데이터를 읽는 중 오류가 발생했습니다: ${e.message}`;
    }
  }

  async function pollTick() {
    try {
      const freshMeta = await fetchSessionMeta(session.session_id);
      if (freshMeta.results_mtime_ms !== lastModified) {
        lastModified = freshMeta.results_mtime_ms;
        entries = await fetchResultsEntries(session.session_id);
        renderCharts();
      }
      meta = freshMeta;
      if (freshMeta.ended_at) {
        stopPolling();
      }
    } catch (e) {
      loadError = `데이터를 읽는 중 오류가 발생했습니다: ${e.message}`;
    }
  }

  function startPolling() {
    stopPolling();
    pollId = setInterval(pollTick, 1000);
  }

  function stopPolling() {
    if (pollId !== null) {
      clearInterval(pollId);
      pollId = null;
    }
  }

  function renderCharts() {
    renderSeriesChart();
    renderLatencyChart();
  }

  function renderSeriesChart() {
    if (!seriesCanvas) return;

    const inkColor = cssVar('--text-h');
    const mutedColor = cssVar('--text-muted');

    const densityPoints = entries.map((e) => ({ x: e.timestamp, y: e.perception.density }));
    const speedPoints = entries.map((e) => ({ x: e.timestamp, y: e.perception.avg_speed }));
    // density/avg_speed는 level·trigger가 아닌 원값이라 색이 아니라 명암(잉크색 vs
    // 뮤트 회색) + 점선으로만 구분한다 — 이 대시보드에서 색은 신호(level/trigger)
    // 전용으로 예약돼 있다.
    const triggerDatasets = Object.keys(TRIGGER_LABELS).map((type) => {
      const color = cssVar(`--trigger-${type}`);
      return {
        label: TRIGGER_LABELS[type],
        type: 'scatter',
        data: entries
          .filter((e) => e.trigger === type)
          .map((e) => ({ x: e.timestamp, y: e.perception.density })),
        backgroundColor: color,
        borderColor: color,
        pointStyle: 'triangle',
        pointRadius: 7,
        pointHoverRadius: 9,
        showLine: false,
        yAxisID: 'yDensity',
      };
    });

    const data = {
      datasets: [
        {
          label: 'density',
          data: densityPoints,
          borderColor: inkColor,
          backgroundColor: inkColor,
          yAxisID: 'yDensity',
          tension: 0.2,
          pointRadius: 2,
        },
        {
          label: 'avg_speed',
          data: speedPoints,
          borderColor: mutedColor,
          backgroundColor: mutedColor,
          borderDash: [4, 3],
          yAxisID: 'ySpeed',
          tension: 0.2,
          pointRadius: 2,
        },
        ...triggerDatasets,
      ],
    };

    if (seriesChart) {
      seriesChart.data = data;
      seriesChart.update();
      return;
    }

    seriesChart = new Chart(seriesCanvas, {
      type: 'line',
      data,
      options: {
        parsing: false,
        animation: false,
        scales: {
          x: { type: 'linear', title: { display: true, text: 'timestamp (s)' } },
          yDensity: { type: 'linear', position: 'left', title: { display: true, text: 'density' } },
          ySpeed: {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'avg_speed (px/s)' },
            grid: { drawOnChartArea: false },
          },
        },
        plugins: { legend: { position: 'bottom' } },
      },
    });
  }

  function renderLatencyChart() {
    if (!latencyCanvas) return;

    const inkColor = cssVar('--text-h');
    const points = llmCallEntries
      .filter((e) => typeof e.agent.agent_elapsed_sec === 'number')
      .map((e) => ({ x: e.timestamp, y: e.agent.agent_elapsed_sec }));

    const data = {
      datasets: [
        {
          label: 'LLM latency',
          data: points,
          borderColor: inkColor,
          backgroundColor: inkColor,
          tension: 0.2,
          pointRadius: 3,
        },
      ],
    };

    if (latencyChart) {
      latencyChart.data = data;
      latencyChart.update();
      return;
    }

    latencyChart = new Chart(latencyCanvas, {
      type: 'line',
      data,
      options: {
        parsing: false,
        animation: false,
        scales: {
          x: { type: 'linear', title: { display: true, text: 'timestamp (s)' } },
          y: { type: 'linear', title: { display: true, text: 'latency (sec)' } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  function goBack() {
    selectedSession.set(null);
  }

  onMount(() => {
    loadAll();
  });

  onDestroy(() => {
    stopPolling();
    seriesChart?.destroy();
    latencyChart?.destroy();
  });
</script>

<div class="toolbar">
  <button class="secondary" onclick={goBack}>목록으로</button>
  {#if meta && !meta.ended_at}
    <span class="badge running"><span class="status-dot"></span>실행 중 · 1초 자동 갱신</span>
  {/if}
</div>

{#if loadError}
  <p class="error">{loadError}</p>
{/if}

{#if meta}
  <section class="session-hero">
    <div class="session-title-block">
      <span class="eyebrow">Session</span>
      <h2>{meta.session_id}</h2>
      <p class="video-path">{meta.video_path}</p>
    </div>
  </section>

  <section class="overview-grid">
    <div class="summary-panel">
      <div class="cards">
        <div class="card">
          <div class="card-label">총 세그먼트</div>
          <div class="card-value">{totalSegments}</div>
        </div>
        <div class="card">
          <div class="card-label">LLM 호출</div>
          <div class="card-value">{llmCallCount}</div>
        </div>
        <div class="card">
          <div class="card-label">호출 비율</div>
          <div class="card-value">{fmtPct(llmCallRate)}</div>
        </div>
        <div class="card">
          <div class="card-label">평균 latency</div>
          <div class="card-value">{fmtSec(avgLatency)}</div>
        </div>
        <div class="card">
          <div class="card-label">p95 latency</div>
          <div class="card-value">{fmtSec(p95Latency)}</div>
        </div>
        <div class="card">
          <div class="card-label">마지막 timestamp</div>
          <div class="card-value">{fmtNum(latestEntry?.timestamp, 1)}</div>
        </div>
      </div>
    </div>

    <aside class="side-panel">
      <div class="level-distribution">
        <h3>규칙 기반 level 분포</h3>
        {#if levelTotal > 0}
          <div class="level-bar">
            {#each Object.keys(LEVEL_LABELS) as lvl}
              {#if levelCounts[lvl] > 0}
                <div
                  class="level-bar-segment {lvl}"
                  style="width: {pct(levelCounts[lvl], levelTotal)}%"
                  title="{lvl}: {levelCounts[lvl]}개 ({pct(levelCounts[lvl], levelTotal).toFixed(1)}%)"
                ></div>
              {/if}
            {/each}
          </div>
          <div class="level-legend">
            {#each Object.keys(LEVEL_LABELS) as lvl}
              <div class="level-legend-item">
                <span class="level-legend-dot {lvl}"></span>
                <span>{lvl}</span>
                <span class="level-legend-count">{levelCounts[lvl]}</span>
                <span class="level-legend-pct">({pct(levelCounts[lvl], levelTotal).toFixed(1)}%)</span>
              </div>
            {/each}
          </div>
        {:else}
          <p class="video-path">데이터 없음</p>
        {/if}
      </div>

      <div class="trigger-panel">
        <h3>활성 트리거</h3>
        <div class="trigger-stack">
          {#if activeTriggers.length > 0}
            {#each activeTriggers as type}
              <span class="badge-trigger {type}">{type}</span>
            {/each}
          {:else}
            <span class="badge-none">-</span>
          {/if}
        </div>
      </div>

      {#if latestThresholds}
        <div class="threshold-panel">
          <h3>최근 임계값</h3>
          <span class="threshold-source {latestThresholds.source}">
            {latestThresholds.source === 'percentile' ? 'percentile' : 'fallback'}
          </span>
          <div class="threshold-values">
            <span><span class="label">density_low</span>{fmtNum(latestThresholds.density_low)}</span>
            <span><span class="label">density_high</span>{fmtNum(latestThresholds.density_high)}</span>
            <span><span class="label">zone_max</span>{fmtNum(latestThresholds.zone_max)}</span>
            <span><span class="label">sample_count</span>{latestThresholds.sample_count}</span>
          </div>
        </div>
      {/if}
    </aside>
  </section>

  <section class="analysis-grid">
    <div class="chart-card wide">
      <div class="section-head">
        <h3>밀도 · 속도 시계열</h3>
        <span>trigger marker</span>
      </div>
      <div class="chart-wrap">
        <canvas bind:this={seriesCanvas}></canvas>
      </div>
    </div>

    <div class="chart-card">
      <div class="section-head">
        <h3>LLM latency</h3>
        <span>{latencies.length} calls</span>
      </div>
      <div class="chart-wrap">
        <canvas bind:this={latencyCanvas}></canvas>
      </div>
    </div>
  </section>

  <div class="section-head table-head">
    <h3>세그먼트 로그</h3>
    <span>{entries.length} rows</span>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>timestamp</th>
          <th>level</th>
          <th>trigger</th>
          <th>co_triggered</th>
          <th>trigger_reason</th>
          <th>assessment</th>
          <th>action</th>
          <th>LLM latency (s)</th>
          <th>기록된 API 응답 수</th>
        </tr>
      </thead>
      <tbody>
        {#each entries as e (e.timestamp)}
          <tr>
            <td>{e.timestamp}</td>
            <td>
              {#if e.aggregated?.level}
                <span class="badge-level {e.aggregated.level}">{e.aggregated.level}</span>
              {:else}
                <span class="badge-none">-</span>
              {/if}
            </td>
            <td>
              {#if e.trigger}
                <span class="badge-trigger {e.trigger}">{e.trigger}</span>
              {:else}
                <span class="badge-none">-</span>
              {/if}
            </td>
            <td class="co-triggered-cell">
              {#if e.co_triggered && e.co_triggered.length > 0}
                {#each e.co_triggered as t}
                  <span class="badge-trigger chip {t}">{t}</span>
                {/each}
              {:else}
                <span class="badge-none">-</span>
              {/if}
            </td>
            <td class="trigger-reason-cell" title={e.trigger_reason ?? ''}>
              {e.trigger_reason ?? '-'}
            </td>
            <td>{e.agent?.assessment ?? '-'}</td>
            <td>{e.agent?.action ?? '-'}</td>
            <td>{e.agent?.agent_elapsed_sec ?? '-'}</td>
            <td>{e.agent?.api_round_trips ?? '-'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
