/**
 * 蜕皮提醒（alerts）与推送设备注册（devices）相关 hooks。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';

import { apiFetch } from '@/lib/api';
import { useServerUrl } from '@/lib/serverUrl';
import type { AlertItem, AlertListResponse, DeviceRegisterInput, PushDevice } from '@/lib/types';

/** 前台收到通知时也显示横幅（App 打开状态下）。 */
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

/** 拉取提醒列表（按时间倒序）。 */
export function useAlerts(options: { petId?: string | null; deviceId?: string | null } = {}) {
  const serverUrl = useServerUrl();
  const { petId, deviceId } = options;
  const params = new URLSearchParams();
  if (petId) params.set('pet_id', petId);
  if (deviceId) params.set('device_id', deviceId);
  params.set('limit', '50');
  const query = params.toString();
  return useQuery({
    queryKey: ['alerts', serverUrl, petId ?? '', deviceId ?? ''],
    queryFn: () => apiFetch<AlertListResponse>(`/api/v1/alerts?${query}`),
    enabled: serverUrl !== '' && (Boolean(petId) || Boolean(deviceId)),
    refetchInterval: 60_000,
  });
}

/** 标记提醒已读。 */
export function useMarkAlertRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ alertId, read }: { alertId: string; read: boolean }) =>
      apiFetch<AlertItem>(`/api/v1/alerts/${alertId}`, {
        method: 'PATCH',
        body: JSON.stringify({ read }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

/** 注册/更新推送 token。 */
export function useRegisterDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DeviceRegisterInput) =>
      apiFetch<PushDevice>('/api/v1/devices', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export type PushSetupState =
  | { kind: 'idle' }
  | { kind: 'working' }
  | { kind: 'ok'; token: string }
  | { kind: 'denied'; message: string }
  | { kind: 'unsupported'; message: string }
  | { kind: 'error'; message: string };

/**
 * 申请通知权限并取 Expo push token。
 * Web 与 Expo Go 下取不到 token，返回 unsupported（提醒列表仍可兜底查看）。
 */
export async function obtainPushToken(): Promise<PushSetupState> {
  if (Platform.OS === 'web') {
    return { kind: 'unsupported', message: '网页版不支持推送，提醒仍可在列表查看' };
  }
  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: '蜕皮提醒',
        importance: 3, // 3 = AndroidImportance.DEFAULT
        lightColor: '#F97316',
      });
    }
    const existing = await Notifications.getPermissionsAsync();
    let granted = existing.granted;
    if (!granted && existing.canAskAgain) {
      const asked = await Notifications.requestPermissionsAsync();
      granted = asked.granted;
    }
    if (!granted) {
      return { kind: 'denied', message: '未授予通知权限，可到系统设置里开启' };
    }
    const projectId =
      Constants.expoConfig?.extra?.eas?.projectId ??
      (Constants as unknown as { easConfig?: { projectId?: string } }).easConfig?.projectId;
    if (!projectId) {
      return {
        kind: 'unsupported',
        message: '需要 EAS 构建（development build）并配置 projectId 才能推送，见 docs/push-setup.md',
      };
    }
    const token = await Notifications.getExpoPushTokenAsync({ projectId });
    return { kind: 'ok', token: token.data };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    // Expo Go / 未配置 EAS projectId 时无法获得远端推送 token。
    return { kind: 'unsupported', message: `当前环境不支持推送（${message}），提醒仍可在列表查看` };
  }
}

/** 监听前台通知，收到时刷新提醒列表。 */
export function useNotificationRefresh() {
  const queryClient = useQueryClient();
  const subscription = useRef<Notifications.EventSubscription | null>(null);
  useEffect(() => {
    subscription.current = Notifications.addNotificationReceivedListener(() => {
      void queryClient.invalidateQueries({ queryKey: ['alerts'] });
    });
    return () => {
      subscription.current?.remove();
    };
  }, [queryClient]);
}

/** 设置屏用的推送启用流程：拿 token 并上报到服务端。 */
export function useEnablePush() {
  const [state, setState] = useState<PushSetupState>({ kind: 'idle' });
  const register = useRegisterDevice();
  const enable = useCallback(
    async (deviceId: string, petId: string | null) => {
      setState({ kind: 'working' });
      const result = await obtainPushToken();
      if (result.kind !== 'ok') {
        setState(result);
        return;
      }
      try {
        await register.mutateAsync({
          expo_push_token: result.token,
          platform: Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : 'web',
          device_id: deviceId.trim() || undefined,
          pet_id: petId ?? undefined,
        });
        setState({ kind: 'ok', token: result.token });
      } catch (error) {
        setState({ kind: 'error', message: error instanceof Error ? error.message : String(error) });
      }
    },
    [register],
  );
  return { state, enable, isPending: register.isPending };
}
