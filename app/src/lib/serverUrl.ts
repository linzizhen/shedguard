/**
 * 服务器地址的持久化与订阅。
 *
 * App 连的是用户自己电脑上跑的 FastAPI 服务（局域网 HTTP），
 * 地址在「设置」页填写，存 AsyncStorage；网络层直接读模块级变量。
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';

import { inferServerUrl } from './serverUrlInfer';

const KEY = 'shedguard.server-url';

/** 开发/演示用：可用 EXPO_PUBLIC_SERVER_URL 预填地址，正式包留空由用户填写。 */
const DEV_DEFAULT = process.env.EXPO_PUBLIC_SERVER_URL ?? '';

/**
 * 读当前页面地址。原生端没有 window，返回 null —— 那就保持「由用户填写」。
 */
function readLocation(): { origin: string; port: string } | null {
  const global = globalThis as { location?: { origin: string; port: string } };
  return global.location ?? null;
}

let current = '';
let loaded = false;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((listener) => listener());
}

/** 网络层用：同步读当前地址（可能为空串） */
export function getServerUrl(): string {
  return current;
}

/** App 启动时调用一次，从 AsyncStorage 恢复 */
export async function loadServerUrl(): Promise<void> {
  if (loaded) return;
  const saved = await AsyncStorage.getItem(KEY);
  // 用户没填过地址时不再要求手填：页面自己就是服务端时，地址取当前页面来源。
  current = inferServerUrl(saved ?? DEV_DEFAULT, readLocation());
  loaded = true;
  emit();
}

/** 设置页保存时调用 */
export async function saveServerUrl(url: string): Promise<void> {
  current = url.trim();
  await AsyncStorage.setItem(KEY, current);
  emit();
}

/** 组件里用：地址变化时触发重渲染与重新请求 */
export function useServerUrl(): string {
  return useSyncExternalStore(
    (callback) => {
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
    () => current,
  );
}
