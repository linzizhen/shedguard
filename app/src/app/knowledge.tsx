/**
 * 蜕皮知识列表（从「我的」进入，不再是独立 Tab）。
 * 后端：GET /api/v1/knowledge/topics。
 * 纸感极简（P34）：条目按 1px 纸线分隔，序号用琥珀小字，不用卡片与图标底座。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Divider, EmptyState, Screen } from '@/components/ui';
import { useKnowledgeTopics } from '@/hooks/useKnowledge';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, hairline, space, type } from '@/lib/theme';

export default function KnowledgeScreen() {
  const serverUrl = useServerUrl();
  const topicsQuery = useKnowledgeTopics();

  if (serverUrl === '') {
    return (
      <Screen>
        <EmptyState
          title="还没连上服务端"
          subtitle="在「我的 → 高级设置」里填入地址。"
        />
      </Screen>
    );
  }

  if (topicsQuery.isLoading) {
    return (
      <Screen>
        <Text style={styles.intro}>加载中…</Text>
      </Screen>
    );
  }

  if (topicsQuery.isError) {
    return (
      <Screen>
        <EmptyState title="加载不出来" subtitle="检查一下网络，稍后再试。" />
      </Screen>
    );
  }

  const topics = topicsQuery.data?.items ?? [];

  return (
    <Screen>
      <Text style={styles.intro}>它为什么发白、要不要帮它撕、卡皮了怎么办。</Text>
      <Divider />
      <View>
        {topics.map((topic, index) => (
          <Pressable
            key={topic.slug}
            onPress={() => router.push(`/topic/${topic.slug}`)}
            accessibilityRole="button"
            style={({ pressed }) => [
              styles.topicRow,
              index < topics.length - 1 && styles.rowDivider,
              pressed && clayPress,
            ]}
          >
            <Text style={styles.index}>{`0${index + 1}`}</Text>
            <View style={styles.topicBody}>
              <Text style={styles.topicTitle}>{topic.title}</Text>
              <Text style={styles.topicSummary} numberOfLines={2}>
                {topic.summary}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.ghostForeground} />
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  intro: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  topicRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.lg,
    gap: space.md,
    minHeight: 64,
  },
  rowDivider: {
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
  },
  index: {
    ...type.caption,
    fontWeight: '700',
    color: colors.accent,
    letterSpacing: 1,
    width: 24,
  },
  topicBody: {
    flex: 1,
    gap: 3,
  },
  topicTitle: {
    ...type.heading,
    fontSize: 16,
    color: colors.foreground,
  },
  topicSummary: {
    ...type.caption,
    color: colors.mutedForeground,
  },
});
