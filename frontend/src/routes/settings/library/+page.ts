import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

// Library settings moved into the consolidated Settings → Library tab.
export const load: PageLoad = async ({ parent }) => {
	// Let the Settings layout finish authentication and authorization before this
	// compatibility route redirects to the consolidated tab.
	await parent();
	throw redirect(307, '/settings?tab=library');
};
