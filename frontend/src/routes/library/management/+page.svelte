<script lang="ts">
	import {
		ArrowLeft,
		FolderCog,
		History,
		ScanSearch,
		Settings2,
		SlidersHorizontal
	} from 'lucide-svelte';

	import PageHeader from '$lib/components/PageHeader.svelte';
	import LibraryOperationsPanel from '$lib/components/library/LibraryOperationsPanel.svelte';
	import SettingsLibraryManagement from '$lib/components/settings/SettingsLibraryManagement.svelte';
	import { getLibraryActivityQuery } from '$lib/queries/library/LibraryActivityQueries.svelte';
	import { getTargetLibrarySettingsQuery } from '$lib/queries/library/LibraryPolicyQueries.svelte';
	import { authStore } from '$lib/stores/authStore.svelte';
	import { onMount } from 'svelte';

	const settingsQuery = getTargetLibrarySettingsQuery(() => authStore.isAdmin);
	const activityQuery = getLibraryActivityQuery(() => authStore.user?.id);
	const roots = $derived(settingsQuery.data?.library_roots ?? []);
	const policyRevision = $derived(settingsQuery.data?.policy_revision ?? '');
	const workItems = $derived(activityQuery.data?.work_items ?? []);
	const scanWork = $derived(
		workItems.find((item) => item.kind === 'scan' || item.kind === 'identification') ?? null
	);
	const managementWork = $derived(
		workItems.find((item) => item.kind === 'library_management' || item.kind === 'recovery') ?? null
	);
	const overviewBadge = $derived(
		workItems.length ? `${workItems.length} ${workItems.length === 1 ? 'task' : 'tasks'}` : null
	);
	const scanBadge = $derived.by(() => {
		if (!scanWork) return null;
		if (scanWork.effect === 'attention') return 'Needs attention';
		if (scanWork.remaining_count !== null) return `${scanWork.remaining_count} left`;
		if (scanWork.total && !scanWork.indeterminate) {
			return `${Math.min(100, Math.round((scanWork.processed / scanWork.total) * 100))}%`;
		}
		return scanWork.state === 'queued' ? 'Queued' : 'Running';
	});
	const managementBadge = $derived.by(() => {
		if (!managementWork) return null;
		if (managementWork.effect === 'attention') return 'Needs attention';
		if (managementWork.effect === 'file_writing') return 'Writing';
		return managementWork.state === 'queued' ? 'Queued' : 'Previewing';
	});
	const workspaceSectionIds = [
		'operations',
		'scanning-controls',
		'management-controls',
		'management-settings'
	] as const;
	type WorkspaceSectionId = (typeof workspaceSectionIds)[number];

	let activeSectionId = $state<WorkspaceSectionId>('operations');
	let jumpNav: HTMLElement;
	let scrollFrame: number | null = null;
	let navFrame: number | null = null;

	function setActiveSection(sectionId: WorkspaceSectionId): void {
		if (activeSectionId === sectionId) return;
		activeSectionId = sectionId;
		if (navFrame !== null) cancelAnimationFrame(navFrame);
		navFrame = requestAnimationFrame(() => {
			navFrame = null;
			const link = jumpNav?.querySelector<HTMLAnchorElement>(`a[href="#${sectionId}"]`);
			if (!link) return;
			const leftEdge = jumpNav.scrollLeft + 8;
			const rightEdge = jumpNav.scrollLeft + jumpNav.clientWidth - 8;
			const linkLeft = link.offsetLeft;
			const linkRight = linkLeft + link.offsetWidth;
			if (linkLeft >= leftEdge && linkRight <= rightEdge) return;
			jumpNav.scrollTo({
				left:
					linkLeft < leftEdge
						? Math.max(0, linkLeft - 8)
						: Math.max(0, linkRight - jumpNav.clientWidth + 8),
				behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
			});
		});
	}

	function updateActiveSection(): void {
		scrollFrame = null;
		const stickyMarker = (jumpNav?.getBoundingClientRect().bottom ?? 140) + 12;
		let nextSection: WorkspaceSectionId = 'operations';
		for (const sectionId of workspaceSectionIds) {
			const section = document.getElementById(sectionId);
			if (!section) continue;
			const scrollMarginTop = Number.parseFloat(getComputedStyle(section).scrollMarginTop) || 0;
			const marker = Math.max(stickyMarker, scrollMarginTop);
			if (section.getBoundingClientRect().top <= marker) nextSection = sectionId;
			else break;
		}
		setActiveSection(nextSection);
	}

	function scheduleActiveSectionUpdate(): void {
		if (scrollFrame !== null) return;
		scrollFrame = requestAnimationFrame(updateActiveSection);
	}

	function revealHashTarget(hash = window.location.hash): void {
		const runner = new URL(window.location.href).searchParams.get('runner');
		const sectionId =
			hash === '#identity-readiness' || hash === '#management-controls'
				? 'management-controls'
				: hash === '#scanning-controls'
					? 'scanning-controls'
					: hash === '#management-settings'
						? 'management-settings'
						: runner === 'manage' || runner === 'baseline_restore'
							? 'management-controls'
							: null;
		const section = sectionId ? document.getElementById(sectionId) : null;
		if (section instanceof HTMLDetailsElement) section.open = true;
		if (sectionId) setActiveSection(sectionId);
		requestAnimationFrame(() => {
			const targetId = hash.startsWith('#') ? hash.slice(1) : sectionId;
			if (!targetId) return;
			const target = document.getElementById(targetId);
			if (target instanceof HTMLElement) {
				target.scrollIntoView({
					behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
						? 'auto'
						: 'smooth',
					block: 'start'
				});
				const focusTarget =
					target instanceof HTMLDetailsElement
						? target.querySelector<HTMLElement>(':scope > summary')
						: target;
				focusTarget?.focus({ preventScroll: true });
			}
		});
	}

	function handleHashNavigation(event: MouseEvent): void {
		if (
			event.defaultPrevented ||
			event.button !== 0 ||
			event.metaKey ||
			event.ctrlKey ||
			event.shiftKey ||
			event.altKey ||
			!(event.target instanceof Element)
		)
			return;
		const link = event.target.closest<HTMLAnchorElement>('a[href^="#"]');
		if (!link) return;
		const hash = new URL(link.href).hash;
		if (!hash) return;
		event.preventDefault();
		if (window.location.hash !== hash) window.history.pushState(null, '', hash);
		revealHashTarget(hash);
	}

	onMount(() => {
		const handleHashChange = (): void => revealHashTarget();
		revealHashTarget();
		scheduleActiveSectionUpdate();
		window.addEventListener('hashchange', handleHashChange);
		window.addEventListener('scroll', scheduleActiveSectionUpdate, { passive: true });
		window.addEventListener('resize', scheduleActiveSectionUpdate);
		document.addEventListener('toggle', scheduleActiveSectionUpdate, true);
		return () => {
			window.removeEventListener('hashchange', handleHashChange);
			window.removeEventListener('scroll', scheduleActiveSectionUpdate);
			window.removeEventListener('resize', scheduleActiveSectionUpdate);
			document.removeEventListener('toggle', scheduleActiveSectionUpdate, true);
			if (scrollFrame !== null) cancelAnimationFrame(scrollFrame);
			if (navFrame !== null) cancelAnimationFrame(navFrame);
		};
	});
</script>

<svelte:head><title>Library Management · DroppedNeedle</title></svelte:head>
<svelte:window onclick={handleHashNavigation} />

<div class="min-h-[calc(100vh-200px)]">
	<PageHeader
		subtitle="Administrator controls for catalog scanning and optional, destructive file organisation."
		gradientClass="bg-gradient-to-br from-primary/25 via-base-100 to-warning/15"
	>
		{#snippet title()}Library Management{/snippet}
		{#snippet actions()}
			<a href="/library" class="btn btn-ghost btn-sm gap-2 rounded-full sm:btn-md">
				<ArrowLeft class="h-4 w-4" />
				<span class="hidden sm:inline">Back to Library</span>
				<span class="sm:hidden">Library</span>
			</a>
		{/snippet}
	</PageHeader>

	<main class="space-y-8 px-4 pb-14 sm:px-6 lg:px-8">
		<nav
			bind:this={jumpNav}
			class="library-management-jump-nav"
			aria-label="Library Management sections"
		>
			<a
				href="#operations"
				aria-current={activeSectionId === 'operations' ? 'location' : undefined}
			>
				<SlidersHorizontal class="h-4 w-4" />
				<span>Overview</span>
				{#if overviewBadge}<small class="library-work-nav-badge">{overviewBadge}</small>{/if}
			</a>
			<a
				href="#scanning-controls"
				data-tone="scan"
				aria-current={activeSectionId === 'scanning-controls' ? 'location' : undefined}
			>
				<ScanSearch class="h-4 w-4" />
				<span>Scan &amp; identify</span>
				{#if scanBadge}<small class="library-work-nav-badge">{scanBadge}</small>{/if}
			</a>
			<a
				href="#management-controls"
				data-tone="manage"
				aria-current={activeSectionId === 'management-controls' ? 'location' : undefined}
			>
				<FolderCog class="h-4 w-4" />
				<span>Manage files</span>
				{#if managementBadge}<small class="library-work-nav-badge">{managementBadge}</small>{/if}
			</a>
			<a
				href="#management-settings"
				data-tone="manage"
				aria-current={activeSectionId === 'management-settings' ? 'location' : undefined}
			>
				<Settings2 class="h-4 w-4" />
				<span>Profiles &amp; automation</span>
			</a>
			<a href="/library/management/history">
				<History class="h-4 w-4" />
				<span>History</span>
			</a>
		</nav>

		<LibraryOperationsPanel />

		<details
			id="management-settings"
			tabindex="-1"
			role="region"
			open
			class="library-detail-section scroll-mt-36"
			aria-labelledby="management-settings-summary-title"
		>
			<summary class="library-detail-summary">
				<span
					><strong id="management-settings-summary-title">Profiles &amp; automation</strong><small
						>Profiles, defaults, root assignments, triggers, retention, and advanced safety settings</small
					></span
				>
			</summary>
			<div class="space-y-4 p-4 sm:p-6">
				<div>
					<p class="font-mono text-xs uppercase tracking-[0.18em] text-library-manage/80">
						Configuration
					</p>
					<h2 id="management-configuration-title" class="font-display text-2xl font-bold">
						Profiles &amp; automation
					</h2>
					<p class="mt-1 max-w-2xl text-sm text-base-content/55">
						Define exactly what may change, then assign and activate those rules one library root at
						a time.
					</p>
				</div>

				{#if settingsQuery.isLoading}
					<div class="space-y-3">
						<div class="skeleton h-32 rounded-box"></div>
						<div class="skeleton h-64 rounded-box"></div>
					</div>
				{:else if settingsQuery.isError}
					<div class="alert alert-error">Could not load Library Management configuration.</div>
				{:else}
					<SettingsLibraryManagement {roots} {policyRevision} />
				{/if}
			</div>
		</details>
	</main>
</div>
