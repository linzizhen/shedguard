/**
 * 底部四 Tab：拍照查验 / 蜕皮日志 / 知识 / 设置。
 * 当前 Tab 橙色高亮；白底 tabBar、浅橙描边。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import type { PropsWithChildren } from 'react';

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
        },
        tabBarLabelStyle: {
          fontSize: 12,
          fontWeight: '700',
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: '拍照查验',
          tabBarIcon: ({ color, size }) => <TabIcon name="camera" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="log"
        options={{
          title: '蜕皮日志',
          tabBarIcon: ({ color, size }) => (
            <TabIcon name="calendar-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="knowledge"
        options={{
          title: '知识',
          tabBarIcon: ({ color, size }) => <TabIcon name="book-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "设置",
          tabBarIcon: ({ color, size }) => (
            <TabIcon name="settings-outline" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
