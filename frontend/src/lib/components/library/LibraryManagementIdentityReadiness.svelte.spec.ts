import { page } from '@vitest/browser/context';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

const h = vi.hoisted(() => ({
	create: vi.fn(),
	apply: vi.fn(),
	discard: vi.fn(),
	preparations: {
		data: { pages: [{ items: [] as Array<Record<string, unknown>> }] },
		isLoading: false,
		isError: false
	},
	estimate: {
		data: {
			album_count: 20,
			ready_album_count: 4,
			mapping_required_count: 12,
			exact_release_required_count: 4,
			selected_root_count: 0,
			queued_preparation_count: 0
		},
		isLoading: false,
		isError: false
	},
	findings: {
		data: {
			pages: [
				{
					current_counts_by_finding: {
						mapping_ready: 1,
						ready: 4,
						exact_release_required: 3,
						needs_review: 1
					},
					refresh_required: false,
					items: [
						{
							id: 'finding-1',
							local_album_id: 'album-1',
							album_title: 'Juturna',
							album_artist_name: 'Circa Survive',
							album_year: 2005,
							cover_available: false,
							evidence_id: 'evidence-1',
							review_id: null,
							finding_code: 'mapping_ready',
							reason_code: 'EXACT_RELEASE_MAPPING_SUPPORTED',
							confidence: 'supported',
							apply_eligible: true,
							state: 'open',
							apply_result: null,
							updated_at: 10,
							row_revision: 1
						}
					]
				}
			]
		},
		isLoading: false,
		isError: false,
		hasNextPage: false
	}
}));

vi.mock('$lib/stores/authStore.svelte', () => ({
	authStore: { isAdmin: true, user: { id: 'admin-1' } }
}));
vi.mock('$lib/queries/library/LibraryIdentityPreparationQueries.svelte', () => ({
	getLibraryIdentityPreparationsQuery: () => h.preparations,
	getLibraryIdentityPreparationEstimateQuery: () => h.estimate,
	getLibraryIdentityPreparationFindingsQuery: () => h.findings
}));
vi.mock('$lib/queries/library/LibraryIdentityPreparationMutations.svelte', () => ({
	createLibraryIdentityPreparation: () => ({ mutateAsync: h.create, isPending: false }),
	applyLibraryIdentityPreparation: () => ({ mutateAsync: h.apply, isPending: false }),
	discardLibraryIdentityPreparation: () => ({ mutateAsync: h.discard, isPending: false })
}));
vi.mock('$lib/queries/library/LibraryOperationMutations.svelte', () => ({
	controlLibraryOperation: () => ({ mutateAsync: vi.fn(), isPending: false })
}));
vi.mock('$lib/queries/library/LibraryQueries.svelte', () => ({
	getLibraryAlbumDetailQuery: () => ({
		data: undefined,
		isLoading: false,
		isError: false
	})
}));

import LibraryManagementIdentityReadiness from './LibraryManagementIdentityReadiness.svelte';

const roots = [
	{ id: 'root-1', label: 'Archive', path: '/music', policy: 'automatic' as const, rules: [] }
];

function readyReport() {
	return {
		id: 'preparation-1',
		kind: 'repair',
		state: 'ready',
		expected_work_count: 20,
		completed_count: 20,
		succeeded_count: 20,
		failed_count: 0,
		skipped_count: 0,
		control_request: 'none',
		terminal_code: 'DRY_RUN_READY',
		row_revision: 7,
		event_revision: 2,
		created_at: 1,
		updated_at: 2,
		results: [],
		results_truncated: false,
		reidentification_candidates: [],
		repair_summary: {
			total_identities: 20,
			remaining_identities: 0,
			input_track_count: 100,
			playable_after_detach_track_count: 100,
			estimated_apply_changes: 12,
			catalog_snapshot_revision: 4,
			target_matcher_version: 'management-exact-release-v2',
			counts_by_finding: {
				mapping_ready: 12,
				ready: 4,
				exact_release_required: 3,
				needs_review: 1
			},
			counts_by_reason: {},
			album_counts_by_root: { 'root-1': 20 },
			provider_deferred_count: 0,
			failed_evidence_count: 0,
			purpose: 'management_readiness',
			ready_album_count: 4,
			mapping_candidate_count: 12,
			exact_release_required_count: 3,
			needs_review_count: 1
		}
	};
}

beforeEach(() => {
	vi.clearAllMocks();
	h.create.mockResolvedValue({});
	h.apply.mockResolvedValue({});
	h.discard.mockResolvedValue({});
	h.preparations = {
		data: { pages: [{ items: [] }] },
		isLoading: false,
		isError: false
	};
	h.findings.data.pages[0].current_counts_by_finding = {
		mapping_ready: 1,
		ready: 4,
		exact_release_required: 3,
		needs_review: 1
	};
	h.findings.data.pages[0].refresh_required = false;
	h.findings.data.pages[0].items[0].reason_code = 'EXACT_RELEASE_MAPPING_SUPPORTED';
});

describe('LibraryManagementIdentityReadiness', () => {
	it('explains the exact-edition prerequisite before starting a read-only check', async () => {
		render(LibraryManagementIdentityReadiness, { roots });

		await expect.element(page.getByText('Need exact track maps')).toBeVisible();
		await expect.element(page.getByText('Need an exact edition', { exact: true })).toBeVisible();
		await page.getByRole('button', { name: 'Prepare identities...' }).click();
		await expect.element(page.getByRole('heading', { name: 'Prepare identities' })).toHaveFocus();
		await expect
			.element(page.getByText(/This dry run checks exact MusicBrainz editions/))
			.toBeVisible();
		await page.getByRole('button', { name: 'Start read-only check' }).click();

		expect(h.create).toHaveBeenCalledWith([]);
	});

	it('requires a second confirmation before accepting catalog-only mappings', async () => {
		h.preparations = {
			data: { pages: [{ items: [readyReport()] }] },
			isLoading: false,
			isError: false
		};
		render(LibraryManagementIdentityReadiness, { roots });

		await expect.element(page.getByText('Juturna')).toBeVisible();
		await expect.element(page.getByText('Circa Survive')).toBeVisible();
		await expect.element(page.getByText('2005')).toBeVisible();
		await expect.element(page.getByText(/Exact track map verified/)).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: /Mappings ready/ }))
			.toHaveTextContent('1');
		await expect
			.element(page.getByRole('link', { name: 'Open release' }))
			.toHaveAttribute('href', '/album/album-1');
		await page.getByRole('button', { name: 'Accept mappings...' }).click();
		await expect
			.element(page.getByRole('heading', { name: 'Accept exact-release mappings?' }))
			.toHaveFocus();
		await expect
			.element(page.getByText(/This writes only verified MusicBrainz identities/))
			.toBeVisible();
		await page.getByRole('button', { name: 'Accept catalog mappings' }).click();

		expect(h.apply).toHaveBeenCalledWith({
			jobId: 'preparation-1',
			expectedRevision: 7
		});
	});

	it('can dismiss a ready report without changing identities or files', async () => {
		h.preparations = {
			data: { pages: [{ items: [readyReport()] }] },
			isLoading: false,
			isError: false
		};
		render(LibraryManagementIdentityReadiness, { roots });

		await page.getByRole('button', { name: 'Dismiss report' }).click();
		await expect.element(page.getByRole('heading', { name: 'Dismiss this report?' })).toHaveFocus();
		await page
			.getByRole('dialog')
			.getByRole('button', { name: 'Dismiss report', exact: true })
			.click();

		expect(h.discard).toHaveBeenCalledWith({
			jobId: 'preparation-1',
			expectedRevision: 7
		});
	});

	it('opens re-identification directly from a needs-review finding', async () => {
		h.preparations = {
			data: { pages: [{ items: [readyReport()] }] },
			isLoading: false,
			isError: false
		};
		h.findings.data.pages[0].items[0].reason_code = 'RELEASE_TYPE_REQUIRES_CONFIRMATION';
		render(LibraryManagementIdentityReadiness, { roots });
		await page.getByRole('button', { name: /Needs review/ }).click();
		await expect.element(page.getByRole('button', { name: 'Re-identify' })).toBeVisible();
		await expect
			.element(page.getByText('Compilation or live edition needs confirmation'))
			.toBeVisible();
		await expect.element(page.getByText(/Only current findings are listed/)).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Open release' })).not.toBeInTheDocument();
	});

	it('requires a fresh check and hides report actions for old matcher rules', async () => {
		h.preparations = {
			data: { pages: [{ items: [readyReport()] }] },
			isLoading: false,
			isError: false
		};
		h.findings.data.pages[0].refresh_required = true;
		h.findings.data.pages[0].items[0].reason_code = 'UNSAFE_RELEASE_TYPE';
		render(LibraryManagementIdentityReadiness, { roots });

		await expect
			.element(page.getByText('These checks used older rules. Run a fresh identity check.'))
			.toBeVisible();
		await expect
			.element(page.getByText('Compilation or live edition needs confirmation'))
			.toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Accept mappings...' }))
			.not.toBeInTheDocument();
		await expect.element(page.getByRole('link', { name: 'Open release' })).not.toBeInTheDocument();
	});
});
