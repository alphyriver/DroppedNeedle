<script lang="ts">
	import {
		AlertTriangle,
		ArrowRight,
		BookOpenCheck,
		CircleCheck,
		FolderCog,
		ScanSearch,
		ShieldCheck
	} from 'lucide-svelte';

	import { authStore } from '$lib/stores/authStore.svelte';
	import { getLibraryActivityQuery } from '$lib/queries/library/LibraryActivityQueries.svelte';
	import { requestLibraryRun } from '$lib/queries/library/LibraryOperationMutations.svelte';
	import {
		getCurrentLibraryRunsQuery,
		getLibraryRunHistoryQuery
	} from '$lib/queries/library/LibraryOperationQueries.svelte';
	import { getTargetLibrarySettingsQuery } from '$lib/queries/library/LibraryPolicyQueries.svelte';
	import {
		getLibraryScanScheduleQuery,
		getLibraryStatsQuery
	} from '$lib/queries/library/LibraryQueries.svelte';
	import {
		getLibraryIdentityPreparationEstimateQuery,
		getLibraryIdentityPreparationsQuery
	} from '$lib/queries/library/LibraryIdentityPreparationQueries.svelte';
	import {
		getLibraryManagementOperationsQuery,
		getLibraryManagementRecoveryQuery,
		getLibraryManagementSettingsQuery
	} from '$lib/queries/library-management/LibraryManagementQueries.svelte';

	const activityQuery = getLibraryActivityQuery(() => authStore.user?.id);
	const runsQuery = getCurrentLibraryRunsQuery(() => authStore.isAdmin);
	const runHistoryQuery = getLibraryRunHistoryQuery(() => authStore.isAdmin);
	const policyQuery = getTargetLibrarySettingsQuery(() => authStore.isAdmin);
	const scheduleQuery = getLibraryScanScheduleQuery(() => authStore.isAdmin);
	const statsQuery = getLibraryStatsQuery();
	const identityEstimateQuery = getLibraryIdentityPreparationEstimateQuery(
		() => authStore.user?.id,
		() => [],
		() => authStore.isAdmin
	);
	const identityRunsQuery = getLibraryIdentityPreparationsQuery(
		() => authStore.user?.id,
		() => authStore.isAdmin
	);
	const managementSettingsQuery = getLibraryManagementSettingsQuery(
		() => authStore.user?.id,
		() => authStore.isAdmin
	);
	const managementRunsQuery = getLibraryManagementOperationsQuery(
		() => authStore.user?.id,
		() => ({ limit: 20 })
	);
	const recoveryQuery = getLibraryManagementRecoveryQuery(
		() => authStore.user?.id,
		() => authStore.isAdmin
	);
	const requestRun = requestLibraryRun();

	const identificationActivity = $derived(
		activityQuery.data?.items.find((item) => item.kind === 'identification')
	);
	const latestScan = $derived(runHistoryQuery.data?.pages[0]?.items[0] ?? null);
	const identityRuns = $derived(identityRunsQuery.data?.pages.flatMap((page) => page.items) ?? []);
	const activeIdentity = $derived(
		identityRuns.find((item) => ['queued', 'running', 'paused'].includes(item.state)) ?? null
	);
	const identityReport = $derived(
		identityRuns.find(
			(item) => item.state === 'ready' && item.terminal_code !== 'IDENTITY_PREPARATION_DISCARDED'
		) ?? null
	);
	const managementHistory = $derived(
		managementRunsQuery.data?.pages.flatMap((page) => page.items) ?? []
	);
	const activeManagement = $derived(
		managementHistory.find((item) =>
			['queued', 'running', 'paused'].includes(item.operation.state)
		) ?? null
	);
	const readyPreview = $derived(
		managementHistory.find(
			(item) => item.operation.state === 'ready' && !item.activation_preview
		) ?? null
	);
	const defaultProfile = $derived(
		managementSettingsQuery.data?.profiles.find(
			(profile) => profile.id === managementSettingsQuery.data?.default_profile_id
		)?.name ?? 'Not configured'
	);
	const automaticAssignments = $derived(
		(managementSettingsQuery.data?.root_assignments ?? []).filter(
			(assignment) =>
				assignment.enabled &&
				(assignment.automatic_acquisitions ||
					assignment.automatic_drop_imports ||
					assignment.automatic_scan_discovered)
		)
	);
	const scanDiscoveredAutomation = $derived(
		automaticAssignments.some((assignment) => assignment.automatic_scan_discovered)
	);
	const enabledAutomationTriggers = $derived(
		[
			automaticAssignments.some((assignment) => assignment.automatic_acquisitions)
				? 'Acquisitions'
				: null,
			automaticAssignments.some((assignment) => assignment.automatic_drop_imports)
				? 'Drop / Free'
				: null,
			scanDiscoveredAutomation ? 'Scan-discovered' : null
		].filter((value): value is string => Boolean(value))
	);
	const recoveryAttention = $derived(
		(recoveryQuery.data?.needs_attention_count ?? 0) +
			(recoveryQuery.data?.cleanup_pending_count ?? 0)
	);
	const failedManagement = $derived(
		managementHistory.filter((item) => item.operation.state === 'failed').length
	);
	const systemAttention = $derived(
		recoveryAttention +
			failedManagement +
			(identityReport ? 1 : 0) +
			(identificationActivity?.provider_unavailable ? 1 : 0) +
			(latestScan?.state === 'failed' ? 1 : 0)
	);
	const systemStatusError = $derived(
		activityQuery.isError ||
			identityRunsQuery.isError ||
			managementRunsQuery.isError ||
			recoveryQuery.isError ||
			runHistoryQuery.isError
	);

	function relativeTime(timestamp: number | null | undefined): string {
		if (!timestamp) return 'Not yet scanned';
		const seconds = Math.max(0, Date.now() / 1000 - timestamp);
		if (seconds < 60) return 'Just now';
		if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
		if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
		return `${Math.floor(seconds / 86_400)}d ago`;
	}

	function scheduleLabel(): string {
		const schedule = scheduleQuery.data;
		if (!schedule) return 'Schedule unavailable';
		if (schedule.scan_frequency === 'manual') return 'Automatic scanning off';
		if (schedule.scan_frequency === 'daily') {
			return `Daily at ${schedule.daily_scan_time} ${schedule.server_timezone ?? ''}`.trim();
		}
		return `Every ${schedule.scan_frequency}`;
	}

	async function scanNow(): Promise<void> {
		const policyRevision = policyQuery.data?.policy_revision;
		if (!policyRevision) return;
		await requestRun
			.mutateAsync({
				kind: 'incremental',
				scope_ids: [],
				expected_policy_revision: policyRevision
			})
			.catch(() => undefined);
	}

	function managementHref(): string {
		if (recoveryAttention || recoveryQuery.isError) return '#management-controls';
		if (activeManagement) {
			return `/library/management/operations/${encodeURIComponent(activeManagement.operation.id)}`;
		}
		if (readyPreview) {
			return `/library/management/previews/${encodeURIComponent(readyPreview.operation.id)}`;
		}
		return '#management-controls';
	}

	function managementAction(): string {
		if (recoveryAttention || recoveryQuery.isError) return 'Review recovery';
		if (activeManagement) return 'Open operation';
		if (readyPreview) return 'Review preview';
		return 'Preview changes';
	}
</script>

<section class="library-action-desk" aria-labelledby="library-action-desk-title">
	<div class="library-action-desk-heading">
		<div>
			<p class="font-mono text-xs uppercase tracking-[0.18em] text-primary/70">Today at the desk</p>
			<h2 id="library-action-desk-title" class="font-display text-2xl font-bold">
				Library actions
			</h2>
		</div>
		<p>Start with routine work. The detailed controls are just below.</p>
	</div>

	<div class="library-action-grid">
		<article
			class="library-action-card library-action-card--scan"
			aria-labelledby="library-action-scan-title"
		>
			<header>
				<span><ScanSearch class="h-5 w-5" /></span>
				<div>
					<p>Read-only catalog</p>
					<h3 id="library-action-scan-title">Scan &amp; identify</h3>
				</div>
			</header>
			{#if activityQuery.isError || statsQuery.isError || scheduleQuery.isError || runsQuery.isError || policyQuery.isError}
				<div class="library-action-error" role="status">
					Scan status is unavailable. Detailed controls remain available.
				</div>
			{:else}
				<div class="library-action-scan-status">
					<strong
						>{runsQuery.data?.active
							? runsQuery.data.active.state.replaceAll('_', ' ')
							: relativeTime(statsQuery.data?.last_scan_at)}</strong
					>
					<span
						>{scheduleLabel()} · {(statsQuery.data?.total_tracks ?? 0).toLocaleString()} tracks in {(
							statsQuery.data?.total_albums ?? 0
						).toLocaleString()} albums</span
					>
				</div>
			{/if}
			<p class="library-action-explainer">
				Finds new, changed, and missing files · updates the catalog · queues album identification.
			</p>
			<p class="library-action-safety">
				<ShieldCheck class="h-4 w-4" /> Scanning never edits music files.{#if scanDiscoveredAutomation}
					Separate scan-discovered management automation is enabled and may stage file changes
					afterward.{/if}
			</p>
			<footer>
				<button
					class="btn btn-primary"
					disabled={requestRun.isPending ||
						Boolean(runsQuery.data?.active) ||
						!policyQuery.data?.policy_revision}
					onclick={() => void scanNow()}
					>{requestRun.isPending
						? 'Queuing…'
						: runsQuery.data?.active
							? 'Scan in progress'
							: 'Scan now'}</button
				>
				<a
					class="btn btn-ghost btn-sm"
					href="#scanning-controls"
					aria-label="Open Scan & identify detailed controls"
					>Open detailed controls <ArrowRight class="h-4 w-4" /></a
				>
			</footer>
		</article>

		<article
			class="library-action-card library-action-card--identity"
			aria-labelledby="library-action-identity-title"
		>
			<header>
				<span><BookOpenCheck class="h-5 w-5" /></span>
				<div>
					<p>Management prerequisite</p>
					<h3 id="library-action-identity-title">Identity readiness</h3>
				</div>
			</header>
			{#if identityEstimateQuery.isError || identityRunsQuery.isError}
				<div class="library-action-error" role="status">
					Identity readiness could not be loaded.
				</div>
			{:else}
				<strong class="library-action-number"
					>{(
						(identityEstimateQuery.data?.mapping_required_count ?? 0) +
						(identityEstimateQuery.data?.exact_release_required_count ?? 0)
					).toLocaleString()}</strong
				>
				<p>albums need preparation</p>
				<div class="library-action-split">
					<span
						><strong
							>{(
								identityEstimateQuery.data?.exact_release_required_count ?? 0
							).toLocaleString()}</strong
						> exact editions</span
					><span
						><strong
							>{(identityEstimateQuery.data?.mapping_required_count ?? 0).toLocaleString()}</strong
						> exact track maps</span
					>
				</div>
			{/if}
			<footer>
				<a class="btn btn-outline" href="#identity-readiness"
					>{activeIdentity
						? 'View progress'
						: identityReport
							? 'Review report'
							: 'Prepare identities'}</a
				><a
					class="btn btn-ghost btn-sm"
					href="#management-controls"
					aria-label="Open Identity readiness detailed controls"
					>Open detailed controls <ArrowRight class="h-4 w-4" /></a
				>
			</footer>
		</article>

		<article
			class="library-action-card library-action-card--manage"
			aria-labelledby="library-action-manage-title"
		>
			<header>
				<span><FolderCog class="h-5 w-5" /></span>
				<div>
					<p>File-writing system</p>
					<h3 id="library-action-manage-title">Organize files</h3>
				</div>
			</header>
			{#if managementSettingsQuery.isError || managementRunsQuery.isError}
				<div class="library-action-error" role="status">
					Management status is unavailable. No file action was started.
				</div>
			{:else}
				<div class="library-manage-facts">
					<span><small>Effective default</small><strong>{defaultProfile}</strong></span><span
						><small>Automation</small><strong
							>{enabledAutomationTriggers.length
								? enabledAutomationTriggers.join(' · ')
								: 'Off everywhere'}</strong
						></span
					><span
						><small>Active work</small><strong>{activeManagement ? '1 operation' : 'None'}</strong
						></span
					><span
						><small>Ready previews</small><strong
							>{readyPreview ? '1 awaiting review' : 'None'}</strong
						></span
					>
				</div>
			{/if}
			<footer>
				<a class="btn management-btn" href={managementHref()}>{managementAction()}</a><a
					class="btn btn-ghost btn-sm"
					href="#management-controls"
					aria-label="Open Organize files detailed controls"
					>Open detailed controls <ArrowRight class="h-4 w-4" /></a
				>
			</footer>
		</article>

		<article
			class="library-action-card library-action-card--condition"
			data-attention={systemAttention > 0 || systemStatusError}
			aria-labelledby="library-action-condition-title"
		>
			<header>
				<span
					>{#if systemAttention || systemStatusError}<AlertTriangle
							class="h-5 w-5"
						/>{:else}<CircleCheck class="h-5 w-5" />{/if}</span
				>
				<div>
					<p>System condition</p>
					<h3 id="library-action-condition-title">
						{systemStatusError
							? 'Status unavailable'
							: systemAttention
								? 'Attention required'
								: 'Ready for routine work'}
					</h3>
				</div>
			</header>
			{#if systemStatusError}<p class="library-action-error" role="status">
					Some system checks could not be loaded. Open the detailed controls before starting file
					writes.
				</p>{:else if systemAttention}<p>
					{recoveryAttention} recovery items · {failedManagement} failed management operations{#if identificationActivity?.provider_unavailable}
						· MusicBrainz unavailable{/if}
					{#if identityReport}
						· Identity report waiting for review{/if}
				</p>{:else}<p>
					Recovery journals are clear, no failed work is waiting, and providers report healthy.
				</p>{/if}
			<footer>
				<a
					class="btn btn-ghost btn-sm"
					href="#management-controls"
					aria-label="Open System condition detailed controls"
					>Open detailed controls <ArrowRight class="h-4 w-4" /></a
				>
			</footer>
		</article>
	</div>
</section>
