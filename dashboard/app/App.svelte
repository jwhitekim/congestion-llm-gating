<script>
  import { onMount } from 'svelte';
  import { sessions, selectedSession } from './lib/stores.js';
  import { fetchSessions } from './lib/api.js';
  import SessionList from './lib/SessionList.svelte';
  import SessionDetail from './lib/SessionDetail.svelte';

  let loading = $state(true);
  let error = $state('');

  onMount(async () => {
    try {
      sessions.set(await fetchSessions());
    } catch (e) {
      error = `세션 목록을 불러오는 중 오류가 발생했습니다: ${e.message}`;
    } finally {
      loading = false;
    }
  });
</script>

<main>
  <h1>실내 혼잡도 모니터링</h1>

  {#if loading}
    <p>불러오는 중...</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if $selectedSession === null}
    <SessionList />
  {:else}
    {#key $selectedSession.session_id}
      <SessionDetail session={$selectedSession} />
    {/key}
  {/if}
</main>
