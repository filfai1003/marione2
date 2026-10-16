import { set, store } from './store.js';
import { t } from './i18n.js';

export class ApiError extends Error {
  constructor(status, body) {
    super(body.message || t('common.error'));
    this.status = status;
    this.code = body.error || 'error';
    this.cooldownSeconds = body.cooldownSeconds;
  }
}

export const hooks = { onUnauthorized() {} };

export async function api(path, { method = 'GET', json, form } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: json ? { 'Content-Type': 'application/json' } : {},
      body: json ? JSON.stringify(json) : form,
    });
  } catch {
    if (store.online) set({ online: false });
    throw new ApiError(0, { error: 'network', message: t('common.network') });
  }
  if (!store.online) set({ online: true });
  let body = null;
  try { body = await res.json(); } catch { body = null; }
  if (!res.ok || (body && body.ok === false)) {
    const err = new ApiError(res.status, body || {});
    if (res.status === 401) hooks.onUnauthorized();
    throw err;
  }
  return body || {};
}

export const post = (path, json = {}) => api(path, { method: 'POST', json });
