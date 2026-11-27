/**
 * 底部三个 Tab：拍照 / 蜕皮记录 / 我的。
 * 纸感极简（P34）：纸底 + 顶部 1px 纸线，选中态用近黑而不是彩色。
 */
import type { PropsWithChildren } from 'react';

import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

import { colors, hairline, type } from '@/lib/theme';

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
        tabBarActiveTintColor: colors.foreground,
        tabBarInactiveTintColor: colors.faintForeground,
        tabBarStyle: {
          backgroundColor: colors.background,
          borderTopColor: colors.divider,
          borderTopWidth: hairline,
          height: 62,
          paddingTop: 7,
          paddingBottom: 7,
          paddingHorizontal: 0,
          elevation: 0,
        },
        tabBarLabelStyle: {
          ...type.label,
          fontWeight: '600',
          letterSpacing: 0.4,
        },
        tabBarIconStyle: {
          marginBottom: -1,
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
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name={focused ? 'camera' : 'camera-outline'} color={color} size={22} />
          ),
        }}
      />
      <Tabs.Screen
        name="log"
        options={{
          title: '记录',
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name={focused ? 'calendar' : 'calendar-outline'} color={color} size={21} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: '我的',
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name={focused ? 'person' : 'person-outline'} color={color} size={21} />
          ),
        }}
      />
    </Tabs>
  );
}
