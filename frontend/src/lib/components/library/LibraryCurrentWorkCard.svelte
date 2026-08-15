<script lang="ts">
	import { ArrowRight, CircleCheck, Clock3, Radio } from 'lucide-svelte';
	import { onMount } from 'svelte';

	import { authStore } from '$lib/stores/authStore.svelte';
	import { getLibraryActivityQuery } from '$lib/queries/library/LibraryActivityQueries.svelte';
	import type { LibraryWorkItem } from '$lib/queries/library/LibraryOperationsTypes';
	import LibraryWorkIcon from './LibraryWorkIcon.svelte';
	import LibraryWorkProgress from './LibraryWorkProgress.svelte';
	import {
		libraryWorkContext,
		libraryWorkEffect,
		libraryWorkFacts,
		libraryWorkHref,
		libraryWorkTitle
	} from './LibraryWorkPresentation';

	const activityQuery = getLibraryActivityQuery(() => authStore.user?.id);
	let now = $state(Date.now() / 1000);

	onMount(() => {
		const timer = window.setInterval(() => (now = Date.now() / 1000), 60_000);
		return () => window.clearInterval(timer);
	});

	const items = $derived(activityQuery.data?.work_items ?? []);
	const primary = $derived(items[0] ?? null);
	const additional = $derived(items.slice(1));
	const facts = $derived(primary ? libraryWorkFacts(primary) : []);
	const steps = $derived(primary && primary.effect !== 'attention' ? workSteps(primary) : []);

	function duration(timestamp: number | null): string {
		if (!timestamp) return 'just now';
		const seconds = Math.max(0, now - timestamp);
		if (seconds < 60) return 'just now';
		if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
		return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m ago`;
	}

	function timing(item: LibraryWorkItem): string {
		if (item.state === 'failed') return `Failed ${duration(item.failure_at ?? item.updated_at)}`;
		if (item.state === 'paused') return `Paused ${duration(item.updated_at)}`;
		if (item.state === 'queued' || !item.started_at) return 'Waiting to start';
		const seconds = Math.max(0, now - item.started_at);
		if (seconds < 60) return 'Started just now';
		if (seconds < 3600) return `Running for ${Math.floor(seconds / 60)}m`;
		return `Running for ${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
	}

	function workSteps(item: LibraryWorkItem): Array<{ label: string; state: string }> {
		let labels: string[];
		let active = 0;
		if (item.kind === 'scan') {
			labels = ['Find files', 'Read metadata', 'Finalize catalog'];
			active = item.phase === 'reconciling' ? 2 : item.phase === 'indexing' ? 1 : 0;
		} else if (item.kind === 'library_management' && item.effect === 'file_writing') {
			labels = ['Snapshot', 'Stage', 'Validate', 'Publish', 'Catalog', 'Clean up'];
			active =
				{
					preparing_snapshots: 0,
					writing_staged_files: 1,
					validating_staged_files: 2,
					publishing_files: 3,
					committing_catalog: 4,
					cleaning_up: 5
				}[item.phase ?? ''] ?? 0;
		} else if (item.kind === 'library_management') {
			labels = ['Count scope', 'Inspect files', 'Seal preview'];
			active = item.processed > 0 ? 1 : 0;
		} else {
			labels = ['Queue', 'Check evidence', 'Prepare result'];
			active = item.state === 'queued' ? 0 : 1;
		}
		return labels.map((label, index) => ({
			label,
			state: index < active ? 'complete' : index === active ? 'current' : 'pending'
		}));
	}
</script>

<section
	class="library-current-work"
	data-effect={primary?.effect ?? 'idle'}
	aria-label="Current library work"
>
	{#if activityQuery.isLoading}
		<div class="skeleton h-36 rounded-[inherit]"></div>
	{:else if activityQuery.isError}
		<div class="library-current-work__idle" role="status">
			<span class="library-current-work__mark"><Radio class="h-5 w-5" /></span>
			<div>
				<h3 id="current-work-title">Current work is unavailable</h3>
				<p>The detailed controls below remain available.</p>
			</div>
		</div>
	{:else if !primary}
		<div class="library-current-work__idle">
			<span class="library-current-work__mark"><CircleCheck class="h-5 w-5" /></span>
			<div>
				<p class="library-current-work__eyebrow">Current work</p>
				<h3 id="current-work-title">No library work is running</h3>
				<p>Start a scan, prepare identities, or preview file changes below.</p>
			</div>
		</div>
	{:else}
		<div class="library-current-work__body">
			<header class="library-current-work__header">
				<span class="library-current-work__mark"><LibraryWorkIcon item={primary} /></span>
				<div class="min-w-0 flex-1">
					<p class="library-current-work__eyebrow">
						<Radio class="h-3 w-3" />
						{primary.effect === 'attention' ? 'Needs attention' : 'Current work'}
					</p>
					<h3 id="current-work-title">{libraryWorkTitle(primary)}</h3>
					<div class="library-current-work__meta">
						{#if primary.effect !== 'attention'}<span>{libraryWorkEffect(primary)}</span>{/if}
						<span><Clock3 class="h-3.5 w-3.5" /> {timing(primary)}</span>
						{#if libraryWorkContext(primary)}<span>{libraryWorkContext(primary)}</span>{/if}
					</div>
				</div>
				<a class="btn btn-ghost btn-sm" href={libraryWorkHref(primary)}>
					Open details <ArrowRight class="h-4 w-4" />
				</a>
			</header>

			<LibraryWorkProgress item={primary} />

			{#if steps.length}
				<ol class="library-current-work__steps" aria-label="Operation phases">
					{#each steps as step (step.label)}
						<li data-state={step.state}><span></span><small>{step.label}</small></li>
					{/each}
				</ol>
			{/if}

			{#if facts.length}
				<div class="library-current-work__facts" aria-label="Current work details">
					{#each facts as fact (fact)}<span>{fact}</span>{/each}
				</div>
			{/if}

			{#if additional.length}
				<div class="library-current-work__queue">
					<p>{additional.length} other {additional.length === 1 ? 'task' : 'tasks'}</p>
					{#each additional as item (item.id)}
						<a href={libraryWorkHref(item)}>
							<LibraryWorkIcon {item} className="h-4 w-4" />
							<span
								><strong>{libraryWorkTitle(item)}</strong><small>{libraryWorkEffect(item)}</small
								></span
							>
							<ArrowRight class="h-4 w-4" />
						</a>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</section>
