import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ isAdmin: false }));

vi.mock('$lib/stores/authStore.svelte', () => ({
	authStore: {
		get isAdmin() {
			return state.isAdmin;
		}
	}
}));

import { load as loadSettings } from './+layout';
import { load as loadLegacyLibrarySettings } from './library/+page';

describe('settings route authorization', () => {
	beforeEach(() => {
		state.isAdmin = false;
	});

	it('waits for slow parent authentication before checking the admin role', async () => {
		const parent = vi.fn(async () => {
			await Promise.resolve();
			state.isAdmin = true;
			return {};
		});

		await expect(loadSettings({ parent } as never)).resolves.toBeUndefined();
		expect(parent).toHaveBeenCalledOnce();
	});

	it('redirects a confirmed non-admin only after the parent load finishes', async () => {
		const parent = vi.fn(async () => ({}));

		await expect(loadSettings({ parent } as never)).rejects.toMatchObject({
			status: 302,
			location: '/'
		});
		expect(parent).toHaveBeenCalledOnce();
	});

	it('waits for the settings guard before redirecting the legacy library route', async () => {
		const parent = vi.fn(async () => ({}));

		await expect(loadLegacyLibrarySettings({ parent } as never)).rejects.toMatchObject({
			status: 307,
			location: '/settings?tab=library'
		});
		expect(parent).toHaveBeenCalledOnce();
	});
});
