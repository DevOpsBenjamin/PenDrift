import path from 'node:path';
import { TEMPLATES_DIR } from '../utils/paths.js';
import { readJSON, writeJSON, listFiles, deleteFile } from './storage.js';

export async function listTemplates() {
  const files = await listFiles(TEMPLATES_DIR, '.json');
  const templates = [];
  for (const file of files) {
    const template = await readJSON(path.join(TEMPLATES_DIR, file));
    if (template) templates.push(template);
  }
  return templates;
}

export async function getTemplate(id) {
  const template = await readJSON(path.join(TEMPLATES_DIR, `${id}.json`));
  if (!template) {
    throw Object.assign(new Error('Template not found'), { status: 404 });
  }
  return template;
}

export async function saveTemplate(template) {
  if (!template.id) {
    throw Object.assign(new Error('Template must have an id'), { status: 400 });
  }
  await writeJSON(path.join(TEMPLATES_DIR, `${template.id}.json`), template);
  return template;
}

export async function deleteTemplate(id) {
  await deleteFile(path.join(TEMPLATES_DIR, `${id}.json`));
}
