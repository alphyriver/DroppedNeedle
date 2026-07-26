import { page } from '@vitest/browser/context';
import { beforeEach, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

const saveMutate = vi.fn().mockResolvedValue({});
let prowlarrEnabled = true;
let indexersData: unknown[] = [];

vi.mock('$lib/queries/downloads/ProwlarrTorrentQueries.svelte', () => ({
	getQbittorrentConfigQuery: () => ({
		data: {
			enabled: false,
			client_type: 'qbittorrent',
			url: 'http://qbt:8080',
			api_key: 'qbittorrent****',
			category: 'droppedneedle',
			downloads_mount: '/qbittorrent-downloads'
		},
		isLoading: false,
		isError: false
	}),
	getProwlarrConfigQuery: () => ({ data: { enabled: prowlarrEnabled }, isLoading: false }),
	saveQbittorrentConfig: () => ({ mutateAsync: saveMutate, isPending: false }),
	testQbittorrent: () => ({ mutateAsync: vi.fn(), isPending: false })
}));
vi.mock('$lib/queries/downloads/IndexerQueries.svelte', () => ({
	getIndexersQuery: () => ({ data: indexersData, isLoading: false })
}));
vi.mock('$lib/stores/toast', () => ({ toastStore: { show: vi.fn() } }));
import SettingsQbittorrent from './SettingsQbittorrent.svelte';

beforeEach(() => {
	prowlarrEnabled = true;
	indexersData = [];
	saveMutate.mockClear();
});

it('renders and saves the masked qBittorrent API key', async () => {
	render(SettingsQbittorrent);
	await page.getByRole('button', { name: 'Expand' }).click();
	await expect
		.element(page.getByLabelText('API key', { exact: true }))
		.toHaveValue('qbittorrent****');
	await page.getByRole('button', { name: 'Save settings' }).click();
	expect(saveMutate).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'qbittorrent****' }));
});

it('accepts an enabled Torznab indexer when Prowlarr is disabled', async () => {
	prowlarrEnabled = false;
	indexersData = [{ id: 't1', type: 'torznab', enabled: true }];
	render(SettingsQbittorrent);

	await page.getByRole('button', { name: 'Expand' }).click();
	await page.getByLabelText('Enable qBittorrent download client').click();

	await expect.element(page.getByText('No torrent indexers configured.')).not.toBeInTheDocument();
});

it('warns when neither Prowlarr nor an enabled Torznab indexer exists', async () => {
	prowlarrEnabled = false;
	render(SettingsQbittorrent);

	await page.getByRole('button', { name: 'Expand' }).click();
	await page.getByLabelText('Enable qBittorrent download client').click();

	await expect.element(page.getByText('No torrent indexers configured.')).toBeInTheDocument();
});
