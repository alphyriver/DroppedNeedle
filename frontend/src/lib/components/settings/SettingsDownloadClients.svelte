<script lang="ts">
	import SettingsDownloadClient from './SettingsDownloadClient.svelte';
	import SettingsDownloadPolicy from './SettingsDownloadPolicy.svelte';
	import SettingsOnboardingChecklist from './SettingsOnboardingChecklist.svelte';
	import SettingsQbittorrent from './SettingsQbittorrent.svelte';
	import SettingsSabnzbd from './SettingsSabnzbd.svelte';
	import SettingsSourcePriority from './SettingsSourcePriority.svelte';
	import SettingsWanted from './SettingsWanted.svelte';
</script>

<div class="space-y-6">
	<div>
		<h2 class="text-xl font-bold">Download clients</h2>
		<p class="text-sm text-base-content/60">
			Soulseek, Usenet and torrents are three ways to acquire music. Configure any of them, set
			which is tried first, and tune the shared policy.
		</p>
	</div>
	<SettingsDownloadPolicy />
	<SettingsWanted />
	<SettingsSourcePriority />
	<SettingsDownloadClient />
	<SettingsSabnzbd />
	<SettingsQbittorrent />
	<SettingsOnboardingChecklist />
</div>
