import api from './client.js';

export const listPrompts = () => api.get('prompts').json();

export const getPrompt = (name) => api.get(`prompts/${encodeURIComponent(name)}`).json();
