import fs from 'node:fs/promises';
import path from 'node:path';

export async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

export async function readJSON(filePath) {
  try {
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data);
  } catch (err) {
    if (err.code === 'ENOENT') return null;
    throw err;
  }
}

export async function writeJSON(filePath, data) {
  await ensureDir(path.dirname(filePath));
  const json = JSON.stringify(data, null, 2) + '\n';
  await fs.writeFile(filePath, json, 'utf-8');
}

export async function deleteFile(filePath) {
  try {
    await fs.unlink(filePath);
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }
}

export async function deleteDir(dirPath) {
  try {
    await fs.rm(dirPath, { recursive: true, force: true });
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }
}

export async function listFiles(dirPath, extension) {
  try {
    const entries = await fs.readdir(dirPath);
    if (extension) {
      return entries.filter(e => e.endsWith(extension));
    }
    return entries;
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
}

export async function copyFile(src, dest) {
  await ensureDir(path.dirname(dest));
  await fs.copyFile(src, dest);
}

export async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}
