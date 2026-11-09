/**
 * 根布局：React Query + 安全区 + 路由 Stack。
 * pet/new 与 pet/[id] 是模态外的普通页面。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { loadServerUrl } from '@/lib/serverUrl';
import { colors } from '@/lib/theme';

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
    void loadServerUrl();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
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
          <Stack.Screen name="pet/new" options={{ title: '添加宠物' }} />
          <Stack.Screen name="pet/[id]" options={{ title: '编辑宠物' }} />
        </Stack>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
