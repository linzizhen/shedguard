/**
 * 服务器地址的持久化与订阅。
 *
 * App 连的是用户自己电脑上跑的 FastAPI 服务（局域网 HTTP），
 * 地址在「设置」页填写，存 AsyncStorage；网络层直接读模块级变量。
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';

const KEY = 'shedguard.server-url';

/** 开发/演示用：可用 EXPO_PUBLIC_SERVER_URL 预填地址，正式包留空由用户填写。 */
const DEV_DEFAULT = process.env.EXPO_PUBLIC_SERVER_URL ?? '';

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
  current = (await AsyncStorage.getItem(KEY)) ?? DEV_DEFAULT;
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
