import { cdp, page } from '@vitest/browser/context';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

interface EmulationCdpSession {
	send(
		method: 'Emulation.setEmulatedMedia',
		params: { features: { name: string; value: string }[] }
	): Promise<unknown>;
}

const h = vi.hoisted(() => ({
	settings: {
		data: {
			library_roots: [
				{
					id: 'root-1',
					path: '/music',
					label: 'Music',
					policy: 'automatic',
					rules: []
				}
			],
			policy_revision: 'policy-1'
		},
		isLoading: false,
		isError: false
	} as Record<string, unknown>,
	activity: {
		data: { items: [], work_items: [] as Array<Record<string, unknown>> },
		isLoading: false,
		isError: false
	},
	operationsRender: vi.fn(),
	settingsRender: vi.fn()
}));

function viewportRect(top: number): DOMRect {
	return {
		x: 0,
		y: top,
		top,
		right: 100,
		bottom: top + 100,
		left: 0,
		width: 100,
		height: 100,
		toJSON: () => ({})
	};
}

vi.mock('$lib/components/library/LibraryOperationsPanel.svelte', () => {
	const Comp = function () {
		h.operationsRender();
	};
	Comp.prototype = {};
	return { default: Comp };
});

vi.mock('$lib/components/settings/SettingsLibraryManagement.svelte', () => {
	const Comp = function (_anchor: unknown, props: Record<string, unknown>) {
		h.settingsRender(props);
	};
	Comp.prototype = {};
	return { default: Comp };
});

vi.mock('$lib/queries/library/LibraryPolicyQueries.svelte', () => ({
	getTargetLibrarySettingsQuery: () => h.settings
}));

vi.mock('$lib/queries/library/LibraryActivityQueries.svelte', () => ({
	getLibraryActivityQuery: () => h.activity
}));

import LibraryManagementPage from './+page.svelte';

let scrollSpy: ReturnType<typeof vi.spyOn>;
let scrollSections: HTMLElement[] = [];

beforeEach(() => {
	vi.clearAllMocks();
	h.activity.data.work_items = [];
	window.history.replaceState(null, '', window.location.pathname);
	scrollSpy = vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(() => {});
	scrollSections = [];
});

afterEach(() => {
	scrollSpy.mockRestore();
	for (const section of scrollSections) section.remove();
});

describe('Library Management route page', () => {
	it('presents one administrator workspace with clear scan and write destinations', async () => {
		render(LibraryManagementPage);
		await expect.element(page.getByRole('heading', { name: 'Library Management' })).toBeVisible();
		const navigation = page.getByRole('navigation', { name: 'Library Management sections' });
		await expect
			.element(navigation.getByRole('link', { name: 'Scan & identify' }))
			.toHaveAttribute('href', '#scanning-controls');
		await expect
			.element(navigation.getByRole('link', { name: 'Manage files' }))
			.toHaveAttribute('href', '#management-controls');
		await expect
			.element(navigation.getByRole('link', { name: 'Profiles & automation' }))
			.toHaveAttribute('href', '#management-settings');
		await expect
			.element(navigation.getByRole('link', { name: 'History' }))
			.toHaveAttribute('href', '/library/management/history');
		await expect
			.element(navigation.getByRole('link', { name: 'Overview' }))
			.toHaveAttribute('aria-current', 'location');
		expect(h.operationsRender).toHaveBeenCalledOnce();
	});

	it('adds compact live-work badges without replacing the section map', async () => {
		h.activity.data.work_items = [
			{
				id: 'scan-1',
				kind: 'scan',
				state: 'running',
				phase: 'indexing',
				effect: 'catalog_only',
				processed: 50,
				total: 100,
				unit: 'files',
				indeterminate: false,
				remaining_count: null
			},
			{
				id: 'management-1',
				kind: 'library_management',
				state: 'running',
				phase: 'applying',
				effect: 'file_writing',
				processed: 1,
				total: 4,
				unit: 'releases',
				indeterminate: false,
				remaining_count: null
			}
		];

		render(LibraryManagementPage);

		const navigation = page.getByRole('navigation', { name: 'Library Management sections' });
		await expect.element(navigation.getByText('2 tasks')).toBeVisible();
		await expect.element(navigation.getByText('50%')).toBeVisible();
		await expect.element(navigation.getByText('Writing')).toBeVisible();
	});

	it('highlights the section currently beneath the sticky workspace map', async () => {
		let scanningTop = -100;
		let managementTop = 900;
		for (const [id, getTop] of [
			['operations', () => -1000],
			['scanning-controls', () => scanningTop],
			['management-controls', () => managementTop]
		] as const) {
			const section = document.createElement('section');
			section.id = id;
			vi.spyOn(section, 'getBoundingClientRect').mockImplementation(() => viewportRect(getTop()));
			document.body.append(section);
			scrollSections.push(section);
		}

		render(LibraryManagementPage);
		vi.spyOn(
			page.getByRole('region', { name: 'Profiles & automation' }).element(),
			'getBoundingClientRect'
		).mockReturnValue(viewportRect(10_000));
		window.dispatchEvent(new Event('scroll'));
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
		const navigation = page.getByRole('navigation', { name: 'Library Management sections' });
		await expect
			.element(navigation.getByRole('link', { name: 'Scan & identify' }))
			.toHaveAttribute('aria-current', 'location');

		scanningTop = -600;
		managementTop = -100;
		window.dispatchEvent(new Event('scroll'));
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
		await expect
			.element(navigation.getByRole('link', { name: 'Manage files' }))
			.toHaveAttribute('aria-current', 'location');
	});

	it('keeps a clicked section active at its scroll-margin landing position', async () => {
		for (const [id, top, scrollMarginTop] of [
			['operations', -1000, '112px'],
			['scanning-controls', -100, '144px'],
			['management-controls', 144, '144px']
		] as const) {
			const section = document.createElement('section');
			section.id = id;
			section.style.scrollMarginTop = scrollMarginTop;
			vi.spyOn(section, 'getBoundingClientRect').mockReturnValue(viewportRect(top));
			document.body.append(section);
			scrollSections.push(section);
		}

		render(LibraryManagementPage);
		vi.spyOn(
			page.getByRole('region', { name: 'Profiles & automation' }).element(),
			'getBoundingClientRect'
		).mockReturnValue(viewportRect(10_000));
		const navigation = page.getByRole('navigation', { name: 'Library Management sections' });
		const link = navigation.getByRole('link', { name: 'Manage files' });
		await link.click();
		window.dispatchEvent(new Event('scroll'));
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

		await expect.element(link).toHaveAttribute('aria-current', 'location');
	});

	it('mounts profile and automation settings with the saved roots and policy revision', async () => {
		render(LibraryManagementPage);
		const details = page.getByRole('region', { name: 'Profiles & automation' });
		expect((details.element() as HTMLDetailsElement).open).toBe(true);
		await expect
			.element(page.getByRole('heading', { name: 'Profiles & automation' }))
			.toBeVisible();
		expect(h.settingsRender).toHaveBeenCalledWith(
			expect.objectContaining({
				roots: expect.arrayContaining([expect.objectContaining({ id: 'root-1' })]),
				policyRevision: 'policy-1'
			})
		);
	});

	it('reopens, scrolls to, and focuses an already-active detail hash', async () => {
		render(LibraryManagementPage);
		const navigation = page.getByRole('navigation', { name: 'Library Management sections' });
		const link = navigation.getByRole('link', { name: 'Profiles & automation' });
		const details = page.getByRole('region', { name: 'Profiles & automation' });
		const summaryText = details.getByText('Profiles & automation', { exact: true }).first();
		const summary = details.element().firstElementChild as HTMLElement;

		await summaryText.click();
		expect((details.element() as HTMLDetailsElement).open).toBe(false);
		await link.click();
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
		expect(window.location.hash).toBe('#management-settings');
		await expect.element(link).toHaveAttribute('aria-current', 'location');
		expect((details.element() as HTMLDetailsElement).open).toBe(true);
		expect(document.activeElement).toBe(summary);
		expect(scrollSpy).toHaveBeenLastCalledWith({ behavior: 'smooth', block: 'start' });

		await summaryText.click();
		await link.click();
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
		expect((details.element() as HTMLDetailsElement).open).toBe(true);
		expect(document.activeElement).toBe(summary);
	});

	it('uses instant detail scrolling when reduced motion is requested', async () => {
		const session = cdp() as EmulationCdpSession;
		await session.send('Emulation.setEmulatedMedia', {
			features: [{ name: 'prefers-reduced-motion', value: 'reduce' }]
		});
		try {
			render(LibraryManagementPage);
			const details = page.getByRole('region', { name: 'Profiles & automation' });
			const summary = details.element().firstElementChild as HTMLElement;
			await details.getByText('Profiles & automation', { exact: true }).first().click();
			await page
				.getByRole('navigation', { name: 'Library Management sections' })
				.getByRole('link', { name: 'Profiles & automation' })
				.click();
			await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
			expect(document.activeElement).toBe(summary);
			expect(scrollSpy).toHaveBeenLastCalledWith({ behavior: 'auto', block: 'start' });
		} finally {
			await session.send('Emulation.setEmulatedMedia', {
				features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }]
			});
		}
	});
});
