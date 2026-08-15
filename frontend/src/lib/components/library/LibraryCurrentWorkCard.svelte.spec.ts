import { page } from '@vitest/browser/context';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type {
	LibraryActivityResponse,
	LibraryWorkItem
} from '$lib/queries/library/LibraryOperationsTypes';
import '../../../app.css';

const h = vi.hoisted(() => ({
	query: {
		data: { items: [], work_items: [] } as LibraryActivityResponse | undefined,
		isLoading: false,
		isError: false
	}
}));

vi.mock('$lib/queries/library/LibraryActivityQueries.svelte', () => ({
	getLibraryActivityQuery: () => h.query
}));

vi.mock('$lib/stores/authStore.svelte', () => ({
	authStore: { user: { id: 'admin-1' } }
}));

import LibraryCurrentWorkCard from './LibraryCurrentWorkCard.svelte';

function work(overrides: Partial<LibraryWorkItem> = {}): LibraryWorkItem {
	return {
		id: 'management-1',
		kind: 'library_management',
		state: 'running',
		phase: 'validating_staged_files',
		mode: 'apply',
		effect: 'file_writing',
		processed: 4,
		total: 10,
		unit: 'releases',
		indeterminate: false,
		remaining_count: null,
		subject_count: 93,
		started_at: null,
		updated_at: 1_000,
		origin: 'manual',
		profile_name: 'Picard-style Organizer + Lyrics',
		scope_label: null,
		new_count: 0,
		changed_count: 0,
		missing_count: 0,
		warning_count: 3,
		blocked_count: 7,
		succeeded_count: 4,
		failed_count: 0,
		skipped_count: 0,
		priority: 10,
		failure_event_id: null,
		failure_at: null,
		...overrides
	};
}

beforeEach(() => {
	h.query.data = { items: [], work_items: [] };
	h.query.isLoading = false;
	h.query.isError = false;
});

describe('LibraryCurrentWorkCard', () => {
	it('makes idle state explicit without filling the page with controls', async () => {
		render(LibraryCurrentWorkCard);
		await expect.element(page.getByText('No library work is running')).toBeVisible();
		await expect
			.element(page.getByText('Start a scan, prepare identities, or preview file changes below.'))
			.toBeVisible();
	});

	it('explains file-writing progress, safety context, and phases at a glance', async () => {
		h.query.data = { items: [], work_items: [work()] };
		render(LibraryCurrentWorkCard);

		await expect.element(page.getByText('Writing tags and organizing files')).toBeVisible();
		await expect.element(page.getByText('Writes music files')).toBeVisible();
		await expect.element(page.getByText('4 / 10 releases · 40%')).toBeVisible();
		await expect.element(page.getByText('Validate')).toBeVisible();
		await expect.element(page.getByText('93 files')).toBeVisible();
		await expect.element(page.getByText('3 warnings')).toBeVisible();
		await expect.element(page.getByText('7 safely excluded')).toBeVisible();
		await expect
			.element(page.getByRole('link', { name: 'Open details' }))
			.toHaveAttribute('href', '/library/management/operations/management-1');
	});

	it('shows concurrent work as a small queue beneath the primary operation', async () => {
		h.query.data = {
			items: [],
			work_items: [
				work(),
				work({
					id: 'scan-1',
					kind: 'scan',
					phase: 'indexing',
					mode: null,
					effect: 'catalog_only',
					processed: 30,
					total: 100,
					unit: 'files',
					subject_count: null,
					profile_name: null,
					origin: null,
					priority: 20
				})
			]
		};
		render(LibraryCurrentWorkCard);

		await expect.element(page.getByText('1 other task')).toBeVisible();
		await expect.element(page.getByText('Scanning library')).toBeVisible();
		await expect.element(page.getByText('Music files stay unchanged')).toBeVisible();
	});

	it('presents a recent failure as attention rather than active work', async () => {
		h.query.data = {
			items: [],
			work_items: [
				work({
					state: 'failed',
					effect: 'attention',
					total: null,
					indeterminate: true,
					failure_event_id: 'failure-1',
					failure_at: 1_000,
					started_at: 900,
					updated_at: 1_000,
					priority: 0
				})
			]
		};
		render(LibraryCurrentWorkCard);

		await expect.element(page.getByText('Needs attention').first()).toBeVisible();
		await expect
			.element(page.getByText('Applying Library Management changes failed'))
			.toBeVisible();
		await expect
			.element(
				page.getByRole('progressbar', {
					name: 'Failed while validating staged files: 4 releases processed'
				})
			)
			.toBeVisible();
		await expect.element(page.getByText('Validate')).not.toBeInTheDocument();
		await expect
			.element(page.getByRole('progressbar'))
			.not.toHaveClass(/library-live-progress__track--indeterminate/);
	});
});
