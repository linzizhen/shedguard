/**
 * 首次使用向导的完成标记。存在 AsyncStorage，避免每次开 App 都弹向导。
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const ONBOARDED_KEY = 'shedguard.onboarded';

let onboarded = false;

export function isOnboarded(): boolean {
  return onboarded;
}

export async function loadOnboarded(): Promise<void> {
  try {
    onboarded = (await AsyncStorage.getItem(ONBOARDED_KEY)) === '1';
  } catch {
    onboarded = false;
  }
}

export async function markOnboarded(): Promise<void> {
  onboarded = true;
  try {
    await AsyncStorage.setItem(ONBOARDED_KEY, '1');
  } catch {
    // 存不上只影响下次是否重弹向导，不影响主流程
  }
}
