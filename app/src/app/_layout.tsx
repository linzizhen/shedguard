/**
 * 根布局：React Query + 安全区 + 路由 Stack。
 * pet/new 与 pet/[id] 是模态外的普通页面。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack, router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useNotificationRefresh } from '@/hooks/useAlerts';
import { ensureToken, loadToken } from '@/lib/auth';
import { loadDeviceId } from '@/lib/deviceId';
import { isOnboarded, loadOnboarded } from '@/lib/onboarding';
import { loadServerUrl } from '@/lib/serverUrl';
import { colors } from '@/lib/theme';

/** 挂在 Provider 内：收到前台通知时刷新提醒列表。 */
function NotificationBridge() {
  useNotificationRefresh();
  return null;
}

export default function RootLayout() {
  // useState 初始化器保证 QueryClient 只建一次
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            staleTime: 30_000,
          },
        },
      }),
  );

  useEffect(() => {
    void (async () => {
      await loadServerUrl();
      void loadDeviceId();
      await loadToken();
      await loadOnboarded();
      // 已配置服务器时提前领取匿名账号，避免首个请求等待注册。
      try {
        await ensureToken();
      } catch {
        // 未配置服务器或注册失败时忽略，首个 API 请求会再试。
      }
      // 第一次打开 App 先走向导，别让用户一进来就面对四个页面。
      if (!isOnboarded()) {
        router.replace('/welcome');
      }
    })();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <NotificationBridge />
      <SafeAreaProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.background },
            headerTintColor: colors.foreground,
            headerTitleStyle: { fontWeight: '800' },
            contentStyle: { backgroundColor: colors.background },
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="welcome" options={{ headerShown: false }} />
          <Stack.Screen name="knowledge" options={{ title: '蜕皮知识' }} />
          <Stack.Screen name="pet/new" options={{ title: '添加宠物' }} />
          <Stack.Screen name="pet/[id]" options={{ title: '编辑宠物' }} />
          <Stack.Screen name="topic/[slug]" options={{ title: '知识详情' }} />
          <Stack.Screen name="alert/[id]" options={{ title: '蜕皮提醒' }} />
          <Stack.Screen name="risk" options={{ title: '卡皮风险评估' }} />
        </Stack>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
