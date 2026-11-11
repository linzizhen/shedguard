/**
 * 摄像头设备标识的持久化与订阅。
 *
 * 一台摄像头（ESP32-S3-EYE）有固定 device_id，App 侧记住它，
 * 用于把「设备 → 宠物」绑定关系上报给服务端，以及查询该设备的提醒。
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';

const KEY = 'shedguard.device-id';

let current = '';
let loaded = false;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((listener) => listener());
}

export function getDeviceId(): string {
  return current;
}

/** App 启动时调用一次，从 AsyncStorage 恢复 */
export async function loadDeviceId(): Promise<void> {
  if (loaded) return;
  current = (await AsyncStorage.getItem(KEY)) ?? '';
  loaded = true;
  emit();
}

/** 设置页保存时调用 */
export async function saveDeviceId(value: string): Promise<void> {
  current = value.trim();
  loaded = true;
  await AsyncStorage.setItem(KEY, current);
  emit();
}

export function useDeviceId(): string {
  return useSyncExternalStore(
    (callback) => {
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
    () => current,
  );
}
