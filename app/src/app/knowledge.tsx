/**
 * 蜕皮知识列表（从「我的」进入，不再是独立 Tab）。
 * 后端：GET /api/v1/knowledge/topics。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, Screen } from '@/components/ui';
import { useKnowledgeTopics } from '@/hooks/useKnowledge';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, hairline, radius, shadow, space, type } from '@/lib/theme';

export default function KnowledgeScreen() {
  const serverUrl = useServerUrl();
  const topicsQuery = useKnowledgeTopics();

  if (serverUrl === '') {
    return (
      <Screen>
        <Card>
          <EmptyState
            icon="cloud-offline-outline"
            title="App 还没连上电脑"
            subtitle="在「我的 → 高级设置」里填入电脑地址。"
          />
        </Card>
      </Screen>
    );
  }

  if (topicsQuery.isLoading) {
    return (
      <Screen>
        <Card>
          <EmptyState icon="hourglass-outline" title="加载中…" />
        </Card>
      </Screen>
    );
  }

  if (topicsQuery.isError) {
    return (
      <Screen>
        <Card>
          <EmptyState
            icon="cloud-offline-outline"
            title="加载不出来"
            subtitle="检查一下网络，稍后再试。"
          />
        </Card>
      </Screen>
    );
  }

  const topics = topicsQuery.data?.items ?? [];

  return (
    <Screen>
      <Text style={styles.intro}>它为什么发白、要不要帮它撕、卡皮了怎么办。</Text>
      <View style={styles.list}>
        {topics.map((topic, index) => (
          <Pressable
            key={topic.slug}
            onPress={() => router.push(`/topic/${topic.slug}`)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.topicCard, pressed && clayPress]}
          >
            <View style={styles.indexBadge}>
              <Text style={styles.indexText}>{index + 1}</Text>
            </View>
            <View style={styles.topicBody}>
              <Text style={styles.topicTitle}>{topic.title}</Text>
              <Text style={styles.topicSummary} numberOfLines={2}>
                {topic.summary}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={17} color={colors.faintForeground} />
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
  list: {
    gap: space.md,
  },
  topicCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderWidth: hairline,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.md,
    minHeight: 64,
    ...shadow.card,
  },
  indexBadge: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  indexText: {
    ...type.caption,
    fontWeight: '800',
    color: colors.primaryDark,
  },
  topicBody: {
    flex: 1,
    gap: 2,
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