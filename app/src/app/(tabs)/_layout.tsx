/**
 * 底部三个 Tab：首页（拍照）/ 蜕皮记录 / 我的。
 * 只有三格，窄屏也不会被裁；技术设置全部收进「我的」里。
 */
import type { PropsWithChildren } from 'react';

import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

import { colors } from '@/lib/theme';

/** Tab 图标：RN 0.88 的 color 参数类型是 ColorValue（可为 null），此处收窄为 string */
function TabIcon({
  name,
  color,
  size,
}: PropsWithChildren<{ name: keyof typeof Ionicons.glyphMap; color: unknown; size: number }>) {
  return <Ionicons name={name} size={size} color={color as string} />;
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.mutedForeground,
        tabBarStyle: {
          backgroundColor: colors.card,
          borderTopColor: colors.border,
          borderTopWidth: 3,
          height: 68,
          paddingTop: 6,
          paddingHorizontal: 0,
        },
        tabBarLabelStyle: {
          fontSize: 12,
          fontWeight: '700',
        },
        tabBarItemStyle: {
          flex: 1,
          minWidth: 0,
          paddingHorizontal: 0,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: '拍照',
          tabBarIcon: ({ color, size }) => <TabIcon name="camera" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="log"
        options={{
          title: '蜕皮记录',
          tabBarIcon: ({ color, size }) => (
            <TabIcon name="calendar-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: '我的',
          tabBarIcon: ({ color, size }) => (
            <TabIcon name="person-outline" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
