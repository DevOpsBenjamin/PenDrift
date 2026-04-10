import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '../../..');

export const DATA_ROOT = path.join(PROJECT_ROOT, 'data');
export const SESSIONS_DIR = path.join(DATA_ROOT, 'sessions');
export const PRESETS_DIR = path.join(DATA_ROOT, 'presets');
export const SETTINGS_DIR = path.join(PRESETS_DIR, 'settings');
export const TEMPLATES_DIR = path.join(PRESETS_DIR, 'templates');
export const DEFAULTS_DIR = path.resolve(__dirname, '../../defaults');
