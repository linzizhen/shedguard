/**
 * 匿名账号令牌管理。
 *
 * - 首次启动调用 `POST /api/v1/users/anonymous` 领取 token，只存本机。
 * - token 存 AsyncStorage；服务端只保存其 sha256。
 * - 401 时由 api 层调用 `resetToken()` 清空，下次请求会重新注册。
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { getServerUrl } from './serverUrl';

const TOKEN_KEY = 'shedguard.auth-token';

let cached: string | null = null;
let inflight: Promise<string> | null = null;

/** 同步读取内存中的令牌（可能为 null）。 */
export function getToken(): string | null {
  return cached;
}

/** 启动时从本机恢复令牌。 */
export async function loadToken(): Promise<void> {
  try {
    cached = await AsyncStorage.getItem(TOKEN_KEY);
  } catch {
    cached = null;
  }
}

async function register(): Promise<string> {
  const base = getServerUrl().replace(/\/+$/, '');
  if (!base) throw new Error('NO_SERVER');
  const res = await fetch(`${base}/api/v1/users/anonymous`, { method: 'POST' });
  if (!res.ok) throw new Error(`注册失败（HTTP ${res.status}）`);
  const body = (await res.json()) as { token: string };
  cached = body.token;
  await AsyncStorage.setItem(TOKEN_KEY, body.token);
  return body.token;
}

/** 确保有令牌可用；没有就注册一个。并发调用共用同一个请求。 */
export async function ensureToken(): Promise<string> {
  if (cached) return cached;
  if (!inflight) {
    inflight = (async () => {
      await loadToken();
      if (cached) return cached;
      return register();
    })().finally(() => {
      inflight = null;
    });
  }
  return inflight;
}

/** 清空本地令牌（收到 401 或用户在设置页重置身份时）。 */
export async function resetToken(): Promise<void> {
  cached = null;
  inflight = null;
  try {
    await AsyncStorage.removeItem(TOKEN_KEY);
  } catch {
    // 忽略存储错误
  }
}

/** 把图片路径拼成带令牌的完整 URL（RN 的 <Image> 不能加请求头）。 */
export function imageUrl(imageId: string): string {
  const base = getServerUrl().replace(/\/+$/, '');
  const token = cached ? `?token=${encodeURIComponent(cached)}` : '';
  return `${base}/api/v1/images/${imageId}${token}`;
}

/** 萌照成品图的地址（服务端二次裁成正方形）。 */
export function portraitUrl(shotId: string): string {
  const base = getServerUrl().replace(/\/+$/, '');
  const token = cached ? `?token=${encodeURIComponent(cached)}` : '';
  return `${base}/api/v1/portraits/${shotId}/image${token}`;
}
