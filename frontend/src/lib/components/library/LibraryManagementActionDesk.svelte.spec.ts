import { page } from '@vitest/browser/context';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import '../../../app.css';

const h = vi.hoisted(() => ({
	activity: { data: { items: [], work_items: [] }, isError: false },
	runs: {
		data: { active: null as Record<string, unknown> | null, queued: null },
		isError: false
	},
	runHistory: {
		data: { pages: [{ items: [] as Array<Record<string, unknown>> }] },
		isError: false
	},
	policy: { data: { policy_revision: 'policy-7' }, isError: false },
	schedule: {
		data: {
			scan_frequency: 'daily',
			daily_scan_time: '03:00',
			server_timezone: 'Europe/London'
		},
		isError: false
	},
	stats: {
		data: { total_tracks: 1951, total_albums: 201, last_scan_at: Date.now() / 1000 - 120 },
		isError: false
	},
	identityEstimate: {
		data: { mapping_required_count: 3, exact_release_required_count: 14 },
		isError: false
	},
	identityRuns: {
		data: { pages: [{ items: [] as Array<Record<string, unknown>> }] },
		isError: false
	},
	managementSettings: {
		data: {
			default_profile_id: 'profile-1',
			profiles: [{ id: 'profile-1', name: 'Picard-style Organizer' }],
			root_assignments: []
		},
		isError: false
	},
	managementRuns: {
		data: { pages: [{ items: [] as Array<Record<string, unknown>> }] },
		isError: false
	},
	recovery: {
		data: { needs_attention_count: 0, cleanup_pending_count: 0 },
		isError: false
	},
	requestRun: vi.fn()
}));

vi.mock('$lib/stores/authStore.svelte', () => ({
	authStore: { user: { id: 'admin-1' }, isAdmin: true }
}));
vi.mock('$lib/queries/library/LibraryActivityQueries.svelte', () => ({
	getLibraryActivityQuery: () => h.activity
}));
vi.mock('$lib/queries/library/LibraryOperationQueries.svelte', () => ({
	getCurrentLibraryRunsQuery: () => h.runs,
	getLibraryRunHistoryQuery: () => h.runHistory
}));
vi.mock('$lib/queries/library/LibraryOperationMutations.svelte', () => ({
	requestLibraryRun: () => ({ mutateAsync: h.requestRun, isPending: false })
}));
vi.mock('$lib/queries/library/LibraryPolicyQueries.svelte', () => ({
	getTargetLibrarySettingsQuery: () => h.policy
}));
vi.mock('$lib/queries/library/LibraryQueries.svelte', () => ({
	getLibraryScanScheduleQuery: () => h.schedule,
	getLibraryStatsQuery: () => h.stats
}));
vi.mock('$lib/queries/library/LibraryIdentityPreparationQueries.svelte', () => ({
	getLibraryIdentityPreparationEstimateQuery: () => h.identityEstimate,
	getLibraryIdentityPreparationsQuery: () => h.identityRuns
}));
vi.mock('$lib/queries/library-management/LibraryManagementQueries.svelte', () => ({
	getLibraryManagementSettingsQuery: () => h.managementSettings,
	getLibraryManagementOperationsQuery: () => h.managementRuns,
	getLibraryManagementRecoveryQuery: () => h.recovery
}));

import LibraryManagementActionDesk from './LibraryManagementActionDesk.svelte';

beforeEach(async () => {
	vi.clearAllMocks();
	await page.viewport(1280, 720);
	h.runs.data.active = null;
	h.activity.isError = false;
	h.runHistory.isError = false;
	h.policy.isError = false;
	h.stats.isError = false;
	h.identityRuns.data.pages = [{ items: [] }];
	h.managementRuns.data.pages = [{ items: [] }];
	h.recovery.data.needs_attention_count = 0;
	h.recovery.data.cleanup_pending_count = 0;
	h.recovery.isError = false;
	h.requestRun.mockResolvedValue({});
});

describe('LibraryManagementActionDesk', () => {
	it('balances the desktop cards and keeps the mobile work order', async () => {
		render(LibraryManagementActionDesk);
		const scanCard = page.getByRole('article', { name: 'Scan & identify' }).element();
		const identityCard = page.getByRole('article', { name: 'Identity readiness' }).element();
		expect(
			Math.abs(
				scanCard.getBoundingClientRect().height - identityCard.getBoundingClientRect().height
			)
		).toBeLessThanOrEqual(1);

		await page.viewport(390, 760);
		const manageCard = page.getByRole('article', { name: 'Organize files' }).element();
		const conditionCard = page.getByRole('article', { name: 'Ready for routine work' }).element();
		const tops = [scanCard, identityCard, manageCard, conditionCard].map(
			(card) => card.getBoundingClientRect().top
		);
		expect(tops).toEqual([...tops].sort((left, right) => left - right));
	});

	it('queues one all-root incremental scan with the current policy revision', async () => {
		render(LibraryManagementActionDesk);

		await expect.element(page.getByRole('heading', { name: 'Scan & identify' })).toBeVisible();
		await expect.element(page.getByText(/Finds new, changed, and missing files/)).toBeVisible();
		await expect.element(page.getByText(/Scanning never edits music files/)).toBeVisible();
		await page.getByRole('button', { name: 'Scan now' }).click();
		expect(h.requestRun).toHaveBeenCalledWith({
			kind: 'incremental',
			scope_ids: [],
			expected_policy_revision: 'policy-7'
		});
	});

	it('adapts actions for active and paused work', async () => {
		h.runs.data.active = { id: 'scan-1', state: 'paused' };
		h.identityRuns.data.pages = [{ items: [{ id: 'identity-1', state: 'paused' }] }];
		h.managementRuns.data.pages = [
			{
				items: [
					{
						operation: { id: 'operation-1', state: 'running' },
						profile_name: 'Picard-style Organizer'
					}
				]
			}
		];
		render(LibraryManagementActionDesk);

		await expect.element(page.getByRole('button', { name: 'Scan in progress' })).toBeDisabled();
		await expect.element(page.getByRole('link', { name: 'View progress' })).toBeVisible();
		await expect
			.element(page.getByRole('link', { name: 'Open operation' }))
			.toHaveAttribute('href', '/library/management/operations/operation-1');
	});

	it('keeps healthy cards visible when scan status fails and promotes recovery attention', async () => {
		h.stats.isError = true;
		h.recovery.data.needs_attention_count = 2;
		render(LibraryManagementActionDesk);

		await expect.element(page.getByText(/Scan status is unavailable/)).toBeVisible();
		await expect.element(page.getByText('17')).toBeVisible();
		await expect.element(page.getByRole('heading', { name: 'Attention required' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Review recovery' })).toBeVisible();
	});

	it('does not claim healthy status when a supporting query fails', async () => {
		h.activity.isError = true;
		render(LibraryManagementActionDesk);

		await expect.element(page.getByText(/Scan status is unavailable/)).toBeVisible();
		await expect.element(page.getByRole('heading', { name: 'Status unavailable' })).toBeVisible();
		await expect.element(page.getByText(/Some system checks could not be loaded/)).toBeVisible();
		await expect.element(page.getByText(/providers report healthy/)).not.toBeInTheDocument();
	});

	it('keeps card-specific detailed-control shortcuts', async () => {
		render(LibraryManagementActionDesk);

		await expect
			.element(page.getByRole('link', { name: 'Open Organize files detailed controls' }))
			.toHaveAttribute('href', '#management-controls');
		await expect
			.element(page.getByRole('link', { name: 'Open System condition detailed controls' }))
			.toHaveAttribute('href', '#management-controls');
	});
});
