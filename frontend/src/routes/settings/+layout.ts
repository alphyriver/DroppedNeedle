import { authStore } from '$lib/stores/authStore.svelte';
import { redirect } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';

export const ssr = false;

export const load: LayoutLoad = async ({ parent }) => {
	// Child layout loads may start before the root layout has finished hydrating
	// authStore from /auth/me. Wait for that bootstrap before deciding whether the
	// user is an administrator, otherwise a slow response looks like a signed-out
	// user and bounces a valid admin back to the home page.
	await parent();
	if (!authStore.isAdmin) {
		throw redirect(302, '/');
	}
};
