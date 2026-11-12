/**
 * 蜕皮知识列表（从「我的」进入，不再是独立 Tab）。
 * 后端：GET /api/v1/knowledge/topics。
 */
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, Screen } from '@/components/ui';
import { useKnowledgeTopics } from '@/hooks/useKnowledge';
import { useServerUrl } from '@/lib/serverUrl';
import { colors, radius } from '@/lib/theme';

export default function KnowledgeScreen() {
  const serverUrl = useServerUrl();
  const topicsQuery = useKnowledgeTopics();

  return (
    <Screen>
      {serverUrl === '' ? (
        <Card>
          <EmptyState
            icon="cloud-offline"
            title="App 还没连上电脑"
            subtitle="在「我的 → 高级设置」里填入电脑地址。"
          />
        </Card>
      ) : topicsQuery.isLoading ? (
        <Card>
          <EmptyState icon="hourglass" title="加载中…" />
        </Card>
      ) : topicsQuery.isError ? (
        <Card>
          <EmptyState icon="cloud-offline" title="加载不出来" subtitle="检查一下网络，稍后再试。" />
        </Card>
      ) : (
        <View style={styles.list}>
          {(topicsQuery.data?.items ?? []).map((topic, index) => (
            <Pressable
              key={topic.slug}
              onPress={() => router.push(`/topic/${topic.slug}`)}
              accessibilityRole="button"
              style={({ pressed }) => [styles.topicCard, pressed && styles.topicPressed]}
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
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          ))}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: 12 },
  topicCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderWidth: 3,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: 16,
    gap: 12,
    minHeight: 64,
  },
  topicPressed: { opacity: 0.85 },
  indexBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.background,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  indexText: { fontSize: 15, fontWeight: '800', color: colors.primary },
  topicBody: { flex: 1, gap: 4 },
  topicTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground },
  topicSummary: { fontSize: 13, lineHeight: 19, color: colors.mutedForeground },
  chevron: { fontSize: 26, color: colors.primary, fontWeight: '300' },
});
