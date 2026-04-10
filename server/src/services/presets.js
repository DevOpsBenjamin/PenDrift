import path from 'node:path';
import { SETTINGS_DIR } from '../utils/paths.js';
import { readJSON, writeJSON, listFiles, deleteFile } from './storage.js';

export async function listSettingsPresets() {
  const files = await listFiles(SETTINGS_DIR, '.json');
  const presets = [];
  for (const file of files) {
    const preset = await readJSON(path.join(SETTINGS_DIR, file));
    if (preset) presets.push(preset);
  }
  return presets;
}

export async function getSettingsPreset(id) {
  const preset = await readJSON(path.join(SETTINGS_DIR, `${id}.json`));
  if (!preset) {
    throw Object.assign(new Error('Settings preset not found'), { status: 404 });
  }
  return preset;
}

export async function saveSettingsPreset(preset) {
  if (!preset.id) {
    throw Object.assign(new Error('Preset must have an id'), { status: 400 });
  }
  await writeJSON(path.join(SETTINGS_DIR, `${preset.id}.json`), preset);
  return preset;
}

export async function deleteSettingsPreset(id) {
  if (id === 'default') {
    throw Object.assign(new Error('Cannot delete the default preset'), { status: 400 });
  }
  await deleteFile(path.join(SETTINGS_DIR, `${id}.json`));
}
