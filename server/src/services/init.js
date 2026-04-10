import path from 'node:path';
import {
  DATA_ROOT, SESSIONS_DIR, SETTINGS_DIR, TEMPLATES_DIR, DEFAULTS_DIR,
} from '../utils/paths.js';
import { ensureDir, fileExists, copyFile, listFiles } from './storage.js';

export async function initDataDirectories() {
  await ensureDir(SESSIONS_DIR);
  await ensureDir(SETTINGS_DIR);
  await ensureDir(TEMPLATES_DIR);

  // Copy default settings presets if none exist
  const existingSettings = await listFiles(SETTINGS_DIR, '.json');
  if (existingSettings.length === 0) {
    const defaultSettings = await listFiles(path.join(DEFAULTS_DIR, 'settings'), '.json');
    for (const file of defaultSettings) {
      await copyFile(
        path.join(DEFAULTS_DIR, 'settings', file),
        path.join(SETTINGS_DIR, file),
      );
    }
    console.log(`Copied ${defaultSettings.length} default settings preset(s)`);
  }

  // Copy default templates if none exist
  const existingTemplates = await listFiles(TEMPLATES_DIR, '.json');
  if (existingTemplates.length === 0) {
    const defaultTemplates = await listFiles(path.join(DEFAULTS_DIR, 'templates'), '.json');
    for (const file of defaultTemplates) {
      await copyFile(
        path.join(DEFAULTS_DIR, 'templates', file),
        path.join(TEMPLATES_DIR, file),
      );
    }
    console.log(`Copied ${defaultTemplates.length} default template(s)`);
  }

  console.log(`Data directory initialized at ${DATA_ROOT}`);
}
